import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('preview explains that the test chat needs a connected shop', async ({page}) => {
  await page.goto('/#automation');
  await expect(page.getByRole('heading', {name: 'Talk to your bot'})).toBeVisible();
  await expect(page.getByText('The test chat uses your real catalog and FAQ')).toBeVisible();
});

test('test chat carries the bot state between messages and mirrors handover', async ({page}) => {
  const now = Date.now() / 1000, bodies = [];
  const snapshot = {shop_name: 'Test shop', generated_at: now, summary: {orders: 0, order_value: 0, pending: 0, products: 0}, orders: [], products: [], series: Array.from({length: 7}, (_, i) => ({timestamp: now - (6 - i) * 86400, value: 0})), automation: true, delivery_mode: 'dry_run', worker_age_seconds: 0, failures: 0, queue: 0, handover_count: 0};
  const card = {attachment: {type: 'template', payload: {template_type: 'generic', elements: [{title: 'Ube Cheese Pandesal', subtitle: 'PHP 180.00 · 25 available', buttons: [{type: 'postback', title: 'Add to cart', payload: 'PRODUCT:UBE-01'}]}]}}};
  await page.route('**/admin/**', route => {
    if (!route.request().url().includes('/test-chat')) return route.fulfill({json: snapshot});
    const body = route.request().postDataJSON();
    bodies.push(body);
    if (body.value === 'pa order po') return route.fulfill({json: {state: 'BROWSING', context: {step: 1}, replies: [card, {text: 'Pick something you like.', quick_replies: [{content_type: 'text', title: 'Checkout', payload: 'CHECKOUT'}]}], handed_over: false, catalog_fresh: true}});
    if (body.value === 'PRODUCT:UBE-01') return route.fulfill({json: {state: 'QTY', context: {step: 2}, replies: [{text: 'How many? Enter a number from 1 to 99.'}], handed_over: false, catalog_fresh: false}});
    return route.fulfill({json: {state: 'IDLE', context: {}, replies: [{text: 'The seller will take over here.'}], handed_over: true, catalog_fresh: true}});
  });
  await page.goto('/#automation');
  await page.getByRole('button', {name: 'Connect shop', exact: true}).click();
  await page.getByLabel('Operator token', {exact: true}).fill('test-token');
  await page.getByRole('button', {name: 'Connect workspace'}).click();

  const input = page.getByLabel('Message as a customer');
  await input.fill('pa order po');
  await page.getByRole('button', {name: 'Send'}).click();
  await expect(page.getByText('Ube Cheese Pandesal')).toBeVisible();
  await page.getByRole('button', {name: 'Add to cart'}).click();
  await expect(page.getByText('How many? Enter a number from 1 to 99.')).toBeVisible();
  await expect(page.getByText(/hasn’t synced from the Sheet in over an hour/)).toBeVisible();
  // The browser holds the conversation; each message carries the previous reply's state.
  expect(bodies[1]).toEqual({state: 'BROWSING', context: {step: 1}, value: 'PRODUCT:UBE-01'});
  await expect(input).toBeFocused();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);

  await input.fill('pakausap sa seller');
  await page.keyboard.press('Enter');
  await expect(page.getByText('you’d take over from here')).toBeVisible();
  await input.fill('hello?');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Send MENU to bring the bot back.')).toBeVisible();
  expect(bodies).toHaveLength(3);

  await page.getByRole('button', {name: 'Start over'}).click();
  await expect(page.getByText('Try a message your customers send')).toBeVisible();
});
