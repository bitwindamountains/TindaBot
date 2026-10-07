import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('overview, filtering, order progression, CSV, and inventory adjustment', async ({page}) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByText('Preview mode.')).toBeVisible();
  await page.getByRole('button', {name: 'View all orders'}).click();
  await page.getByRole('button', {name: 'Pending', exact: true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', {name: 'Confirm order', exact: true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.getByRole('searchbox').fill('no-such-order');
  await expect(page.getByRole('heading', {name: 'No orders match just yet'})).toBeVisible();
  await page.getByRole('button', {name: 'Clear filters'}).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', {name: 'Export CSV'}).click();
  expect((await download).suggestedFilename()).toBe('tindabot-sample-orders.csv');
  await page.getByRole('button', {name: 'Inventory', exact: true}).click();
  await page.getByRole('button', {name: 'Low stock', exact: true}).click();
  await expect(page.locator('.product')).toHaveCount(2);
  await page.getByRole('button', {name: 'Adjust stock'}).first().click();
  await page.getByLabel('Units to add or remove').fill('0');
  await page.getByRole('button', {name: 'Save adjustment'}).click();
  await expect(page.getByRole('alert')).toHaveText('Enter a whole number other than zero.');
  await page.getByLabel('Units to add or remove').fill('10');
  await page.getByRole('button', {name: 'Save adjustment'}).click();
  await expect(page.locator('.product')).toHaveCount(1);
  await page.getByRole('button', {name: 'Automation', exact: true}).click();
  await page.getByRole('switch', {name: 'Automated replies'}).click();
  await page.getByRole('button', {name: 'Pause replies', exact: true}).click();
  await expect(page.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  expect(errors).toEqual([]);
});

for (const theme of ['light', 'dark']) {
  test(`${theme} contrast, accessibility, keyboard, and desktop screenshot`, async ({page}) => {
    await page.setViewportSize({width: 1440, height: 1100});
    await page.emulateMedia({colorScheme: theme, reducedMotion: 'reduce'});
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect(page.getByRole('heading', {name: 'A good day to grow.'})).toBeVisible();
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.screenshot({path: `docs/validation/workspace-${theme}.png`, fullPage: true});
    await page.keyboard.press('/');
    await expect(page.getByRole('searchbox')).toBeFocused();
    await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
    await expect(page.getByLabel('Operator token', {exact: true})).toBeFocused();
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', {name: 'Connect shop', exact: true})).toBeFocused();
    await page.getByRole('button', {name: `Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}).click();
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme === 'light' ? 'dark' : 'light');
  });
}

test('mobile layouts, touch targets, all views, and reduced motion', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.emulateMedia({colorScheme: 'light', reducedMotion: 'reduce'});
  await page.goto('/');
  await page.screenshot({path: 'docs/validation/workspace-mobile.png', fullPage: true});
  for (const view of ['Overview', 'Orders', 'Inventory', 'Automation']) {
    await page.locator('.nav').getByRole('button', {name: view}).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    const undersized = await page.locator('button:visible, input:visible, select:visible').evaluateAll(nodes => nodes.filter(n => {const r = n.getBoundingClientRect(); return r.width < 44 || r.height < 44;}).map(n => n.textContent || n.getAttribute('aria-label')));
    expect(undersized).toEqual([]);
  }
  await page.setViewportSize({width: 320, height: 720});
  await page.locator('.nav').getByRole('button', {name: 'Overview'}).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('.metric').first().evaluate(n => getComputedStyle(n).animationName)).toBe('none');
});

test('authentication errors, skeleton, empty connected shop, server error, and disconnect', async ({page}) => {
  let allow = false, failure = false;
  await page.route('**/admin/workspace?*', async route => {
    if (!allow) return route.fulfill({status: 401, json: {detail: 'Unauthorized'}});
    await new Promise(resolve => setTimeout(resolve, 300));
    if (failure) return route.fulfill({status: 503, json: {detail: 'Unavailable'}});
    const now = Date.now() / 1000;
    return route.fulfill({json: {shop_name: '<script>unsafe</script>', generated_at: now, days: 7, summary: {orders: 0, order_value: 0, pending: 0, products: 0}, orders: [], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now - (6 - i) * 86400, value: 0})), automation: true, delivery_mode: 'dry_run', worker_age_seconds: null, failures: 0, queue: 0}});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('invalid-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await expect(page.getByRole('alert')).toContainText('wasn’t accepted');
  allow = true;
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await expect(page.getByText('Connected.', {exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Your next chapter starts here'})).toBeVisible();
  expect(await page.locator('script').count()).toBe(2);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('invalid-token');
  await page.getByRole('button', {name: 'Refresh workspace'}).click();
  await expect(page.locator('.skeleton-block').first()).toBeVisible();
  await expect(page.locator('#main')).toHaveAttribute('aria-busy', 'false');
  failure = true;
  await page.getByRole('button', {name: 'Refresh workspace'}).click();
  await expect(page.getByRole('heading', {name: 'We couldn’t refresh your workspace'})).toBeVisible();
  await page.getByRole('button', {name: 'Disconnect', exact: true}).click();
  await expect(page.getByText('Preview mode.')).toBeVisible();
});

test('connected writes retain idempotency on retry and dark detail views stay accessible', async ({page}) => {
  const now = Date.now() / 1000;
  const order = {id: 'live-order', code: 'TB-TEST', name: 'Test Customer', total_minor: 50000, status: 'pending', payment_status: 'unpaid', version: 9, created_at: now, item_count: 1, details: {name: 'Test Customer', payment: 'cod', delivery: 'pickup'}, shipping_minor: 0, items: [{sku: 'ITEM-1', name: 'Test item', qty: 1, price_minor: 50000}]};
  const product = {sku: 'ITEM-1', name: 'Test item', stock: 2, price_minor: 50000, active: true};
  const statusWrites = [], stockWrites = [];
  await page.route('**/admin/**', async route => {
    expect(route.request().headers().authorization).toBe('Bearer browser-test-token');
    const path = new URL(route.request().url()).pathname;
    if (path === '/admin/workspace') return route.fulfill({json: {shop_name: 'Connected test shop', generated_at: now, summary: {orders: 1, order_value: 50000, pending: order.status === 'pending' ? 1 : 0, products: 1}, orders: [order], products: [product], series: Array.from({length: 7}, (_, i) => ({timestamp: now - (6 - i) * 86400, value: i === 6 ? 50000 : 0})), automation: true, delivery_mode: 'dry_run', worker_age_seconds: 3, failures: 0, queue: 0}});
    if (path === '/admin/workspace/orders/live-order') return route.fulfill({json: order});
    if (path === '/admin/order-status') {
      statusWrites.push(route.request().postDataJSON());
      if (statusWrites.length === 1) return route.fulfill({status: 503, json: {detail: 'Temporary failure'}});
      order.status = 'confirmed'; order.version = 10;
      return route.fulfill({json: {order_id: order.id, status: 'confirmed', version: 10}});
    }
    if (path === '/admin/stock') {
      stockWrites.push(route.request().postDataJSON());
      if (stockWrites.length === 1) return route.fulfill({status: 503, json: {detail: 'Temporary failure'}});
      product.stock += 5;
      return route.fulfill({json: {sku: product.sku, delta: 5, stock: product.stock}});
    }
    return route.abort();
  });
  await page.emulateMedia({colorScheme: 'dark'});
  await page.goto('/');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('browser-test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: 'Open order TB-TEST'}).click();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', {name: 'Confirm order', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('couldn’t complete');
  await page.getByRole('button', {name: 'Confirm order', exact: true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  expect(statusWrites).toHaveLength(2);
  expect(statusWrites[0]).toEqual(statusWrites[1]);
  expect(statusWrites[0]).toMatchObject({order_id: 'live-order', expected_version: 9, status: 'confirmed'});
  expect(statusWrites[0].command_id).toMatch(/^[a-f0-9-]{36}$/);
  await page.getByRole('button', {name: 'Inventory', exact: true}).click();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', {name: 'Adjust stock'}).click();
  await page.getByLabel('Units to add or remove').fill('5');
  await page.getByRole('button', {name: 'Save adjustment'}).click();
  await expect(page.getByRole('alert')).toContainText('couldn’t complete');
  await page.getByRole('button', {name: 'Save adjustment'}).click();
  await expect(page.getByText('7 available')).toBeVisible();
  expect(stockWrites).toHaveLength(2);
  expect(stockWrites[0]).toEqual(stockWrites[1]);
  await page.getByRole('button', {name: 'Automation', exact: true}).click();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
});

test('chart exploration, quick actions, and controllable ambient motion', async ({page}) => {
  await page.addInitScript(() => { const get = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function(type, ...args) { return type.startsWith('webgl') ? null : get.call(this, type, ...args); }; });
  await page.setViewportSize({width: 1440, height: 1000});
  await page.emulateMedia({reducedMotion: 'no-preference', colorScheme: 'light'});
  await page.goto('/');
  const slider = page.getByRole('slider', {name: 'Explore by day'});
  await slider.focus();
  await page.keyboard.press('Home');
  await expect(slider).toHaveValue('0');
  await expect(slider).toHaveAttribute('aria-valuetext', /₱/);
  const firstDay = await page.locator('#chart-date').textContent();
  await page.keyboard.press('End');
  await expect(slider).toHaveValue('6');
  expect(await page.locator('#chart-date').textContent()).not.toBe(firstDay);
  await page.getByRole('button', {name: 'Pause ambient motion'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'off');
  await expect(page.locator('.hero-scene canvas')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('button', {name: 'Play ambient motion'})).toHaveAttribute('aria-pressed', 'false');
  await page.getByRole('button', {name: 'Play ambient motion'}).click();
  await page.getByRole('heading', {name: 'A good day to grow.'}).scrollIntoViewIfNeeded();
  await expect(page.locator('.hero-scene')).not.toHaveClass(/scene-paused/);
  await page.getByRole('button', {name: 'Pause ambient motion'}).scrollIntoViewIfNeeded();
  await expect(page.locator('.hero-scene')).toHaveClass(/scene-paused/);
  await page.keyboard.press('Control+k');
  await expect(page.getByLabel('Find a quick action')).toBeFocused();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByLabel('Find a quick action').fill('not-an-action');
  await expect(page.getByText('No actions match.', {exact: false})).toBeVisible();
  await page.getByLabel('Find a quick action').fill('Restock');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('.product')).toHaveCount(2);
  await expect(page.getByRole('button', {name: 'Low stock', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await page.emulateMedia({reducedMotion: 'reduce'});
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'off');
  await expect(page.getByRole('button', {name: 'Ambient motion disabled by system preference'})).toBeDisabled();
});
