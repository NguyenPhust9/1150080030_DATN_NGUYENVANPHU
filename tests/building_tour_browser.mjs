// Run tests/serve_room_walkthrough_preview.py --port 8006 first.
// All movement and navigation use visible controls; datasets only observe state.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.WALKTHROUGH_TEST_ORIGIN || 'http://127.0.0.1:8006';
const output = 'test-results/building-walkthrough';
const roomId = number => {
  const suffix = Number(number.slice(1));
  return `${number.toLowerCase()}0000-0000-4000-8000-${String(suffix < 200 ? suffix - 100 : suffix).padStart(12, '0')}`;
};
const tourUrl = number => `${origin}/phong/${roomId(number)}/tham-quan/`;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let stage = 'start';
const position = (target = page) => target.locator('#map-player').evaluate(marker => ({
  x: Number(marker.dataset.x), y: Number(marker.dataset.y), z: Number(marker.dataset.z),
  room: marker.dataset.room, floor: Number(marker.dataset.floor), level: marker.dataset.level,
  airborne: marker.dataset.airborne === 'true',
}));

async function login(target, number = 'A101', username = 'walkthrough-preview') {
  await target.goto(tourUrl(number));
  if (await target.locator('[name="username"]').count()) {
    await target.locator('[name="username"]').fill(username);
    await target.locator('[name="password"]').fill('local-preview-only');
    await target.locator('button[type="submit"]').click();
  }
}

async function ready(target = page) {
  await expect(target.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 60000 });
  await expect(target.locator('#tour-fallback')).toBeHidden();
  await target.locator('#tour-start').click();
}

async function moveUntil(key, predicate, label, timeout = 60000) {
  stage = label;
  if (predicate(await position())) return;
  await page.keyboard.down(key);
  try { await expect.poll(async () => predicate(await position()), { timeout, intervals: [50], message: label }).toBe(true); }
  finally { await page.keyboard.up(key); }
}

async function renderedFrames(target = page, frames = 5) {
  await target.evaluate(count => new Promise((resolve, reject) => {
    const deadline = setTimeout(() => reject(new Error('Render loop stopped')), 30000);
    const advance = () => --count <= 0 ? (clearTimeout(deadline), resolve()) : requestAnimationFrame(advance);
    requestAnimationFrame(advance);
  }), frames);
}

async function jumpAndLand(target = page, touch = false) {
  const before = await position(target);
  await target.evaluate(() => {
    const marker = document.getElementById('map-player');
    window.testJumpPeak = Number(marker.dataset.y);
    window.testJumpObserver = new MutationObserver(() => { window.testJumpPeak = Math.max(window.testJumpPeak, Number(marker.dataset.y)); });
    window.testJumpObserver.observe(marker, { attributes: true, attributeFilter: ['data-y'] });
  });
  try {
    if (touch) await target.locator('#tour-jump').tap();
    else await target.keyboard.down('Space');
    await expect.poll(() => target.evaluate(() => window.testJumpPeak), { timeout: 15000 }).toBeGreaterThan(before.y + .15);
    await expect(target.locator('#map-player')).toHaveAttribute('data-airborne', 'false', { timeout: 15000 });
    await renderedFrames(target);
    expect((await position(target)).y).toBeCloseTo(before.y, 2);
    expect((await position(target)).airborne).toBe(false);
  } finally {
    if (!touch) await target.keyboard.up('Space');
    await target.evaluate(() => window.testJumpObserver.disconnect());
  }
}

