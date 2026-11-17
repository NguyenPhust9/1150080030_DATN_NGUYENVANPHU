// Local fixture only: first run tests/serve_room_walkthrough_preview.py.
// All movement uses the visible keyboard controls; scene state is read through
// the minimap's accessibility/debug attributes, never teleported or modified.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const base = 'http://127.0.0.1:8003';
const output = 'test-results/room-lofts';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let activeRoom = 'login';
const position = () => page.locator('#map-player').evaluate(element => ({
  x: Number(element.dataset.x), y: Number(element.dataset.y), z: Number(element.dataset.z),
  level: element.dataset.level, airborne: element.dataset.airborne === 'true',
}));

async function moveUntil(key, predicate, label, timeout = 20000) {
  await page.keyboard.down(key);
  try {
    await expect.poll(async () => predicate(await position()), {
      message: `${activeRoom}: ${label}`, timeout, intervals: [40],
    }).toBe(true);
  } finally {
    await page.keyboard.up(key);
  }
}

try {
  await page.goto(`${base}/phong/`);
  await page.locator('[name="username"]').fill('walkthrough-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  const rooms = [
    { number: 'A101', offsetX: 0 },
    { number: 'A102', offsetX: -3.6 },
  ];
  for (const room of rooms) {
    room.url = await page.getByRole('row')
      .filter({ has: page.getByRole('cell', { name: room.number, exact: true }) })
      .getByRole('link', { name: 'Tham quan 3D' }).getAttribute('href');
    expect(room.url).toMatch(/^\/phong\/[a-f0-9-]+\/tham-quan\/$/);
  }

  for (const room of rooms) {
    activeRoom = room.number;
    await page.goto(`${base}${room.url}`);
    await expect(page.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 30000 });
    await expect(page.locator('#tour-fallback')).toBeHidden();
    await page.locator('#tour-start').click();
    await expect(page.locator('#map-player')).toHaveAttribute('data-room', room.number);
    await expect(page.locator('#map-player')).toHaveAttribute('data-level', 'ground');

    // Walk around the inward-opening door before lining up at the stair foot.
    await moveUntil('w', state => state.z < -1.45, 'walk past the open door');
    await moveUntil('a', state => state.x - room.offsetX < -.59, 'pass the door on its left');
    await moveUntil('s', state => state.z > -.69, 'approach the stair from its front');
    await moveUntil('a', state => state.x - room.offsetX < -1.23, 'align with stair centre');
    const baseOfStair = await position();
    expect(baseOfStair.y).toBeCloseTo(0, 2);
    await moveUntil('w', state => state.level === 'stairs' && state.y > .45, 'start ascending stairs');
    const halfway = await position();
    expect(halfway.y).toBeGreaterThan(.45);
    expect(halfway.y).toBeLessThan(2.2);
    await page.screenshot({ path: `${output}/${room.number}-stairs.png` });

    await moveUntil('w', state => state.z < -3.22 && state.level === 'loft', 'reach the loft landing');
    const landing = await position();
    expect(landing.y).toBeGreaterThan(2.2);
    expect(landing.airborne).toBe(false);
    const loftY = landing.y;
    await moveUntil('d', state => state.x - room.offsetX > .4, 'walk across the loft');
    expect((await position()).y).toBeCloseTo(loftY, 2);
    await expect(page.locator('#map-player')).toHaveAttribute('data-level', 'loft');
    await page.screenshot({ path: `${output}/${room.number}-loft.png` });

    // A jump lands on this elevated floor, rather than falling to the ground.
    await page.keyboard.down('Space');
    try {
      await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
      await expect.poll(async () => (await position()).y, { intervals: [20] }).toBeGreaterThan(loftY + .1);
    } finally {
      await page.keyboard.up('Space');
    }
    await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
    expect((await position()).y).toBeCloseTo(loftY, 2);
    await expect(page.locator('#map-player')).toHaveAttribute('data-level', 'loft');

    if (room.number === 'A102') {
      // The low mattress remains solid while jumping: moving over its front
      // must not leave the avatar landing inside the furniture footprint.
      await page.keyboard.down('w');
      await page.keyboard.down('Space');
      try {
        await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'true');
        await expect(page.locator('#map-player')).toHaveAttribute('data-airborne', 'false');
        await page.waitForTimeout(300);
      } finally {
        await page.keyboard.up('Space');
        await page.keyboard.up('w');
      }
      const atBed = await position();
      expect(atBed.z).toBeLessThan(-3.4);
      expect(atBed.z).toBeGreaterThanOrEqual(-3.545);
      expect(atBed.y).toBeCloseTo(loftY, 2);
      expect(atBed.level).toBe('loft');
      await page.screenshot({ path: `${output}/${room.number}-bed-jump.png` });
      await moveUntil('s', state => state.z > -3.3, 'move clear of the mattress');
      console.log('A102 jumping into mattress remains outside its footprint', atBed);
    }

    // Walking toward the front guardrail cannot leave the elevated platform.
    await page.keyboard.down('s');
    try { await page.waitForTimeout(2200); }
    finally { await page.keyboard.up('s'); }
    const atRail = await position();
    expect(atRail.z).toBeGreaterThan(-3.4);
    expect(atRail.z).toBeLessThanOrEqual(-2.75);
    expect(atRail.y).toBeCloseTo(loftY, 2);
    expect(atRail.level).toBe('loft');
    await page.screenshot({ path: `${output}/${room.number}-rail.png` });

    // Approach the stair opening from inside the loft, then descend normally.
    await moveUntil('w', state => state.z < -3.24, 'back away from the rail');
    await moveUntil('a', state => state.x - room.offsetX < -1.23, 'return to stair opening');
    await moveUntil('s', state => state.level === 'stairs' && state.y < loftY - .25, 'start descending stairs');
    const descending = await position();
    expect(descending.y).toBeGreaterThan(0);
    await moveUntil('s', state => state.z > -1.02 && state.level === 'ground', 'return to ground floor');
    expect((await position()).y).toBeCloseTo(0, 2);
    expect((await position()).airborne).toBe(false);
    await page.screenshot({ path: `${output}/${room.number}-ground.png` });
    console.log(`${room.number}: stairs ascent, loft traversal, jump/landing, guardrail and descent passed`, {
      halfway, loft: landing, rail: atRail, ground: await position(),
    });
  }

  // The added stair instructions and start button remain reachable on phones,
  // including short landscape screens where the introduction must scroll.
  for (const [name, viewport] of [
    ['portrait', { width: 390, height: 844 }],
    ['landscape', { width: 667, height: 320 }],
  ]) {
    const mobileContext = await browser.newContext({ viewport, hasTouch: true, storageState: await context.storageState() });
    try {
      const mobile = await mobileContext.newPage();
      mobile.on('pageerror', error => errors.push(error.message));
      await mobile.goto(`${base}${rooms[0].url}`);
      await expect(mobile.locator('#tour-start')).toBeEnabled({ timeout: 30000 });
      await expect(mobile.locator('.intro-hint')).toContainText('W lên gác, S xuống');
      await mobile.locator('#tour-start').scrollIntoViewIfNeeded();
      const startBounds = await mobile.locator('#tour-start').boundingBox();
      expect(startBounds.y).toBeGreaterThanOrEqual(0);
      expect(startBounds.y + startBounds.height).toBeLessThanOrEqual(viewport.height);
      await mobile.screenshot({ path: `${output}/mobile-${name}-intro.png` });
      await mobile.locator('#tour-start').click();
      await mobile.locator('#tour-help').click();
      await expect(mobile.locator('#tour-help-dialog')).toBeVisible();
      await expect(mobile.locator('#tour-help-dialog p').first()).toContainText('W luôn đi lên và S luôn đi xuống');
      await mobile.locator('#tour-help-dialog p').first().scrollIntoViewIfNeeded();
      await mobile.screenshot({ path: `${output}/mobile-${name}-help.png` });
      await mobile.locator('#tour-help-dialog [data-close-dialog]').click();
      await expect(mobile.locator('#tour-help-dialog')).toBeHidden();
      console.log(`Mobile ${name}: stair introduction, start button and help instructions reachable.`);
    } finally {
      await mobileContext.close();
    }
  }
  expect(errors).toEqual([]);
  console.log('Both room lofts passed keyboard-only navigation and elevation checks.');
} catch (error) {
  await page.screenshot({ path: `${output}/${activeRoom}-failure.png` }).catch(() => {});
  console.log('Loft failure', activeRoom, await position().catch(() => null), 'page errors', errors);
  throw error;
} finally {
  await browser.close();
}
