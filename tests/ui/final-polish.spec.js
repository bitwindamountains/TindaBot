import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('mobile automation keeps status labels intact and gives delivery review its own row', async ({page}) => {
  await page.setViewportSize({width: 320, height: 740});
  await page.goto('/#automation');
  for (const badge of await page.locator('.setting-row > .badge').all()) {
    expect(await badge.evaluate(n => {
      const range = document.createRange(); range.selectNodeContents(n);
      return range.getClientRects().length;
    })).toBe(1);
  }
  const row = page.locator('.setting-row-action');
  const description = await row.locator('p').boundingBox();
  const action = await row.getByRole('button', {name: 'Review deliveries'}).boundingBox();
  expect(action.y).toBeGreaterThanOrEqual(description.y + description.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: 'docs/validation/final-automation-mobile.png', fullPage: true});
});

test('handover and recovery confirmations have readable tap targets in both themes', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/#automation');
  for (const theme of ['light', 'dark']) {
    if (theme === 'dark') await page.getByRole('button', {name: 'Switch to dark mode'}).click();
    for (const flow of ['handover', 'recovery']) {
      await page.getByRole('button', {name: flow === 'handover' ? /Customers needing help/ : 'Review deliveries'}).click();
      await page.getByRole('button', {name: flow === 'handover' ? 'Review resume' : 'Review retry'}).first().click();
      const label = page.locator('label.refund-confirm');
      const box = await label.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.width).toBeGreaterThanOrEqual(44);
      const text = await label.locator('span').boundingBox();
      const checkbox = await page.getByRole('checkbox').boundingBox();
      expect(text.x).toBeGreaterThan(checkbox.x + checkbox.width);
      await label.locator('span').click();
      await expect(page.getByRole('checkbox')).toBeChecked();
      await page.getByRole('checkbox').focus();
      await page.keyboard.press('Space');
      await expect(page.getByRole('checkbox')).not.toBeChecked();
      expect((await new AxeBuilder({page}).include('dialog').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
      if (theme === 'light' && flow === 'recovery') await page.screenshot({path: 'docs/validation/final-confirmation-mobile.png'});
      await page.getByRole('button', {name: 'Close dialog'}).click();
    }
  }
});

test('long customer names fit the queue and resume dialog at 320 pixels', async ({page}) => {
  await page.setViewportSize({width: 320, height: 740});
  const now = Date.now()/1000;
  await page.route('**/admin/**', route => route.fulfill({json: route.request().url().includes('/handovers') ? {conversations: [{psid: '200', name: 'W'.repeat(80), reason: 'customer', version: 1, last_customer_at: now}], next_cursor: null} : {shop_name: 'Test shop', generated_at: now, summary: {orders: 0, pending: 0, products: 0, order_value: 0}, orders: [], products: [], series: Array.from({length: 7}, (_,i) => ({timestamp: now-i*86400, value: 0})), automation: true, delivery_mode: 'dry_run', failures: 0, queue: 0, worker_age_seconds: 0, handover_count: 1}}));
  await page.goto('/#automation');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: /Customers needing help/}).click();
  await expect(page.getByRole('button', {name: 'Review resume'})).toBeVisible();
  expect(await page.locator('dialog').evaluate(n => n.scrollWidth <= n.clientWidth)).toBe(true);
  await page.getByRole('button', {name: 'Review resume'}).click();
  expect(await page.locator('dialog').evaluate(n => n.scrollWidth <= n.clientWidth)).toBe(true);
  await page.getByRole('checkbox').check();
  await expect(page.getByRole('button', {name: 'Resume bot', exact: true})).toBeInViewport();
});
