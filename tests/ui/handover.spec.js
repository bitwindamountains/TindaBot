import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('sample handovers require confirmation and update the waiting count', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/#automation');
  await page.getByRole('button', {name: /Customers needing help/}).click();
  await expect(page.getByRole('heading', {name: 'Sofia Reyes'})).toBeVisible();
  await expect(page.getByRole('link', {name: /Open Page inbox/})).toHaveCount(0);
  expect((await new AxeBuilder({page}).include('dialog').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: 'docs/validation/workspace-handover.png'});
  await page.getByRole('button', {name: 'Review resume'}).first().click();
  await page.getByRole('button', {name: 'Resume bot', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Resume the bot for this customer?'})).toBeVisible();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: 'Resume bot', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Review resume'})).toHaveCount(1);
  await page.getByRole('button', {name: 'Close dialog'}).click();
  await expect(page.getByRole('button', {name: /Customers needing help/})).toContainText('1 tracked handovers');
  await page.getByRole('button', {name: 'Switch to dark mode'}).click();
  await page.getByRole('button', {name: /Customers needing help/}).click();
  expect((await new AxeBuilder({page}).include('dialog').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
});

test('connected handovers paginate, escape names and reject stale resume', async ({page}) => {
  const now = Date.now()/1000;
  let version = 2, resumed = false;
  const commands = [];
  const person = {psid: '200', name: '<img src=x onerror=alert(1)>', reason: 'stop', version, last_customer_at: now};
  await page.route('**/admin/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/pause')) {
      const body = route.request().postDataJSON(); commands.push(body);
      if (body.expected_version === 2) {version = 3; return route.fulfill({status: 409, json: {detail: 'Conversation changed'}});}
      resumed = true; return route.fulfill({json: {paused: false}});
    }
    if (url.pathname.endsWith('/handovers')) return route.fulfill({json: {conversations: resumed ? [] : url.searchParams.has('after') ? [{...person, psid: '201', name: 'Second customer'}] : [{...person, version}], next_cursor: resumed || url.searchParams.has('after') ? null : '100:200'}});
    return route.fulfill({json: {shop_name: 'Handover shop', generated_at: now, summary: {orders: 0, order_value: 0, pending: 0, products: 0}, orders: [], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now-(6-i)*86400, value: 0})), automation: false, delivery_mode: 'dry_run', worker_age_seconds: 0, failures: 0, queue: 0, handover_count: resumed ? 0 : 2}});
  });
  await page.goto('/#automation');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: /Customers needing help/}).click();
  await expect(page.getByRole('link', {name: /Open Page inbox/})).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(page.locator('dialog img')).toHaveCount(0);
  await page.getByRole('button', {name: 'Load more handovers'}).click();
  await expect(page.getByRole('button', {name: 'Review resume'})).toHaveCount(2);
  await page.getByRole('button', {name: 'Review resume'}).first().click();
  await page.getByLabel('The customer wants bot replies again, and I have handled their request.').check();
  await page.getByRole('button', {name: 'Resume bot', exact: true}).click();
  await expect(page.locator('#handover-error')).toContainText('refresh');
  await page.getByRole('button', {name: 'Keep paused'}).click();
  await page.getByRole('button', {name: 'Refresh handovers'}).click();
  await page.getByRole('button', {name: 'Review resume'}).click();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: 'Resume bot', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'No tracked handovers waiting.'})).toBeVisible();
  expect(commands).toEqual([{enabled: false, expected_version: 2}, {enabled: false, expected_version: 3}]);
});
