// Start tests/serve_room_walkthrough_preview.py --port 8006 before running.
// Uses visible controls; the mini-map only observes position and floor state.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.WALKTHROUGH_TEST_ORIGIN || 'http://127.0.0.1:8006';
const output = 'test-results/tour-landscape';
const roomId = number => {
  const suffix = Number(number.slice(1));
  return `${number.toLowerCase()}0000-0000-4000-8000-${String(suffix < 200 ? suffix - 100 : suffix).padStart(12, '0')}`;
};
const roomUrl = number => `${origin}/phong/${roomId(number)}/tham-quan/`;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let stage = 'start';
const position = (target = page) => target.locator('#map-player').evaluate(marker => ({
  x: Number(marker.dataset.x), y: Number(marker.dataset.y), z: Number(marker.dataset.z),
  floor: Number(marker.dataset.floor), room: marker.dataset.room, level: marker.dataset.level,
  rotation: Number(marker.getAttribute('transform').match(/rotate\(([-.\d]+)/)?.[1]),
}));

async function ready(target, number) {
  await target.goto(roomUrl(number));
  if (await target.locator('[name="username"]').count()) {
    await target.locator('[name="username"]').fill('walkthrough-preview');
    await target.locator('[name="password"]').fill('local-preview-only');
    await target.locator('button[type="submit"]').click();
  }
  await expect(target.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 60000 });
  await expect(target.locator('#tour-fallback')).toBeHidden();
  await target.locator('#tour-start').click();
}

async function frames(target = page, count = 6) {
  await target.evaluate(count => new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('The 3D render loop stopped')), 30000);
    const step = () => --count <= 0 ? (clearTimeout(timeout), resolve()) : requestAnimationFrame(step);
    requestAnimationFrame(step);
  }), count);
}

async function moveUntil(key, predicate, label) {
  stage = label;
  await page.keyboard.down(key);
  try { await expect.poll(async () => predicate(await position()), { timeout: 60000, intervals: [50], message: label }).toBe(true); }
  finally { await page.keyboard.up(key); }
}

async function dragLook(target, dx, dy = 0) {
  const viewport = target.viewportSize();
  // Several short swipes work on narrow screens without touching HUD buttons.
  const segments = Math.ceil(Math.abs(dx) / (viewport.width * .5));
  for (let i = 0; i < Math.max(1, segments); i++) {
    const partX = dx / Math.max(1, segments), partY = dy / Math.max(1, segments);
    const x = partX >= 0 ? viewport.width * .23 : viewport.width * .77;
    const y = viewport.height * .48;
    await target.mouse.move(x, y);
    await target.mouse.down();
    await target.mouse.move(x + partX, y + partY, { steps: 8 });
    await target.mouse.up();
  }
  await frames(target);
}

async function exterior(floor, pitch) {
  stage = `look outside from floor ${floor}`;
  const before = await position();
  await dragLook(page, Math.PI / .005, pitch / .004);
  expect((await position()).rotation).toBeCloseTo(180, 0);
  expect((await position()).x).toBe(before.x);
  expect((await position()).z).toBe(before.z);
  await expect(page.locator('#tour-model-note')).toContainText('Cảnh quan minh họa');
  await page.screenshot({ path: `${output}/floor-${floor}-exterior.png` });
  if (floor === 2) {
    await page.keyboard.press('v');
    await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
    await frames(page, 8);
    await page.screenshot({ path: `${output}/floor-2-third-person.png` });
    await page.keyboard.press('v');
    await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
    // Looking out toward +Z, the existing balcony limit must still hold.
    await moveUntil('w', state => state.z > 3.2, 'approach second-floor balcony rail');
    await page.keyboard.down('w');
    await frames(page, 12);
    await page.keyboard.up('w');
    expect((await position()).z).toBeLessThanOrEqual(3.351);
    expect((await position()).y).toBe(0);
    expect((await position()).level).toBe('ground');
  }
  await dragLook(page, -Math.PI / .005, -pitch / .004);
  if (floor === 2) await moveUntil('w', state => state.z < 2.45, 'return from balcony rail');
}

async function takeElevator(floor) {
  await moveUntil('a', state => state.x < -17.8, `walk to elevator for floor ${floor}`);
  await expect(page.locator('#tour-elevator')).toBeVisible();
  await page.keyboard.press('f');
  await expect(page.locator('[data-elevator-floor]')).toHaveCount(5);
  await page.locator(`[data-elevator-floor="${floor}"]`).click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-floor', String(floor), { timeout: 20000 });
  await expect(page.locator('#room-tour')).toHaveAttribute('data-traveling', 'false');
  await expect(page.locator('#tour-fallback')).toBeHidden();
  await moveUntil('d', state => state.x > -6.7, `leave elevator on floor ${floor}`);
}

try {
  await ready(page, 'A103');
  const config = JSON.parse(await page.locator('#tour-config').textContent());
  expect(config.rooms).toHaveLength(25);
  expect(config.roomDetails.filter(room => room.profile !== 'generic').map(room => room.number)).toEqual(['A101', 'A102', 'A103', 'A104', 'A105']);
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  await exterior(1, .08);
  console.log('Floor 1 exterior captured; first-person drag keeps avatar position.');

  await takeElevator(2);
  await exterior(2, .24);
  console.log('Floor 2 exterior captured; balcony collision still blocks leaving the building.');

  stage = 'select route to floor five';
  await page.keyboard.press('m');
  await expect(page.locator('[data-building-room]')).toHaveCount(25);
  await page.locator('[data-building-room="A503"]').click();
  await page.locator('#building-route-start').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-destination', 'A503');
  await takeElevator(5);
  await exterior(5, .5);
  await moveUntil('w', state => state.z < -1.55, 'enter A503 after viewing landscape');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A503');
  await expect(page.locator('#tour-model-note')).toContainText('Nội thất mô phỏng cơ bản');
  await expect(page.locator('#tour-route')).toContainText('A503');
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
  console.log('Floor 5 landscape, 1→2→5 elevator trips, building map, route and room entry passed.');

  stage = 'mobile exterior view';
  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, storageState: await context.storageState() });
  try {
    const mobile = await mobileContext.newPage();
    mobile.on('pageerror', error => errors.push(error.message));
    await ready(mobile, 'A203');
    await mobile.locator('#tour-view').tap();
    await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
    await dragLook(mobile, Math.PI / .005, .24 / .004);
    expect((await position(mobile)).rotation).toBeCloseTo(180, 0);
    expect(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await mobile.screenshot({ path: `${output}/mobile-floor-2-exterior.png` });
    for (const selector of ['#tour-map', '#tour-view', '#tour-jump', '[data-move="KeyW"]']) {
      expect(await mobile.locator(selector).evaluate(button => {
        const box = button.getBoundingClientRect();
        return button.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
      })).toBe(true);
    }
    await mobile.locator('#tour-map').tap();
    await expect(mobile.locator('[data-building-room]')).toHaveCount(25);
    await mobile.locator('#tour-building-dialog [data-close-dialog]').tap();
    await expect(mobile.locator('#tour-canvas')).toBeFocused();
  } finally { await mobileContext.close(); }
  expect(errors).toEqual([]);
  console.log('Mobile landscape view, touch controls, map/focus and zero JavaScript errors passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.error('Landscape QA failure:', stage, await position().catch(() => null), errors);
  throw error;
} finally { await browser.close(); }
