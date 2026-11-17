// Local fixture only: run tests/serve_room_walkthrough_preview.py first.
// Exercises the rendered controls and exposed position marker, without changing
// scene internals, fixture data, or any deployed database.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.WALKTHROUGH_TEST_ORIGIN || 'http://127.0.0.1:8003';
const roomIds = {
  A101: 'a1010000-0000-4000-8000-000000000001',
  A102: 'a1020000-0000-4000-8000-000000000002',
  A103: 'a1030000-0000-4000-8000-000000000003',
};
const a103Offset = -7.2;
const a103X = localX => a103Offset + localX;
const output = 'test-results/a103-walkthrough';
const browser = await chromium.launch({
  channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir(output, { recursive: true });

const position = () => page.locator('#map-player').evaluate(marker => ({
  x: Number(marker.dataset.x), y: Number(marker.dataset.y), z: Number(marker.dataset.z),
  room: marker.dataset.room, level: marker.dataset.level, airborne: marker.dataset.airborne === 'true',
}));

async function moveUntil(key, predicate, timeout = 45000) {
  if (predicate(await position())) return;
  await page.keyboard.down(key);
  try {
    await expect.poll(async () => predicate(await position()), { timeout, intervals: [50] }).toBe(true);
  } finally {
    await page.keyboard.up(key);
  }
}

async function holdFrames(key, count = 18) {
  await page.keyboard.down(key);
  try {
    await page.evaluate(frames => new Promise((resolve, reject) => {
      let remaining = frames;
      const timeout = setTimeout(() => reject(new Error('Rendered frames stopped advancing')), 30000);
      function advance() {
        if (--remaining <= 0) { clearTimeout(timeout); resolve(); }
        else requestAnimationFrame(advance);
      }
      requestAnimationFrame(advance);
    }), count);
  } finally {
    await page.keyboard.up(key);
  }
}

async function openRoom(number) {
  await page.goto(`${origin}/phong/${roomIds[number]}/tham-quan/`);
  if (await page.locator('[name="username"]').count()) {
    await page.locator('[name="username"]').fill('walkthrough-preview');
    await page.locator('[name="password"]').fill('local-preview-only');
    await page.locator('button[type="submit"]').click();
  }
  await expect(page.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 45000 });
  await expect(page.locator('#tour-fallback')).toBeHidden();
  await page.keyboard.press('v');
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
  await page.locator('#tour-start').click();
  await expect(page.locator('#map-player')).toHaveAttribute('data-room', number);
}

async function switchView(mode, keyboard = false) {
  const before = await position();
  if (keyboard) await page.keyboard.press('v');
  else await page.locator('#tour-view').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', mode);
  const firstPerson = mode === 'first-person';
  await expect(page.locator('#tour-view')).toHaveAttribute('aria-pressed', String(firstPerson));
  await expect(page.locator('#tour-view')).toContainText(firstPerson ? 'Góc nhìn thứ ba' : 'Góc nhìn thứ nhất');
  expect(await position()).toEqual(before);
}

async function jumpAndLand({ floor, ceiling }) {
  await page.evaluate(() => {
    const marker = document.getElementById('map-player');
    window.a103JumpSamples = [Number(marker.dataset.y)];
    window.a103JumpObserver = new MutationObserver(() => {
      window.a103JumpSamples.push(Number(marker.dataset.y));
    });
    window.a103JumpObserver.observe(marker, { attributes: true, attributeFilter: ['data-y'] });
  });
  try {
    await page.keyboard.down('Space');
    await expect.poll(() => page.evaluate(() => Math.max(...window.a103JumpSamples)), { timeout: 10000, intervals: [30] }).toBeGreaterThan(floor + .15);
    await page.keyboard.down('Space'); // Repeated keydown must not create a second jump.
    await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false', { timeout: 15000 });
    await holdFrames('Space', 5);
    expect((await position()).airborne).toBe(false);
    expect((await position()).y).toBeCloseTo(floor, 2);
    const peak = await page.evaluate(() => Math.max(...window.a103JumpSamples));
    expect(peak).toBeGreaterThan(floor + .15);
    expect(peak + 1.4).toBeLessThanOrEqual(ceiling + .002);
    return peak;
  } finally {
    await page.keyboard.up('Space');
    await page.evaluate(() => window.a103JumpObserver.disconnect());
  }
}

try {
  await openRoom('A103');
  await expect(page.locator('#tour-room-name')).toHaveText('Phòng A103');
  expect((await position()).x).toBeCloseTo(a103X(.55), 3);
  expect((await position()).z).toBeCloseTo(2.4, 3);
  await page.screenshot({ path: `${output}/a103-entry.png` });
  await switchView('first-person');
  await page.screenshot({ path: `${output}/a103-first-person-entry.png` });
  await page.locator('#tour-media').click();
  const gallery = page.locator('[data-room-media="A103"]');
  await expect(gallery).toBeVisible();
  await expect(gallery.locator('img')).toHaveCount(2);
  await expect(gallery.locator('video')).toHaveCount(1);
  await expect(page.locator('[data-room-media="A101"]')).toBeHidden();
  await expect.poll(() => gallery.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)), { timeout: 15000 }).toBe(true);
  const pausedAtGallery = await position();
  await page.keyboard.press('v');
  await holdFrames('w', 5);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  expect(await position()).toEqual(pausedAtGallery);
  await page.locator('#tour-media-dialog [data-close-dialog]').click();
  await expect(page.locator('#tour-canvas')).toBeFocused();
  await jumpAndLand({ floor: 0, ceiling: 4.1 });
  await moveUntil('w', state => state.z < -.48);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A103');
  await page.screenshot({ path: `${output}/a103-ground.png` });
  await moveUntil('w', state => state.z < -1.65);
  await page.mouse.move(720, 370);
  await page.mouse.wheel(0, -900);
  await holdFrames('Shift', 10);
  await page.screenshot({ path: `${output}/a103-overview.png` });
  // Approach the actual stair foot from the doorway, passing the wardrobe.
  // Go around the open door leaf first, then back toward the stair foot.
  await moveUntil('a', state => state.x < a103X(-.4));
  await moveUntil('s', state => state.z > -.5);
  await moveUntil('a', state => state.x < a103X(-1.18));
  await moveUntil('w', state => state.level === 'loft', 60000);
  expect((await position()).y).toBeCloseTo(2.36, 2);
  await expect(page.locator('#tour-position')).toHaveText('Gác lửng · Phòng A103');
  await moveUntil('w', state => state.z < -3.3);
  await moveUntil('d', state => state.x > a103X(.1));
  await page.screenshot({ path: `${output}/a103-loft.png` });
  await switchView('third-person', true);
  await page.screenshot({ path: `${output}/a103-third-person-loft.png` });
  await switchView('first-person', true);
  await jumpAndLand({ floor: 2.36, ceiling: 4.4 });
  await moveUntil('s', state => state.z > -3.12);
  await holdFrames('s');
  expect((await position()).z).toBeLessThanOrEqual(-3.0);
  expect((await position()).level).toBe('loft');
  expect((await position()).y).toBeCloseTo(2.36, 2);
  await moveUntil('a', state => state.x < a103X(-1.18));
  await moveUntil('s', state => state.level === 'ground', 60000);
  expect((await position()).y).toBe(0);
  expect((await position()).z).toBeGreaterThanOrEqual(-.50);
  await moveUntil('d', state => state.x > a103X(-.46));
  await moveUntil('w', state => state.z < -1.45);
  await moveUntil('d', state => state.x > a103X(.50));
  await moveUntil('w', state => state.z < -3.4);
  expect((await position()).level).toBe('ground');
  expect((await position()).y).toBe(0);
  await page.screenshot({ path: `${output}/a103-rear.png` });
  // The photographed bathroom is accessible past the wardrobe, including the
  // wall-mounted heater and fittings; it must not be just a visible backdrop.
  await moveUntil('w', state => state.z < -4.55);
  await moveUntil('a', state => state.x < a103X(-1.06));
  await moveUntil('w', state => state.z < -5.42);
  expect((await position()).level).toBe('ground');
  expect((await position()).y).toBe(0);
  await page.screenshot({ path: `${output}/a103-bathroom.png` });
  const beforeLook = await position();
  const beforeDirection = await page.locator('#map-player').getAttribute('transform');
  await page.mouse.move(640, 340);
  await page.mouse.down();
  await page.mouse.move(790, 385, { steps: 8 });
  await page.mouse.up();
  await expect(page.locator('#map-player')).not.toHaveAttribute('transform', beforeDirection);
  expect(await position()).toEqual(beforeLook);
  await page.screenshot({ path: `${output}/a103-first-person-look.png` });
  await page.keyboard.press('r');
  await expect.poll(position).toMatchObject({ x: a103X(.55), y: 0, z: 2.4, room: 'A103', level: 'ground' });
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');

  // A103 is immediately to the left of A102 in the same corridor. Walking to
  // either doorway must not navigate or change the current camera mode.
  await openRoom('A102');
  await switchView('first-person');
  const sharedUrl = page.url();
  await moveUntil('a', state => state.x < a103X(.60));
  await moveUntil('w', state => state.z < -.65);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A103');
  expect(page.url()).toBe(sharedUrl);
  await moveUntil('s', state => state.z > 1.5);
  await moveUntil('d', state => state.x > -3.10);
  await moveUntil('w', state => state.z < -.65);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A102');
  expect(page.url()).toBe(sharedUrl);
  await moveUntil('s', state => state.z > 1.5);
  await moveUntil('d', state => state.x > .50);
  await moveUntil('w', state => state.z < -.65);
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A101');
  expect(page.url()).toBe(sharedUrl);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  await switchView('third-person');
  await page.locator('#tour-help').click();
  const pausedAtHelp = await position();
  await page.keyboard.press('v');
  await holdFrames('w', 5);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
  expect(await position()).toEqual(pausedAtHelp);
  await page.locator('#tour-help-dialog [data-close-dialog]').click();

  for (const [orientation, viewport] of [
    ['portrait', { width: 390, height: 844 }],
    ['landscape', { width: 667, height: 320 }],
  ]) {
    const touchContext = await browser.newContext({ viewport, hasTouch: true, storageState: await context.storageState() });
    try {
      const mobile = await touchContext.newPage();
      mobile.on('pageerror', error => errors.push(error.message));
      await mobile.goto(`${origin}/phong/${roomIds.A103}/tham-quan/`);
      await expect(mobile.locator('#tour-start')).toBeEnabled({ timeout: 45000 });
      await mobile.locator('#tour-start').click();
      const view = mobile.locator('#tour-view');
      await expect(view).toBeVisible();
      const box = await view.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
      expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
      // Wrapped portrait actions stay below the heading, not halfway down a
      // stretched full-height flex header where they cover the room itself.
      if (orientation === 'portrait') expect(box.y + box.height).toBeLessThan(180);
      expect(await view.evaluate(button => {
        const rect = button.getBoundingClientRect();
        return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
      })).toBe(true);
      await view.click();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
      expect(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      await mobile.screenshot({ path: `${output}/a103-first-person-mobile-${orientation}.png` });
      await view.click();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
    } finally {
      await touchContext.close();
    }
  }
  expect(errors).toEqual([]);
  console.log('A103 moved next to A102: direct entry, gallery, first/third-person button and V, Space, WASD, stairs, loft headroom/rail, bathroom, camera drag, reset, dialog pause, A103/A102/A101 corridor traversal and mobile view controls passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.error('A103 position at failure:', await position().catch(() => null), 'page errors:', errors);
  throw error;
} finally {
  await browser.close();
}
