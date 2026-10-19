import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('order update switches show the customer message and shipping asks for an optional note', async ({page}) => {
  await page.goto('/#automation');
  const shipped = page.getByRole('switch', {name: 'Message customers: Shipped or ready for pickup'});
  await expect(shipped).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByText('“Your order TB-1048 is on its way!”')).toBeVisible();
  await expect(page.getByText(/within 24 hours of the customer’s last message, so older conversations are skipped/)).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await shipped.click();
  await expect(shipped).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#toast')).toHaveText('Shipped or ready for pickup updates on.');

  await page.goto('/#orders');
  await page.getByRole('button', {name: 'Open order TB-1044'}).click();
  await page.getByRole('button', {name: 'Mark as shipped'}).click();
  await expect(page.getByLabel('Note for the customer (optional)')).toBeFocused();
  await page.getByLabel('Note for the customer (optional)').fill('J&T 1234');
  await page.getByRole('button', {name: 'Yes, mark as shipped'}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#toast')).toHaveText('Sample order TB-1044 is on its way. Update queued for the customer.');
});

test('with shipped updates off, marking as shipped stays one click', async ({page}) => {
  await page.goto('/#orders');
  await page.getByRole('button', {name: 'Open order TB-1044'}).click();
  await page.getByRole('button', {name: 'Mark as shipped'}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('#toast')).toHaveText('Sample order TB-1044 is on its way.');
});
