// Uses only the temporary SQLite fixture from serve_indoor_preview.py.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const origin = 'http://127.0.0.1:8001';
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jNuoAAAAASUVORK5CYII=', 'base64');
try {
  await page.goto(origin + '/khach-thue/them/');
  await page.locator('[name=username]').fill('indoor-preview');
  await page.locator('[name=password]').fill('local-preview-only');
  await page.locator('button[type=submit]').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('#id_full_name')).toHaveAttribute('required', '');
  for (const name of ['phone', 'email', 'identity_number', 'identity_front', 'identity_back']) {
    expect(await page.locator('#id_' + name).getAttribute('required')).toBeNull();
  }
  await expect(page.locator('#tenant-info')).toBeVisible();
  await expect(page.locator('#tenant-images')).toBeHidden();
  await expect(page.locator('#site-loading')).toHaveCSS('opacity', '0');
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: 'test-results/tenant-form-info.png', fullPage: true });
  await page.getByRole('tab', { name: 'Ảnh CCCD' }).click();
  await expect(page.locator('#tenant-images')).toBeVisible();
  await expect(page.locator('.tenant-image-status')).toHaveText('Ảnh CCCD không bắt buộc');
  await page.locator('#id_identity_front').setInputFiles({ name: 'front.png', mimeType: 'image/png', buffer: png });
  await expect(page.locator('[data-side=front] img')).toBeVisible();
  await expect(page.locator('.tenant-image-status')).toContainText('1/2');
  await page.locator('#id_identity_back').setInputFiles({ name: 'back.png', mimeType: 'image/png', buffer: png });
  await expect(page.locator('.tenant-image-status')).toContainText('2/2');
  await page.screenshot({ path: 'test-results/tenant-form-images.png', fullPage: true });
  await page.locator('[data-side=front] .tenant-clear-selection').click();
  await page.locator('[data-side=back] .tenant-clear-selection').click();
  await expect(page.locator('.tenant-image-status')).toHaveText('Ảnh CCCD không bắt buộc');
  // Native required validation opens the information tab, rather than trapping focus.
  await page.locator('.tenant-submit').click();
  await expect(page.locator('#tenant-info')).toBeVisible();
  await page.locator('#id_full_name').fill('Khách thử form không CCCD');
  await page.locator('#id_occupation').fill('Sinh viên');
  await page.locator('.tenant-submit').click();
  await expect(page).toHaveURL(origin + '/khach-thue/');
  await expect(page.locator('table')).toContainText('Khách thử form không CCCD');
  // Create another blank identity to verify the database uniqueness behavior too.
  await page.goto(origin + '/khach-thue/them/');
  await page.locator('#id_full_name').fill('Khách thứ hai không CCCD');
  await page.locator('.tenant-submit').click();
  await expect(page).toHaveURL(origin + '/khach-thue/');
  await page.goto(origin + '/khach-thue/them/');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#site-loading')).toHaveCSS('opacity', '0');
  await page.getByRole('tab', { name: 'Ảnh CCCD' }).click();
  await expect(page.locator('[data-side=back]')).toBeVisible();
  expect(await page.locator('.tenant-dialog').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/tenant-form-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
  console.log('PASS: optional contacts/CCCD, tabs, previews, clear files, native validation, name-only submissions, multiple blank IDs and mobile layout');
} finally {
  await browser.close();
}
