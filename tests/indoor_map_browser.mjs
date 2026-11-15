// Run against tests/serve_indoor_preview.py only, never against live data.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
  args: ['--enable-unsafe-swiftshader'],
});
const context = await browser.newContext({ viewport: { width: 1536, height: 1000 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
await mkdir('test-results', { recursive: true });
try {
  await page.goto('http://127.0.0.1:8001/ban-do-trong-nha/');
  await page.locator('[name="username"]').fill('indoor-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await page.locator('a').filter({ hasText: 'Xem bản đồ →' }).click();
  await expect(page.locator('#map-status')).toContainText('Chọn phòng');
  await expect(page.locator('#map-fallback')).toBeHidden();
  await expect(page.locator('#map-directory button')).toHaveCount(7);
  await expect(page.locator('#site-loading')).toHaveCSS('opacity', '0');
  await page.screenshot({ path: 'test-results/indoor-3d.png', fullPage: true });

  await page.locator('#map-directory button').filter({ hasText: 'Phòng A01' }).click();
  await expect(page.locator('#route-destination')).toHaveText('Lối thoát Tây');
  await expect(page.locator('#route-steps')).toContainText('Cửa phòng A01');
  await page.screenshot({ path: 'test-results/indoor-route.png', fullPage: true });
  const initialCanvas = await page.locator('#indoor-map-3d').screenshot();
  await page.locator('[data-map-action="zoom-in"]').click();
  await expect.poll(async () => !(await page.locator('#indoor-map-3d').screenshot()).equals(initialCanvas)).toBe(true);
  await page.locator('[data-map-action="rotate"]').click();
  await page.locator('[data-map-action="reset"]').click();
  await page.locator('[data-map-view="2d"]').click();
  await expect(page.locator('[data-map-view="2d"]')).toHaveAttribute('aria-pressed', 'true');
  await page.screenshot({ path: 'test-results/indoor-2d.png', fullPage: true });
  await page.locator('[data-map-view="3d"]').click();
  await page.locator('#map-search').fill('f1-04');
  await expect(page.locator('#map-directory button')).toHaveCount(1);
  await page.locator('#map-search').fill('khong-ton-tai');
  await expect(page.locator('#map-directory-empty')).toBeVisible();
  await page.locator('#map-search').fill('');

  const end = page.locator('#end');
  await page.locator('#map-directory button').filter({ hasText: 'Phòng F1-04' }).click();
  await page.locator('#map-selection button').filter({ hasText: 'Đến đây' }).click();
  await expect(page.locator('#start option:checked')).toHaveText('Phòng A01');
  await expect(page.locator('#route-destination')).toHaveText('Phòng F1-04');
  await expect(page.locator('#route-steps')).toContainText('Cửa phòng F1-04');
  await end.selectOption('');
  await expect(page.locator('#route-destination')).toHaveText('Lối thoát Tây');
  await page.locator('.indoor-simulation summary').click();
  const west = page.locator('[data-hazard-form]').filter({ hasText: 'Lối thoát trái' });
  const east = page.locator('[data-hazard-form]').filter({ hasText: 'Lối thoát phải' });
  await west.locator('button').click();
  await expect(page.locator('#route-destination')).toHaveText('Lối thoát Đông');
  await expect(west.locator('button')).toHaveText('Bỏ chặn');
  await east.locator('button').click();
  await expect(page.locator('#route-destination')).toHaveText('Không có tuyến khả dụng');
  await expect(page.locator('#route-steps li')).toHaveCount(0);
  await west.locator('button').click();
  await expect(page.locator('#route-destination')).toHaveText('Lối thoát Tây');
  await east.locator('button').click();
  await page.locator('#map-show-graph').check();
  await page.locator('#map-show-graph').uncheck();
  await page.locator('.indoor-simulation summary').click();
  const mapUrl = page.url();
  await page.route('**/*format=json*', (route) => route.abort());
  await end.selectOption({ label: 'Phòng F1-04' });
  await expect(page.locator('#map-status')).toContainText('Không tải được tuyến đường');
  await expect(page.locator('#route-steps li')).toHaveCount(0);
  await page.unroute('**/*format=json*');
  await end.selectOption('');
  await expect(page.locator('#route-destination')).toHaveText('Lối thoát Tây');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/indoor-mobile.png', fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  expect(overflow).toBe(false);
  const fallback = await page.context().newPage();
  await fallback.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return type.includes('webgl') ? null : getContext.call(this, type, ...args);
    };
  });
  await fallback.goto(mapUrl);
  await expect(fallback.locator('#map-fallback')).toBeVisible();
  await expect(fallback.locator('#map-fallback svg rect')).toHaveCount(11);
  await expect(fallback.locator('#route-destination')).toHaveText('Lối thoát Tây');
  await fallback.close();
  expect(errors).toEqual([]);
  console.log('PASS: WebGL, room selection, door routes, zoom, rotate, 2D/3D, search, hazards, no-route state, network failure, mobile, no-WebGL fallback.');
} catch (error) {
  await page.screenshot({ path: 'test-results/indoor-failure.png', fullPage: true });
  console.error('Browser errors:', errors);
  throw error;
} finally {
  await browser.close();
}
