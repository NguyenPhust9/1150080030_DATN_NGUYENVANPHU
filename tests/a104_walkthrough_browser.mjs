// Run the isolated fixture in tests/serve_room_walkthrough_preview.py first.
// Controls drive every move; the public minimap marker is read, never changed.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.WALKTHROUGH_TEST_ORIGIN || 'http://127.0.0.1:8003';
const roomIds = {
  A103: 'a1030000-0000-4000-8000-000000000003',
  A104: 'a1040000-0000-4000-8000-000000000004',
};
const offset = -10.8;
const xAt = x => offset + x;
const output = 'test-results/a104-walkthrough';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let stage = 'start';
const position = () => page.locator('#map-player').evaluate(marker => ({
  x: Number(marker.dataset.x), y: Number(marker.dataset.y), z: Number(marker.dataset.z),
  room: marker.dataset.room, level: marker.dataset.level, airborne: marker.dataset.airborne === 'true',
}));

async function moveUntil(key, predicate, label, timeout = 45000) {
  stage = label;
  if (predicate(await position())) return;
  await page.keyboard.down(key);
  try {
    await expect.poll(async () => predicate(await position()), { message: label, timeout, intervals: [50] }).toBe(true);
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
  stage = `open ${number}`;
  await page.goto(`${origin}/phong/${roomIds[number]}/tham-quan/`);
  if (await page.locator('[name="username"]').count()) {
    await page.locator('[name="username"]').fill('walkthrough-preview');
    await page.locator('[name="password"]').fill('local-preview-only');
    await page.locator('button[type="submit"]').click();
  }
  await expect(page.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 45000 });
  await expect(page.locator('#tour-fallback')).toBeHidden();
  await page.locator('#tour-start').click();
  await expect(page.locator('#map-player')).toHaveAttribute('data-room', number);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
}

async function switchView(mode, keyboard = false) {
  const before = await position();
  if (keyboard) await page.keyboard.press('v');
  else await page.locator('#tour-view').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', mode);
  await expect(page.locator('#tour-view')).toHaveAttribute('aria-pressed', String(mode === 'first-person'));
  expect(await position()).toEqual(before);
}

async function jumpAndLand(floor, ceiling) {
  stage = `jump at ${floor}`;
  await page.evaluate(() => {
    const marker = document.getElementById('map-player');
    window.a104JumpSamples = [Number(marker.dataset.y)];
    window.a104JumpObserver = new MutationObserver(() => window.a104JumpSamples.push(Number(marker.dataset.y)));
    window.a104JumpObserver.observe(marker, { attributes: true, attributeFilter: ['data-y'] });
  });
  try {
    await page.keyboard.down('Space');
    await expect.poll(() => page.evaluate(() => Math.max(...window.a104JumpSamples)), { timeout: 15000, intervals: [30] }).toBeGreaterThan(floor + .15);
    await page.keyboard.down('Space');
    await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false', { timeout: 15000 });
    await holdFrames('Space', 5);
    expect((await position()).airborne).toBe(false);
    expect((await position()).y).toBeCloseTo(floor, 2);
    expect(await page.evaluate(() => Math.max(...window.a104JumpSamples)) + 1.4).toBeLessThanOrEqual(ceiling + .002);
  } finally {
    await page.keyboard.up('Space');
    await page.evaluate(() => window.a104JumpObserver.disconnect());
  }
}

