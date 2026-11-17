// Local fixture only: first run tests/serve_room_walkthrough_preview.py.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const output = 'test-results/shared-room-walkthrough';
await mkdir(output, { recursive: true });
const position = async () => page.locator('#map-player').evaluate(el => ({ x: Number(el.dataset.x), z: Number(el.dataset.z) }));
async function moveUntil(key, predicate, timeout = 20000) {
  await page.keyboard.down(key);
  try { await expect.poll(async () => predicate(await position()), { timeout, intervals: [50] }).toBe(true); }
  finally { await page.keyboard.up(key); }
}
try {
  await page.goto('http://127.0.0.1:8003/phong/');
  await page.locator('[name="username"]').fill('walkthrough-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'A101', exact: true }) }).getByRole('link', { name: 'Tham quan 3D' }).click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 30000 });
  await expect(page.locator('#tour-fallback')).toBeHidden();
  await page.screenshot({ path: `${output}/intro.png` });
  await page.locator('#tour-start').click();
  await page.screenshot({ path: `${output}/outside.png` });
  // One held Space produces one jump, including repeated keydown events.
  await page.keyboard.down('Space');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
  await page.keyboard.down('Space');
  await expect.poll(async () => Number(await page.locator('#map-player').getAttribute('data-y')), { intervals: [30] }).toBeGreaterThan(.15);
  await page.screenshot({ path: `${output}/jump.png` });
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
  await page.waitForTimeout(800);
  await expect(page.locator('#map-player')).toHaveAttribute('data-y', '0.000');
  await page.keyboard.up('Space');
  await moveUntil('w', p => p.z < -1.6);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A101');
  await page.screenshot({ path: `${output}/inside.png` });
  console.log('Door entry', await position());
  await moveUntil('d', p => p.x > 1.2);
  await page.keyboard.down('d');
  await page.waitForTimeout(1200);
  await page.keyboard.up('d');
  expect((await position()).x).toBeLessThanOrEqual(1.401);
  await moveUntil('a', p => p.x < .6);
  await moveUntil('s', p => p.z > -1);
  await page.locator('#tour-help').click();
  const paused = await position();
  await page.keyboard.down('w');
  await page.waitForTimeout(500);
  await page.keyboard.up('w');
  expect(await position()).toEqual(paused);
  await page.locator('#tour-help-dialog [data-close-dialog]').click();
  await page.locator('#tour-media').click();
  await expect(page.locator('#tour-media-dialog')).toBeVisible();
  await page.locator('#tour-media-dialog [data-close-dialog]').click();
  await page.keyboard.press('r');
  await expect.poll(async () => (await position()).z).toBe(2.4);
  // Walk along the shared landing and enter A102 without loading another page.
  const tourUrl = page.url();
  await moveUntil('a', p => p.x < -2.98);
  await moveUntil('w', p => p.z < -3.5);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A102');
  await expect(page.locator('#tour-room-name')).toHaveText('Phòng A102');
  expect(page.url()).toBe(tourUrl);
  await page.screenshot({ path: `${output}/a102-inside.png` });
  await page.locator('#tour-media').click();
  await expect(page.locator('[data-room-media="A102"]')).toBeVisible();
  await expect(page.locator('[data-room-media="A101"]')).toBeHidden();
  await expect(page.locator('#media-title')).toContainText('A102');
  await page.locator('#tour-media-dialog [data-close-dialog]').click();
  await page.keyboard.press('Space');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
  await expect(page.locator('#map-player')).toHaveAttribute('data-y', '0.000');
  // The lower bathroom lintel also limits a jumping character's head.
  await moveUntil('a', p => p.x < -4.79);
  await moveUntil('w', p => p.z < -5.02);
  await page.evaluate(() => {
    const marker = document.getElementById('map-player');
    window.jumpPeak = 0;
    window.jumpObserver = new MutationObserver(() => { window.jumpPeak = Math.max(window.jumpPeak, Number(marker.dataset.y)); });
    window.jumpObserver.observe(marker, { attributes: true, attributeFilter: ['data-y'] });
  });
  await page.keyboard.press('Space');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
  const jumpPeak = await page.evaluate(() => { window.jumpObserver.disconnect(); return window.jumpPeak; });
  expect(jumpPeak).toBeGreaterThan(.2);
  expect(jumpPeak).toBeLessThanOrEqual(.601);
  await moveUntil('s', p => p.z > -3.8);
  await moveUntil('d', p => p.x > -3.1);
  // Walk back out and re-enter A101.
  await moveUntil('s', p => p.z > 1.5);
  await moveUntil('d', p => p.x > .5);
  await moveUntil('w', p => p.z < -.5);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A101');
  await page.keyboard.press('r');
  await moveUntil('w', p => p.z < -3.4);
  await page.screenshot({ path: `${output}/rear.png` });
  await page.keyboard.down('e');
  await page.waitForTimeout(1400);
  await page.keyboard.up('e');
  await page.screenshot({ path: `${output}/rotated.png` });
  const directionBeforeDrag = await page.locator('#map-player').getAttribute('transform');
  await page.mouse.move(720, 370);
  await page.mouse.down();
  await page.mouse.move(850, 370, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator('#map-player')).not.toHaveAttribute('transform', directionBeforeDrag);
  await page.keyboard.press('r');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${output}/mobile.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  const forward = page.locator('[data-move="KeyW"]');
  await page.locator('#tour-jump').click();
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
  await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
  const box = await forward.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  try { await expect.poll(async () => (await position()).z, { timeout: 12000 }).toBeLessThan(1.8); }
  finally { await page.mouse.up(); }
  await page.setViewportSize({ width: 667, height: 320 });
  await page.emulateMedia({ media: 'screen' });
  const touchContext = await browser.newContext({ viewport: { width: 667, height: 320 }, hasTouch: true, storageState: await context.storageState() });
  const landscape = await touchContext.newPage();
  await landscape.goto(page.url());
  await expect(landscape.locator('#tour-start')).toBeEnabled();
  await landscape.locator('#tour-start').click();
  const pad = await landscape.locator('.touch-controls').boundingBox();
  expect(pad.y + pad.height).toBeLessThanOrEqual(320);
  const jumpPad = await landscape.locator('#tour-jump').boundingBox();
  expect(jumpPad.y + jumpPad.height).toBeLessThanOrEqual(320);
  await landscape.screenshot({ path: `${output}/mobile-landscape.png` });
  await touchContext.close();
  // Starting directly from A102 selects its doorway, reset point and media.
  const direct = await context.newPage();
  await direct.goto('http://127.0.0.1:8003/phong/a1020000-0000-4000-8000-000000000002/tham-quan/');
  await expect(direct.locator('#tour-start')).toBeEnabled();
  await direct.locator('#tour-start').click();
  await expect(direct.locator('#map-player')).toHaveAttribute('data-room', 'A102');
  await expect(direct.locator('#map-player')).toHaveAttribute('data-x', '-3.050');
  await direct.close();
  const fallback = await context.newPage();
  await fallback.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return type.includes('webgl') ? null : original.call(this, type, ...args);
    };
  });
  await fallback.goto(page.url());
  await expect(fallback.locator('#tour-fallback')).toBeVisible();
  await fallback.close();
  expect(errors).toEqual([]);
  console.log('Shared A101/A102 walkthrough: both doors, corridor traversal, Space jump/landing/no repeat, room media, WASD, collision, pause, reset, camera, mobile controls and WebGL fallback passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.log('Position at failure', await position().catch(() => null), 'errors', errors);
  throw error;
} finally {
  await browser.close();
}
