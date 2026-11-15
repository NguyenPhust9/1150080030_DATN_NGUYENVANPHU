// Run only against tests/serve_indoor_preview.py (isolated SQLite fixtures).
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
});
const context = await browser.newContext({ viewport: { width: 1536, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir('test-results', { recursive: true });

try {
  await page.goto('http://127.0.0.1:8001/');
  await expect(page.locator('.guest-hero')).toBeVisible();
  await expect(page.locator('.custom-hero, .public-brand')).toHaveCount(0);
  await expect(page.locator('link[href*="hero-banner.css"], link[href*="about.css"]')).toHaveCount(0);
  await expect(page.locator('.guest-hero')).toHaveCSS('height', '300px');
  await expect(page.locator('.guest-search [name="building"]')).toBeVisible();
  await expect(page.locator('.guest-search [name="min_price"]')).toBeVisible();
  await expect(page.locator('.guest-search [name="max_price"]')).toBeVisible();
  await expect(page.locator('.public-header')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(page.locator('.login-cta')).toHaveCSS('border-top-color', 'rgb(234, 88, 12)');
  await expect(page.locator('#site-loading')).toHaveCSS('opacity', '0');
  await page.screenshot({ path: 'test-results/local-home-desktop.png', fullPage: true });

  await page.locator('.guest-search [name="min_price"]').fill('3000000');
  await page.locator('.guest-search [name="max_price"]').fill('3500000');
  await page.locator('.guest-search button').click();
  await expect(page).toHaveURL(/min_price=3000000.*max_price=3500000/);
  await expect(page.locator('.public-header')).toBeVisible();
  await expect(page.locator('.room-card')).toHaveCount(5);

  await page.goto('http://127.0.0.1:8001/');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.guest-search button')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/local-home-mobile.png', fullPage: true });

  await page.setViewportSize({ width: 1536, height: 1000 });
  await page.locator('.login-cta').click();
  await expect(page.locator('.auth-brand img').first()).toHaveAttribute('src', /images\/anhlogo\.png/);
  await page.locator('[name="username"]').fill('indoor-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await expect(page.locator('.sidebar')).toBeVisible();
  await expect(page.locator('.sidebar .brand')).toHaveCount(0);
  const group = page.locator('.nav-group').first();
  const toggle = group.locator('.nav-group-toggle');
  await expect(group).toHaveClass(/is-open/);
  await toggle.click();
  await expect(group).not.toHaveClass(/is-open/);
  await toggle.click();
  await expect(group).toHaveClass(/is-open/);
  await page.screenshot({ path: 'test-results/local-dashboard.png', fullPage: true });

  expect(errors).toEqual([]);
  console.log('PASS: local orange design, desktop/mobile, search, login and collapsible sidebar');
} finally {
  await browser.close();
}