async function checkControls(target, viewport) {
  for (const selector of ['#tour-view', '#tour-jump', '#tour-map', '[data-move="KeyW"]', '[data-move="KeyS"]', '[data-move="KeyA"]', '[data-move="KeyD"]']) {
    const control = target.locator(selector);
    await expect(control).toBeVisible();
    const rect = await control.boundingBox();
    expect(rect.x).toBeGreaterThanOrEqual(0);
    expect(rect.y).toBeGreaterThanOrEqual(0);
    expect(rect.x + rect.width).toBeLessThanOrEqual(viewport.width);
    expect(rect.y + rect.height).toBeLessThanOrEqual(viewport.height);
    expect(await control.evaluate(button => {
      const box = button.getBoundingClientRect();
      return button.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
    })).toBe(true);
  }
  expect(await target.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
}

try {
  stage = 'initial building configuration';
  await login(page);
  await ready();
  const config = JSON.parse(await page.locator('#tour-config').textContent());
  expect(config.rooms).toHaveLength(25);
  expect(config.floors).toEqual([1, 2, 3, 4, 5]);
  expect(config.roomDetails.filter(room => room.profile !== 'generic').map(room => room.number)).toEqual(['A101', 'A102', 'A103', 'A104', 'A105']);
  expect(config.roomDetails.find(room => room.number === 'A303')).toMatchObject({ floor: 3, profile: 'generic', hasMedia: false });
  await page.screenshot({ path: `${output}/building-entry.png` });
  await jumpAndLand();
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');

  stage = 'building map and route to A303';
  await page.locator('#tour-map').click();
  await expect(page.locator('#tour-building-dialog')).toBeVisible();
  await expect(page.locator('.building-storey')).toHaveCount(5);
  await expect(page.locator('[data-building-room]')).toHaveCount(25);
  await expect(page.locator('[data-building-room="A101"]')).toHaveAttribute('data-status', 'occupied');
  await expect(page.locator('[data-building-room="A303"]')).toHaveAttribute('data-status', 'available');
  await page.locator('[data-building-room="A303"]').click();
  await expect(page.locator('#tour-building-dialog')).toContainText('A303');
  const paused = await position();
  await page.keyboard.down('w');
  await renderedFrames();
  await page.keyboard.up('w');
  expect(await position()).toEqual(paused);
  await page.screenshot({ path: `${output}/building-map-a303.png` });
  await page.locator('#building-route-start').click();
  await expect(page.locator('#tour-building-dialog')).toBeHidden();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-destination', 'A303');
  await expect(page.locator('#tour-route')).toContainText('A303');
  await page.keyboard.press('f');
  await expect(page.locator('#tour-elevator-dialog')).toBeHidden();
  await moveUntil('a', state => state.x < -17.8, 'walk along floor one to elevator');
  await expect(page.locator('#tour-elevator')).toBeVisible();
  await page.keyboard.press('f');
  await expect(page.locator('#tour-elevator-dialog')).toBeVisible();
  await expect(page.locator('[data-elevator-floor]')).toHaveCount(5);
  await page.locator('[data-elevator-floor="3"]').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-floor', '3', { timeout: 15000 });
  await expect(page.locator('#map-player')).toHaveAttribute('data-floor', '3');
  await expect(page.locator('#tour-floor-label')).toHaveText('Tầng 3');
  await expect(page.locator('#mini-floor-label')).toContainText('Tầng 3');
  await page.screenshot({ path: `${output}/floor-three-elevator.png` });
  await moveUntil('d', state => state.x > -6.7, 'walk floor-three corridor to A303');
  await moveUntil('w', state => state.z < -1.6, 'enter simulated room A303');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A303');
  await expect(page.locator('#tour-room-name')).toHaveText('Phòng A303');
  expect((await position()).level).toBe('ground');
  await jumpAndLand();
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  await page.screenshot({ path: `${output}/a303-simulated-interior.png` });
  await page.locator('#tour-media').click();
  await expect(page.locator('[data-room-media="A303"]')).toBeVisible();
  await expect(page.locator('[data-room-media="A303"]')).toContainText('chưa có ảnh hoặc video');
  await expect(page.locator('[data-room-media="A101"]')).toBeHidden();
  await page.locator('#tour-media-dialog [data-close-dialog]').click();
  await expect(page.locator('#tour-canvas')).toBeFocused();
  await moveUntil('s', state => state.z > 1.55, 'exit A303 to floor-three corridor');
  await moveUntil('a', state => state.x < -17.8, 'return to floor-three elevator');
  await page.locator('#tour-elevator').click();
  await page.locator('[data-elevator-floor="1"]').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-floor', '1', { timeout: 15000 });
  console.log('Five-floor map, target A303, physical elevator approach, floor travel and simulated interior passed.');

  stage = 'five original rooms and reference media remain available';
  for (const [number, x, photos] of [['A105', -13.85, 1], ['A104', -10.25, 2], ['A103', -6.65, 2], ['A102', -3.05, 2], ['A101', .55, 2]]) {
    await moveUntil('d', state => state.x > x - .05, `approach original ${number}`);
    await moveUntil('w', state => state.z < -1.55, `enter original ${number}`);
    await expect(page.locator('#tour-position')).toHaveText(`Bên trong phòng ${number}`);
    await page.locator('#tour-media').click();
    const gallery = page.locator(`[data-room-media="${number}"]`);
    await expect(gallery).toBeVisible();
    await expect(gallery.locator('img')).toHaveCount(photos);
    await expect(gallery.locator('video')).toHaveCount(1);
    await expect.poll(() => gallery.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)), { timeout: 15000 }).toBe(true);
    await gallery.locator('video').evaluate(video => { video.preload = 'metadata'; video.load(); });
    await expect.poll(() => gallery.locator('video').evaluate(video => video.readyState >= 1 && Number.isFinite(video.duration) && video.duration > 0), { timeout: 15000 }).toBe(true);
    await page.locator('#tour-media-dialog [data-close-dialog]').click();
    await moveUntil('s', state => state.z > 1.55, `exit original ${number}`);
  }
  console.log('All five original rooms still enterable with their own photos and playable video metadata.');

  for (const [orientation, viewport] of [
    ['portrait', { width: 390, height: 844 }], ['landscape', { width: 667, height: 320 }],
  ]) {
    stage = `mobile ${orientation}`;
    const mobileContext = await browser.newContext({ viewport, hasTouch: true, storageState: await context.storageState() });
    try {
      const mobile = await mobileContext.newPage();
      mobile.on('pageerror', error => errors.push(error.message));
      await mobile.goto(tourUrl('A303'));
      await ready(mobile);
      await checkControls(mobile, viewport);
      await mobile.locator('#tour-map').tap();
      await expect(mobile.locator('[data-building-room]')).toHaveCount(25);
      await mobile.locator('[data-building-room="A505"]').tap();
      await mobile.screenshot({ path: `${output}/map-mobile-${orientation}.png` });
      await mobile.locator('#building-route-start').tap();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-destination', 'A505');
      await mobile.locator('#tour-view').tap();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
      await jumpAndLand(mobile, true);
      const forward = await mobile.locator('[data-move="KeyW"]').boundingBox();
      const touch = await mobileContext.newCDPSession(mobile);
      await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: forward.x + forward.width / 2, y: forward.y + forward.height / 2 }] });
      try { await expect.poll(() => position(mobile).then(value => value.z), { timeout: 15000 }).toBeLessThan(2.1); }
      finally { await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await touch.detach(); }
      await mobile.screenshot({ path: `${output}/tour-mobile-${orientation}.png` });
    } finally { await mobileContext.close(); }
  }
  console.log('Mobile portrait/landscape map, target selection, touch walking, jumping and view switching passed.');

  stage = 'access isolation';
  const guest = await browser.newContext();
  expect((await guest.request.get(tourUrl('A303'), { maxRedirects: 0 })).status()).toBe(302);
  await guest.close();
  for (const [username, expectedCount, neighborStatus] of [
    ['walkthrough-tenant', 1, 404], ['walkthrough-staff', 25, 200],
  ]) {
    const roleContext = await browser.newContext();
    try {
      const rolePage = await roleContext.newPage();
      await login(rolePage, 'A101', username);
      await rolePage.locator('#tour-config').waitFor({ state: 'attached' });
      const roleConfig = JSON.parse(await rolePage.locator('#tour-config').textContent());
      expect(roleConfig.rooms).toHaveLength(expectedCount);
      expect((await roleContext.request.get(tourUrl('A303'))).status()).toBe(neighborStatus);
      if (username === 'walkthrough-tenant') {
        await ready(rolePage);
        await rolePage.locator('#tour-map').click();
        await expect(rolePage.locator('[data-building-room]')).toHaveCount(1);
        await expect(rolePage.locator('[data-building-room="A101"]')).toBeVisible();
      }
    } finally { await roleContext.close(); }
  }

  stage = 'WebGL unavailable fallback';
  const fallback = await context.newPage();
  await fallback.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return type.includes('webgl') ? null : getContext.call(this, type, ...args);
    };
  });
  await fallback.goto(tourUrl('A303'));
  await expect(fallback.locator('#tour-fallback')).toBeVisible();
  await fallback.close();
  console.log('Anonymous login guard, tenant/staff permissions and WebGL fallback passed.');

  expect(errors).toEqual([]);
  console.log('Building walkthrough browser checks passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.error('Building tour failure:', stage, await position().catch(() => null), errors);
  throw error;
} finally { await browser.close(); }