try {
  await openRoom('A104');
  await expect(page.locator('#tour-room-name')).toHaveText('Phòng A104');
  await expect(page.locator('.connected-rooms')).toContainText('A105 ↔ A104 ↔ A103 ↔ A102 ↔ A101');
  expect((await position()).x).toBeCloseTo(xAt(.55), 3);
  expect((await position()).z).toBeCloseTo(2.4, 3);
  const map = await page.locator('#map-geometry').evaluate(group => {
    const labels = [...group.querySelectorAll('text')].filter(item => /^A10[1-5]$/.test(item.textContent));
    const sorted = labels.sort((a, b) => Number(a.getAttribute('x')) - Number(b.getAttribute('x')));
    const bounds = group.getBBox();
    return { rooms: sorted.map(item => item.textContent), x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  });
  expect(map.rooms).toEqual(['A105', 'A104', 'A103', 'A102', 'A101']);
  expect(map.x).toBeGreaterThanOrEqual(0);
  expect(map.x + map.width).toBeLessThanOrEqual(220);
  expect(map.y).toBeGreaterThanOrEqual(0);
  expect(map.y + map.height).toBeLessThanOrEqual(215);
  await page.screenshot({ path: `${output}/a104-entry.png` });
  await jumpAndLand(0, 4.1);
  await switchView('first-person');
  await page.locator('#tour-media').click();
  const gallery = page.locator('[data-room-media="A104"]');
  await expect(gallery).toBeVisible();
  await expect(gallery.locator('img')).toHaveCount(2);
  await expect(gallery.locator('video')).toHaveCount(1);
  await expect.poll(() => gallery.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)), { timeout: 15000 }).toBe(true);
  const paused = await position();
  await page.keyboard.press('v');
  await holdFrames('w', 5);
  expect(await position()).toEqual(paused);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  await page.locator('#tour-media-dialog [data-close-dialog]').click();
  await expect(page.locator('#tour-canvas')).toBeFocused();
  await moveUntil('w', state => state.z < -1.65, 'enter A104 past open door');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A104');
  await page.screenshot({ path: `${output}/a104-overview.png` });

  // The left stair is reached around the inward-opening door, from the front.
  await moveUntil('a', state => state.x < xAt(-.4), 'walk left around door');
  await moveUntil('s', state => state.z > -.5, 'approach stair foot');
  await moveUntil('a', state => state.x < xAt(-1.18), 'align with A104 stair');
  await moveUntil('w', state => state.level === 'stairs' && state.y > .5, 'climb A104 stair', 60000);
  expect((await position()).y).toBeLessThan(2.4);
  await page.screenshot({ path: `${output}/a104-stairs.png` });
  await moveUntil('w', state => state.level === 'loft' && state.z < -3.3, 'reach A104 loft', 60000);
  expect((await position()).y).toBeCloseTo(2.4, 2);
  await moveUntil('d', state => state.x > xAt(.1), 'walk across A104 loft');
  await page.screenshot({ path: `${output}/a104-loft.png` });
  await switchView('third-person', true);
  await page.screenshot({ path: `${output}/a104-third-person-loft.png` });
  await jumpAndLand(2.4, 4.5);
  await switchView('first-person', true);
  await moveUntil('s', state => state.z > -3.12, 'approach A104 rail');
  await holdFrames('s');
  expect((await position()).z).toBeLessThanOrEqual(-3.0);
  expect((await position()).level).toBe('loft');
  await moveUntil('a', state => state.x < xAt(-1.18), 'return to A104 stair opening');
  await moveUntil('s', state => state.level === 'ground', 'descend A104 stair', 60000);
  expect((await position()).y).toBe(0);
  expect((await position()).z).toBeGreaterThanOrEqual(-.50);
  console.log('A104: both views, Space, stair ascent/descent, loft and rail passed.');

  await moveUntil('d', state => state.x > xAt(-.46), 'leave stair foot');
  await moveUntil('w', state => state.z < -1.45, 'pass door on return');
  await moveUntil('d', state => state.x > xAt(.5), 'return to central aisle');
  await moveUntil('w', state => state.z < -3.35, 'walk downstairs under loft');
  expect((await position()).y).toBe(0);
  expect((await position()).level).toBe('ground');
  await jumpAndLand(0, 2.2);
  await moveUntil('a', state => state.x < xAt(-.65), 'approach refrigerator from side');
  await holdFrames('a');
  expect((await position()).x).toBeGreaterThanOrEqual(xAt(-.83));
  expect((await position()).y).toBe(0);
  await moveUntil('d', state => state.x > xAt(.5), 'leave refrigerator');
  await moveUntil('w', state => state.z < -4.45, 'view rear kitchen and vanity');
  await page.screenshot({ path: `${output}/a104-rear.png` });
  await moveUntil('w', state => state.z < -5.0, 'approach kitchen');
  await holdFrames('d');
  expect((await position()).x).toBeLessThanOrEqual(xAt(.86));
  await page.screenshot({ path: `${output}/a104-kitchen.png` });
  console.log('A104: under-loft headroom, refrigerator and kitchen collision passed.');

  await page.keyboard.press('r');
  await expect.poll(position).toMatchObject({ x: xAt(.55), y: 0, z: 2.4, room: 'A104', level: 'ground' });
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  const sharedUrl = page.url();
  await moveUntil('d', state => state.x > -6.7, 'walk next door to A103');
  await moveUntil('w', state => state.z < -.65, 'enter adjacent A103');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A103');
  expect(page.url()).toBe(sharedUrl);
  await moveUntil('s', state => state.z > 1.5, 'leave A103');
  await moveUntil('a', state => state.x < xAt(.6), 'walk back to A104');
  await moveUntil('w', state => state.z < -.65, 're-enter A104');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A104');
  expect(page.url()).toBe(sharedUrl);
  await expect(page.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
  console.log('A104: shared corridor to A103 and five-room minimap passed.');

  for (const [orientation, viewport] of [
    ['portrait', { width: 390, height: 844 }], ['landscape', { width: 667, height: 320 }],
  ]) {
    stage = `mobile ${orientation}`;
    const touchContext = await browser.newContext({ viewport, hasTouch: true, storageState: await context.storageState() });
    try {
      const mobile = await touchContext.newPage();
      mobile.on('pageerror', error => errors.push(error.message));
      await mobile.goto(`${origin}/phong/${roomIds.A104}/tham-quan/`);
      await expect(mobile.locator('#tour-start')).toBeEnabled({ timeout: 45000 });
      await mobile.locator('#tour-start').click();
      for (const selector of ['#tour-view', '#tour-jump', '[data-move="KeyW"]', '[data-move="KeyS"]']) {
        const control = mobile.locator(selector);
        await expect(control).toBeVisible();
        const box = await control.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
        expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
        expect(await control.evaluate(button => {
          const rect = button.getBoundingClientRect();
          return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
        })).toBe(true);
      }
      await mobile.locator('#tour-view').click();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'first-person');
      const forward = await mobile.locator('[data-move="KeyW"]').boundingBox();
      await mobile.mouse.move(forward.x + forward.width / 2, forward.y + forward.height / 2);
      await mobile.mouse.down();
      try {
        await expect.poll(() => mobile.locator('#map-player').getAttribute('data-z').then(Number), { timeout: 15000 }).toBeLessThan(2.1);
      } finally { await mobile.mouse.up(); }
      await mobile.evaluate(() => {
        const marker = document.getElementById('map-player');
        window.mobileJumpPeak = Number(marker.dataset.y);
        window.mobileJumpObserver = new MutationObserver(() => { window.mobileJumpPeak = Math.max(window.mobileJumpPeak, Number(marker.dataset.y)); });
        window.mobileJumpObserver.observe(marker, { attributes: true, attributeFilter: ['data-y'] });
      });
      await mobile.locator('#tour-jump').click();
      await expect.poll(() => mobile.evaluate(() => window.mobileJumpPeak), { timeout: 15000 }).toBeGreaterThan(.15);
      await expect(mobile.locator('#map-player')).toHaveAttribute('data-airborne', 'false', { timeout: 15000 });
      await mobile.evaluate(() => window.mobileJumpObserver.disconnect());
      expect(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      await mobile.screenshot({ path: `${output}/a104-mobile-${orientation}.png` });
      await mobile.locator('#tour-view').click();
      await expect(mobile.locator('#room-tour')).toHaveAttribute('data-view-mode', 'third-person');
    } finally { await touchContext.close(); }
  }
  expect(errors).toEqual([]);
  console.log('A104: local gallery, both camera modes, keyboard/touch movement and jump, loft, furniture, adjacent A103, full minimap and mobile layouts passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.error('A104 failure:', stage, await position().catch(() => null), 'page errors:', errors);
  throw error;
} finally { await browser.close(); }
