import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('private notes and partial refunds stay in the order timeline; completion clears the queue', async ({page}) => {
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('/#orders');
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await page.getByLabel('Private note', {exact: true}).fill('Use the small gift bag.\nCustomer will collect after 3pm.');
  await page.getByRole('button', {name: 'Add note', exact: true}).click();
  await expect(page.locator('.activity-body')).toContainText('Use the small gift bag.');
  await expect(page.getByRole('button', {name: 'Previous order', exact: true})).toBeDisabled();
  await page.getByRole('button', {name: 'Verify payment…'}).click();
  await page.getByRole('button', {name: 'Yes, payment received'}).click();
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await page.getByRole('button', {name: 'Cancel order…'}).click();
  await page.getByRole('button', {name: 'Yes, cancel order'}).click();
  await page.getByLabel('Order date scope').selectOption('open');
  await page.getByLabel('Filter orders by payment').selectOption('refund_required');
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await page.getByRole('button', {name: 'Record external refund', exact: true}).click();
  await page.getByLabel('Amount refunded (PHP)').fill('100');
  await page.getByLabel('Refund reference', {exact: true}).fill('TRANSFER-001');
  await page.getByRole('button', {name: 'Save refund record'}).click();
  await expect(page.getByRole('dialog')).toContainText('Record an external refund');
  await page.getByRole('checkbox').check();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', {name: 'Save refund record'}).click();
  await expect(page.locator('.refund-amounts')).toContainText('₱960');
  await expect(page.locator('.activity-list')).toContainText('TRANSFER-001');
  await expect(page.locator('.activity-list')).toContainText('Private note');
  await page.locator('#activity-title').scrollIntoViewIfNeeded();
  await page.screenshot({path: 'docs/validation/workspace-journal.png'});
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', {name: 'Record external refund', exact: true}).click();
  await expect(page.getByLabel('Amount refunded (PHP)')).toHaveValue('960.00');
  await page.getByLabel('Refund reference', {exact: true}).fill('TRANSFER-002');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: 'Save refund record'}).click();
  await expect(page.getByRole('dialog')).toContainText('The full external refund has been recorded.');
  await expect(page.getByRole('button', {name: 'Record external refund', exact: true})).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', {name: 'No orders match just yet'})).toBeVisible();
  await page.getByLabel('Order date scope').selectOption('all');
  await page.getByLabel('Filter orders by payment').selectOption('refunded');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button', {name: 'Switch to dark mode'}).click();
  await page.setViewportSize({width: 390, height: 844});
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  expect(await page.getByRole('dialog').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
});

test('connected notes and refunds preserve command IDs on retry and safely render text', async ({page}) => {
  const now = Date.now() / 1000;
  const order = {id: 'journal-order', code: 'TB-JOURNAL', name: 'Test customer', status: 'cancelled', payment_status: 'refund_required', total_minor: 10000, shipping_minor: 0, version: 3, created_at: now - 86400, details: {name: 'Test customer', payment: 'gcash'}, items: [], activity: [], refunded_minor: 0};
  const notes = [], refunds = [];
  await page.route('**/admin/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/notes')) {
      notes.push(route.request().postDataJSON());
      if (notes.length === 1) return route.fulfill({status: 503, json: {detail: 'Temporary failure'}});
      order.version++;
      order.activity.unshift({id: 1, kind: 'note', actor: 'operator', created_at: now, occurred_at: now, body: notes[1].body, data: {}});
      return route.fulfill({json: {version: order.version}});
    }
    if (path.endsWith('/refunds')) {
      refunds.push(route.request().postDataJSON());
      if (refunds.length === 1) return route.fulfill({status: 503, json: {detail: 'Temporary failure'}});
      order.version++; order.payment_status = 'refunded'; order.refunded_minor = 10000;
      return route.fulfill({json: {version: order.version}});
    }
    if (path.includes('/orders/')) return route.fulfill({json: order});
    return route.fulfill({json: {shop_name: 'Test shop', generated_at: now, summary: {orders: 1, order_value: 0, pending: 0, products: 0}, orders: [order], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now - (6-i)*86400, value: 0})), automation: true, delivery_mode: 'dry_run', worker_age_seconds: 0, failures: 0, queue: 0}});
  });
  await page.goto('/#orders');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('journal-test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: 'Open order TB-JOURNAL'}).click();
  await page.getByLabel('Private note', {exact: true}).fill('<img src=x onerror="window.injected=true">');
  await page.getByRole('button', {name: 'Add note', exact: true}).click();
  await expect(page.locator('#note-error')).toContainText('couldn’t complete');
  await expect(page.getByLabel('Private note', {exact: true})).toHaveValue('<img src=x onerror="window.injected=true">');
  await page.getByRole('button', {name: 'Add note', exact: true}).click();
  await expect(page.locator('.activity-body')).toContainText('<img');
  expect(notes[0]).toEqual(notes[1]);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  await page.getByRole('button', {name: 'Record external refund', exact: true}).click();
  await page.getByLabel('Refund reference', {exact: true}).fill('MOCK-REFERENCE');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: 'Save refund record'}).click();
  await expect(page.locator('#refund-error')).toContainText('couldn’t complete');
  await page.getByRole('button', {name: 'Save refund record'}).click();
  await expect(page.locator('.refund-card')).toContainText('full external refund');
  expect(refunds[0]).toEqual(refunds[1]);
  expect(refunds[0]).toMatchObject({expected_version: 4, amount_minor: 10000, completed_at: null});
});
