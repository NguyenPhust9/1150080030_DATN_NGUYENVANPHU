// Run tests/serve_room_walkthrough_preview.py --port 8006 first.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.WALKTHROUGH_TEST_ORIGIN || 'http://127.0.0.1:8006';
const output = 'test-results/building-enclosure';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const position = () => page.locator('#map-player').evaluate(marker => ({
  x: Number(marker.dataset.x), y: Number(marker.dataset.y), z: Number(marker.dataset.z), zone: marker.dataset.zone,
}));
async function move(key, predicate, label) {
  await page.keyboard.down(key);
  try { await expect.poll(async () => predicate(await position()), { timeout: 60000, intervals: [50], message: label }).toBe(true); }
  finally { await page.keyboard.up(key); }
}
async function frames(count = 6) {
  await page.evaluate(count => new Promise(resolve => {
    const next = () => --count ? requestAnimationFrame(next) : resolve(); requestAnimationFrame(next);
  }), count);
}
try {
  await page.goto(`${origin}/phong/a1050000-0000-4000-8000-000000000005/tham-quan/`);
  await page.locator('[name="username"]').fill('walkthrough-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-ready', 'true', { timeout: 60000 });
  await page.locator('#tour-start').click();
  await page.mouse.move(850, 430); await page.mouse.down();
  await page.mouse.move(850 - Math.PI / 2 / .005, 430, { steps: 12 }); await page.mouse.up();
  await frames();
  await page.screenshot({ path: `${output}/enclosed-corridor-a105.png` });
  await page.keyboard.press('r');
  await move('d', p => p.x >= -7.22, 'walk along unchanged corridor to the main entrance');
  await move('s', p => p.z > 11, 'exit through the entrance canopy into the courtyard');
  await expect(page.locator('#map-player')).toHaveAttribute('data-zone', 'outside');
  await expect(page.locator('#tour-position')).toHaveText('Lối đi ngoài sân · Cổng chính');
  await frames();
  await page.screenshot({ path: `${output}/building-main-entrance.png` });
  await move('s', p => p.z > 31.5, 'follow the garden path through the gate');
  const marker = page.locator('#map-player');
  expect(await marker.evaluate(el => {
    const box = el.getBoundingClientRect(), svg = el.closest('svg').getBoundingClientRect();
    return box.x >= svg.x && box.y >= svg.y && box.right <= svg.right && box.bottom <= svg.bottom;
  })).toBe(true);
  await page.locator('#tour-map').click();
  await page.locator('[data-building-room="A105"]').click();
  await page.locator('#building-route-start').click();
  await expect(page.locator('#room-tour')).toHaveAttribute('data-destination', 'A105');
  await page.screenshot({ path: `${output}/gate-to-building-route.png` });
  await move('w', p => p.z < 2.45, 'walk from the gate back into the enclosed hallway');
  await move('a', p => p.x <= -13.8, 'return to the original A105 door');
  await move('w', p => p.z < -1.5, 'enter the preserved room interior');
  await expect(page.locator('#tour-position')).toHaveText('Bên trong phòng A105');
  await page.keyboard.press('v');
  await frames();
  await page.screenshot({ path: `${output}/a105-interior-preserved.png` });
  await page.keyboard.press('r');
  expect((await position()).x).toBeCloseTo(-13.85, 2);
  expect((await position()).z).toBeCloseTo(2.4, 2);
  expect(errors).toEqual([]);
  console.log('Enclosed corridor, outside path, gate, map marker, routing, return to A105 and reset passed.');
} catch (error) {
  await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
  console.error('Enclosure browser failure', await position().catch(() => null), errors);
  throw error;
} finally { await browser.close(); }
