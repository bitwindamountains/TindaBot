import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('automation leads with the self-serve summary and turns a missed question into an FAQ row', async ({page, context}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/#automation');
  await expect(page.getByRole('heading', {name: 'Today, TindaBot handled 44 of 52 conversations on its own.'})).toBeVisible();
  await expect(page.getByText('Questions TindaBot couldn’t answer')).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Operator checks'})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);

  await page.getByRole('button', {name: 'Add to FAQ: May size small pa po?'}).click();
  await expect(page.getByRole('dialog', {name: 'Teach TindaBot'})).toBeVisible();
  await expect(page.getByLabel('Keywords')).toHaveValue('may size small pa po');
  await expect(page.getByLabel('Answer')).toBeFocused();
  await page.getByRole('button', {name: 'Copy FAQ row'}).click();
  await expect(page.getByRole('alert')).toHaveText('Add at least one keyword and an answer.');
  await page.getByLabel('Keywords').fill('size small, small size');
  await page.getByLabel('Answer').fill('Yes po, small is in stock.\nTap Shop to order.');
  await page.getByRole('button', {name: 'Copy FAQ row'}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#toast')).toHaveText('FAQ row copied. Paste it into the FAQ tab of your Sheet.');
  // Two Sheet cells: keywords, then the answer on one line in the plain-text fallback.
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('size small, small size\tYes po, small is in stock. Tap Shop to order.');
});

test('automation insights stack cleanly on a phone', async ({page}) => {
  await page.setViewportSize({width: 320, height: 700});
  await page.goto('/#automation');
  await expect(page.getByRole('button', {name: 'Add to FAQ: Open po kayo Sunday?'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
});
