import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('delivery recovery confirms duplicate risk, keeps retries stable and paginates', async ({page}) => {
  const now = Date.now()/1000, commands = [];
  let resolved = false;
  const job = {id: 55, destination: 'messenger', status: 'uncertain', attempts: 3, created_at: now, revision: 'a'.repeat(64), error_code: 'meta_transport_unknown', guidance: 'Check the provider before retrying.'};
  await page.route('**/admin/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/resolve')) {
      commands.push(route.request().postDataJSON());
      if (commands.length === 1) return route.fulfill({status: 503, json: {detail: 'Temporary failure'}});
      resolved = true;
      return route.fulfill({json: {success: true}});
    }
    if (url.pathname.endsWith('/jobs')) return route.fulfill({json: {jobs: resolved ? [] : url.searchParams.has('before') ? [{...job, id: 4, status: 'failed'}] : [job], next_cursor: resolved || url.searchParams.has('before') ? null : 55}});
    return route.fulfill({json: {shop_name: 'Recovery shop', generated_at: now, summary: {orders: 0, order_value: 0, pending: 0, products: 0}, orders: [], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now-(6-i)*86400, value: 0})), automation: true, delivery_mode: 'dry_run', worker_age_seconds: 0, failures: resolved ? 0 : 2, queue: 0}});
  });
  await page.goto('/#automation');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();
  await page.getByRole('button', {name: 'Review deliveries'}).click();
  await page.getByRole('button', {name: 'Load earlier deliveries'}).click();
  await expect(page.getByRole('button', {name: 'Review retry'})).toHaveCount(2);
  await page.getByRole('button', {name: 'Review retry'}).first().click();
  await page.getByRole('button', {name: 'Queue retry'}).click();
  expect(commands).toHaveLength(0);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: 'Queue retry'}).click();
  await expect(page.locator('#recovery-error')).not.toBeEmpty();
  await page.getByRole('button', {name: 'Queue retry'}).click();
  await expect(page.getByRole('heading', {name: 'No deliveries awaiting review.'})).toBeVisible();
  expect(commands).toHaveLength(2);
  expect(commands[0]).toEqual(commands[1]);
  expect(commands[0].accept_duplicate_risk).toBe(true);
});

test('sample recovery works on mobile and is accessible in both themes', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/#automation');
  for (const theme of ['light', 'dark']) {
    if (theme === 'dark') await page.getByRole('button', {name: 'Switch to dark mode'}).click();
    await page.getByRole('button', {name: 'Review deliveries'}).click();
    await expect(page.getByRole('button', {name: 'Review retry'})).toBeVisible();
    if (theme === 'light') await page.screenshot({path: 'docs/validation/workspace-recovery.png'});
    expect((await new AxeBuilder({page}).include('dialog').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole('button', {name: 'Suppress delivery'}).click();
    await page.getByRole('checkbox').check();
    await page.getByRole('button', {name: 'Confirm suppression'}).click();
    await expect(page.getByRole('heading', {name: 'No deliveries awaiting review.'})).toBeVisible();
    await page.getByRole('button', {name: 'Close dialog'}).click();
  }
});
