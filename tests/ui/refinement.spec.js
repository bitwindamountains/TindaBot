import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('pipeline filters, scoped search, and sequential order review', async ({page}) => {
  await page.goto('/#orders');
  await page.getByRole('button', {name: 'To confirm: 3 orders', exact: true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await expect(page.getByRole('button', {name: 'Pending', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('searchbox').fill('Sofia');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button', {name: 'Clear search', exact: true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await expect(page.getByRole('searchbox')).toBeFocused();
  await page.getByRole('button', {name: 'Open order TB-1048'}).click();
  await expect(page.getByRole('button', {name: 'Previous order', exact: true})).toBeDisabled();
  await expect(page.locator('.order-journey [aria-current="step"]')).toContainText('Pending');
  await page.getByRole('button', {name: 'Next order', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'TB-1047', exact: true})).toBeVisible();
  await expect(page.getByText('Order 2 of 3 in this view')).toBeVisible();
  await page.getByRole('button', {name: 'Next order', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Next order', exact: true})).toBeDisabled();
  await page.getByRole('button', {name: 'Previous order', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'TB-1047', exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', {name: 'Open order TB-1048'})).toBeFocused();
  await page.getByRole('searchbox').fill('Sofia');
  await page.getByRole('button', {name: 'Inventory', exact: true}).click();
  await expect(page.getByRole('searchbox')).toHaveValue('');
  await expect(page.locator('.product')).toHaveCount(6);
});

test('mobile navigation stays reachable and order amounts fit without horizontal scrolling', async ({page}) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({width, height: 844});
    await page.goto('/#orders');
    await page.locator('.page-footer').scrollIntoViewIfNeeded();
    const nav = await page.locator('.nav').boundingBox();
    expect(nav.y).toBeGreaterThan(0);
    expect(nav.y + nav.height).toBeLessThanOrEqual(844);
    const tableFits = await page.locator('.table-scroll').evaluate(node => node.scrollWidth <= node.clientWidth);
    expect(tableFits).toBe(true);
    await expect(page.locator('.mobile-customer').first()).toBeVisible();
    await page.getByRole('button', {name: 'Inventory', exact: true}).click();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.getByRole('heading', {name: 'Good things in stock.'})).toBeVisible();
  }
});

test('order pipeline and fulfillment drawer remain accessible in both themes', async ({page}) => {
  for (const theme of ['light', 'dark']) {
    await page.emulateMedia({colorScheme: theme});
    await page.goto('/#orders');
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.getByRole('button', {name: 'Open order TB-1048'}).click();
    expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.keyboard.press('Escape');
  }
});
