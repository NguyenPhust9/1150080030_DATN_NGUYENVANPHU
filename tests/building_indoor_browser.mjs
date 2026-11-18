// Local-only fixture: python tests/serve_indoor_preview.py (temporary SQLite).
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1536, height: 1050 }, deviceScaleFactor: 1 });
const page = await context.newPage(), errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir('test-results', { recursive: true });
try {
  await page.goto('http://127.0.0.1:8001/ban-do-trong-nha/');
  await page.locator('[name="username"]').fill('indoor-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await page.getByText('Xem bản đồ →').click();
  await expect(page.locator('#map-status')).toContainText('Chọn phòng', { timeout: 60000 });
  await expect(page.locator('[data-map-floor]')).toHaveCount(5);
  await expect(page.locator('#map-building-meta')).toHaveText('5 TẦNG · 25 PHÒNG');
  await expect(page.locator('#map-labels button')).toHaveCount(7);
  await expect(page.locator('#map-fallback')).toBeHidden();
  await page.screenshot({ path: 'test-results/building-map-floor1-3d.png', fullPage: true });

  const beforeZoom = await page.locator('#indoor-map-3d').screenshot();
  await page.locator('[data-map-action="zoom-in"]').click();
  await expect.poll(async () => !(await page.locator('#indoor-map-3d').screenshot()).equals(beforeZoom)).toBe(true);
  await page.locator('[data-map-action="rotate"]').click();
  await page.locator('[data-map-action="reset"]').click();
  await page.locator('#map-labels .is-lift').click();
  await expect(page.locator('.indoor-lift-floors button')).toHaveCount(5);
  await page.locator('.indoor-lift-floors button').getByText('Tầng 3', { exact: true }).click();
  await expect(page.locator('[data-map-floor="3"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('[data-map-floor="5"]').click();
  await expect(page.locator('#map-labels button')).toHaveCount(6);
  await expect(page.locator('#map-floor-description')).toHaveText('Tầng 5 · 5 phòng');
  await expect(page.locator('#map-directory')).toContainText('A505');

  await page.locator('#start').selectOption({ label: 'Phòng A101 · Tầng 1' });
  await page.locator('#end').selectOption({ label: 'Phòng A505 · Tầng 5' });
  await expect(page.locator('#route-destination')).toHaveText('Phòng A505');
  await expect(page.locator('#route-steps')).toContainText('tầng 1 → tầng 5');
  await page.locator('[data-map-view="2d"]').click();
  await expect(page.locator('[data-plan-room]')).toHaveCount(5);
  await expect(page.locator('[data-plan-lift="5"]')).toBeVisible();
  await page.screenshot({ path: 'test-results/building-map-floor5-2d.png', fullPage: true });
  await page.locator('[data-map-overview]').click();
  await expect(page.locator('.indoor-plan-card')).toHaveCount(5);
  await expect(page.locator('[data-plan-room]')).toHaveCount(25);
  await page.locator('[data-map-view="3d"]').click();
  await expect(page.locator('#map-labels .is-floor')).toHaveCount(5);
  await page.screenshot({ path: 'test-results/building-map-overview-3d.png', fullPage: true });

  await page.locator('#map-search').fill('a505');
  await expect(page.locator('#map-directory button')).toHaveCount(1);
  await page.locator('#map-directory button').click();
  await expect(page.locator('[data-map-floor="5"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#map-search').fill('');
  await page.locator('#start').selectOption({ label: 'Phòng A505 · Tầng 5' });
  await page.locator('#route-mode').selectOption('evacuation');
  await expect(page.locator('#route-distance')).toContainText('Không dùng thang máy');
  await expect(page.locator('#route-steps li')).toHaveCount(0);
  await page.locator('#route-mode').selectOption('visit');
  await page.locator('#start').selectOption({ label: 'Phòng A101 · Tầng 1' });
  await page.locator('#end').selectOption({ label: 'Phòng A505 · Tầng 5' });
  await expect(page.locator('#route-destination')).toHaveText('Phòng A505');
  await page.locator('[data-map-floor="1"]').click();
  await page.locator('.indoor-simulation summary').click();
  const zone = page.locator('.indoor-hazard-row').filter({ hasText: 'A101' });
  await zone.getByRole('button', { name: 'Chặn thử' }).click();
  await expect(page.locator('#route-destination')).toHaveText('Chưa có tuyến khả dụng');
  await zone.getByRole('button', { name: 'Bỏ chặn' }).click();
  await expect(page.locator('#route-destination')).toHaveText('Phòng A505');
  await page.locator('.indoor-simulation summary').click();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-map-view="2d"]').click();
  await expect(page.locator('[data-map-floor="5"]')).toBeVisible();
  await page.locator('[data-map-floor="5"]').click();
  await expect(page.locator('[data-plan-room="A505"]')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/building-map-mobile.png', fullPage: true });
  await page.reload();
  await expect(page.locator('[data-map-view="2d"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-map-floor="5"]')).toHaveAttribute('aria-pressed', 'true');

  await page.route('**/*format=json*', route => route.abort());
  await page.locator('#map-route-form button').click();
  await expect(page.locator('#map-status')).toContainText('Không kết nối');
  await expect(page.locator('#route-steps li')).toHaveCount(0);
  await page.unroute('**/*format=json*');
  await page.locator('#map-route-form button').click();
  await expect(page.locator('#route-destination')).toHaveText('Phòng A505');

  const fallback = await context.newPage();
  await fallback.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) { return /webgl/i.test(type) ? null : original.call(this, type, ...args); };
  });
  await fallback.goto(page.url().replace('&view=2d', ''));
  await expect(fallback.locator('#map-fallback')).toBeVisible();
  await expect(fallback.locator('[data-plan-room]')).toHaveCount(5);
  await expect(fallback.locator('#map-warnings')).toContainText('Bản đồ 2D');
  await fallback.close();
  expect(errors).toEqual([]);
  console.log('PASS: 5 floors / 25 rooms, 2D + 3D + overview, lift routes, evacuation, hazards, mobile, reload, network recovery, WebGL fallback.');
} catch (error) {
  await page.screenshot({ path: 'test-results/building-map-failure.png', fullPage: true });
  console.error('Browser errors:', errors);
  throw error;
} finally { await browser.close(); }
