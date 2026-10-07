import {test, expect, chromium} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('mobile, reduced motion, and unavailable WebGL keep the workspace usable without the effect bundle', async ({page}) => {
  const effects = [];
  page.on('request', request => { if (request.url().includes('/effects/')) effects.push(request.url()); });
  await page.setViewportSize({width: 390, height: 844});
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await page.goto('/');
  await page.getByRole('button', {name: 'Review 3 orders'}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.setViewportSize({width: 1440, height: 1000});
  await page.emulateMedia({reducedMotion: 'reduce'});
  await page.goto('/');
  await page.getByRole('button', {name: 'Refresh workspace'}).click();
  await expect(page.locator('.hero-scene canvas')).toHaveCount(0);
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      return type.startsWith('webgl') ? null : getContext.call(this, type, ...args);
    };
  });
  await page.reload();
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await expect(page.locator('.hero-scene')).toHaveAttribute('data-renderer', 'unavailable');
  await page.getByRole('button', {name: 'Review 3 orders'}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  expect(effects).toEqual([]);
});

test('order sorting preserves filters, focus, and the newest-first overview', async ({page}) => {
  await page.goto('/#orders');
  const amounts = () => page.locator('tbody tr td:last-child').allTextContents().then(values => values.map(value => Number(value.replace(/[^\d.]/g, ''))));
  await page.getByLabel('Sort orders').selectOption('highest');
  const descending = await amounts();
  expect(descending).toEqual([...descending].sort((a, b) => b - a));
  await expect(page.getByLabel('Sort orders')).toBeFocused();
  await page.getByRole('button', {name: 'Pending', exact: true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.getByLabel('Sort orders').selectOption('lowest');
  const ascending = await amounts();
  expect(ascending).toEqual([...ascending].sort((a, b) => a - b));
  await page.getByRole('button', {name: 'Overview', exact: true}).click();
  await expect(page.locator('tbody tr').first()).toContainText('TB-1048');
});

test('glass quick actions retain contrast, focus containment, and dismissal in both themes', async ({page}) => {
  for (const theme of ['light', 'dark']) {
    await page.emulateMedia({colorScheme: theme});
    await page.goto('/');
    await page.getByRole('button', {name: 'Quick actions', exact: true}).click();
    await expect(page.getByLabel('Find a quick action')).toBeFocused();
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('button', {name: /Shop overview/})).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', {name: 'Quick actions', exact: true})).toBeFocused();
  }
});

test('real shader draws locally, survives refresh, pauses, disposes, and falls back on context loss', async () => {
  test.setTimeout(120000);
  const browser = await chromium.launch({args: ['--enable-unsafe-swiftshader']});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
    const errors = [], external = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:8000/')) external.push(request.url()); });
    await page.addInitScript(() => {
      window.shaderDraws = 0;
      for (const method of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
        const original = WebGL2RenderingContext.prototype[method];
        WebGL2RenderingContext.prototype[method] = function(...args) { window.shaderDraws++; return original.apply(this, args); };
      }
    });
    await page.goto('http://127.0.0.1:8000/');
    const scene = page.locator('.hero-scene');
    await expect(scene).toHaveAttribute('data-renderer', 'shader', {timeout: 30000});
    await expect.poll(() => page.evaluate(() => window.shaderDraws), {timeout: 30000}).toBeGreaterThan(0);
    await scene.evaluate(node => { window.originalScene = node; window.originalCanvas = node.querySelector('canvas'); });
    await page.getByRole('button', {name: 'Refresh workspace'}).click();
    expect(await scene.evaluate(node => node === window.originalScene && node.querySelector('canvas') === window.originalCanvas)).toBe(true);
    await page.getByRole('button', {name: 'Pause ambient motion'}).click();
    await page.getByRole('heading', {name: 'A good day to grow.'}).scrollIntoViewIfNeeded();
    await expect(scene).toHaveAttribute('data-rendering', 'paused');
    await page.waitForTimeout(500);
    const paused = await page.evaluate(() => window.shaderDraws);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.shaderDraws)).toBe(paused);
    await page.getByRole('button', {name: 'Play ambient motion'}).click();
    await page.getByRole('heading', {name: 'A good day to grow.'}).scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => window.shaderDraws)).toBeGreaterThan(paused);
    await page.getByRole('button', {name: 'Inventory', exact: true}).click();
    await expect(page.locator('.hero-scene')).toHaveCount(0);
    await page.getByRole('button', {name: 'Overview', exact: true}).click();
    await expect(scene).toHaveAttribute('data-renderer', 'shader', {timeout: 30000});
    await scene.locator('canvas').evaluate(canvas => canvas.getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
    await expect(scene).toHaveAttribute('data-renderer', 'fallback');
    await page.getByRole('button', {name: 'Review 3 orders'}).click();
    await expect(page.locator('tbody tr')).toHaveCount(3);
    expect(external).toEqual([]);
    expect(errors).toEqual([]);
  } finally { await browser.close(); }
});
