import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {readFileSync} from 'node:fs';

test('payment follow-up filters compose with status and export refund requirements', async ({page}) => {
  await page.goto('/#orders');
  await page.getByLabel('Filter orders by payment').selectOption('unpaid');
  await expect(page.locator('tbody tr')).toHaveCount(5);
  await page.getByRole('button', {name: 'Pending', exact: true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await page.getByRole('button', {name: 'Verify payment…'}).click();
  await page.getByRole('button', {name: 'Yes, payment received'}).click();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.getByLabel('Filter orders by payment').selectOption('paid');
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await page.getByRole('button', {name: 'Cancel order…'}).click();
  await page.getByRole('button', {name: 'Yes, cancel order'}).click();
  await expect(page.getByRole('heading', {name: 'No orders match just yet'})).toBeVisible();
  await page.getByRole('button', {name: 'Clear filters'}).click();
  await expect(page.getByLabel('Filter orders by payment')).toHaveValue('all');
  await page.getByLabel('Filter orders by payment').selectOption('refund_required');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).toContainText('refund required');
  const download = page.waitForEvent('download');
  await page.getByRole('button', {name: 'Export CSV'}).click();
  const csv = readFileSync(await (await download).path(), 'utf8');
  expect(csv).toContain('"Payment status"');
  expect(csv).toContain('"TB-1048"');
  expect(csv).toContain('"refund_required"');
  expect(csv.split('\r\n')).toHaveLength(2);
});

test('stock triage, adjustment preview, and out-of-stock handling', async ({page}) => {
  await page.goto('/#inventory');
  await page.getByLabel('Sort products').selectOption('stock');
  await expect(page.locator('.product').first()).toContainText('Slow morning candle');
  const mug = page.locator('.product').filter({hasText: 'Sunday ceramic mug'});
  await mug.getByRole('button', {name: 'Adjust stock'}).click();
  await page.getByRole('button', {name: 'Add 10', exact: true}).click();
  await expect(page.locator('#stock-preview')).toHaveText('4 available + 10 = 14 after adjustment');
  await expect(page.getByLabel('Units to add or remove')).toBeFocused();
  await page.getByLabel('Units to add or remove').fill('-5');
  await expect(page.locator('#stock-preview')).toContainText('more stock than is available');
  await page.getByLabel('Units to add or remove').fill('-4');
  await expect(page.locator('#stock-preview')).toHaveText('4 available - 4 = 0 after adjustment');
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', {name: 'Save adjustment'}).click();
  await page.getByRole('button', {name: 'Out of stock', exact: true}).click();
  await expect(page.locator('.product')).toHaveCount(1);
  await expect(page.locator('.product')).toContainText('Sunday ceramic mug');
  await page.getByRole('button', {name: 'Adjust stock'}).click();
  await expect(page.getByRole('button', {name: 'Remove 1', exact: true})).toBeDisabled();
  await page.keyboard.press('Escape');
  await page.getByRole('button', {name: 'Inactive', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'A little room on the shelf'})).toBeVisible();
});

test('connected diagnostics explain failures and older detail payloads do not break the drawer', async ({page}) => {
  const now = Date.now() / 1000;
  const order = {id: 'test-order', code: 'TB-CHECK', name: 'Test customer', total_minor: 10000, status: 'pending', payment_status: 'unpaid', version: 1, created_at: now, item_count: 1};
  await page.route('**/admin/**', route => {
    if (route.request().url().includes('/orders/')) return route.fulfill({json: {id: order.id, code: order.code, total_minor: 10000, status: 'pending', payment_status: 'unpaid', version: 1, shipping_minor: 0, details: {name: 'Test customer', payment: 'cod'}, items: []}});
    return route.fulfill({json: {shop_name: 'Test shop', generated_at: now, summary: {orders: 1, order_value: 10000, pending: 1, products: 0}, orders: [order], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now - (6-i) * 86400, value: 0})), automation: false, automation_locked: true, delivery_mode: 'dry_run', worker_age_seconds: 300, failures: 4, queue: 8, job_health: {inbox_failed: 1, delivery_failed: 1, delivery_uncertain: 2}}});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: 'Open order TB-CHECK'}).click();
  await expect(page.getByText('Placed date unavailable', {exact: false})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Confirm order', exact: true})).toBeEnabled();
  await page.keyboard.press('Escape');
  await page.getByRole('button', {name: 'Automation', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'A few things need a look.'})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Check the worker', exact: true})).toBeVisible();
  await expect(page.getByText('2 deliveries have an uncertain result.', {exact: false})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Server setting is off'})).toBeVisible();
  await expect(page.getByRole('switch', {name: 'Automated replies'})).toBeDisabled();
  for (const theme of ['light', 'dark']) {
    if (theme === 'dark') await page.getByRole('button', {name: 'Switch to dark mode'}).click();
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  }
});
