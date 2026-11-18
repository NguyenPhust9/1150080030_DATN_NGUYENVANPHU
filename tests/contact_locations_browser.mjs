// Run against the isolated tests/serve_public_home_preview.py fixture.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const base = 'http://127.0.0.1:8005';
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir('test-results', { recursive: true });

async function checkSelected(building) {
  await expect(page.locator('[aria-current="location"]')).toHaveAttribute('data-building-id', building.id);
  await expect(page.locator('#contact-map-name')).toHaveText(building.name);
  await expect(page.locator('#contact-map-address')).toHaveText(building.address);
  const mapQuery = building.address === '118 Nguyễn Thị Minh Khai, Quận 3, TP.HCM'
    ? 'Nguyễn Thị Minh Khai, Quận 3, TP.HCM' : building.address;
  expect(new URL(await page.locator('#contact-map').getAttribute('src')).searchParams.get('q')).toBe(mapQuery);
  expect(new URL(await page.locator('#contact-directions').getAttribute('href')).searchParams.get('destination')).toBe(mapQuery);
  expect(new URL(await page.locator('#contact-open-map').getAttribute('href')).searchParams.get('query')).toBe(mapQuery);
  expect(new URL(await page.locator('#contact-building-rooms').getAttribute('href'), base).searchParams.get('building')).toBe(building.name);
}

try {
  await page.goto(`${base}/lien-he/`, { waitUntil: 'domcontentloaded' });
  const buildings = await page.locator('[data-building-id]').evaluateAll(links => links.map(link => ({
    id: link.dataset.buildingId, name: link.dataset.buildingName, address: link.dataset.buildingAddress,
  })));
  expect(buildings).toHaveLength(5);
  await checkSelected(buildings[0]);
  await page.locator('#contact-map').scrollIntoViewIfNeeded();
  // Check the real map UI; Google may omit the street label from its place card.
  const mapBody = page.frameLocator('#contact-map').locator('body');
  await expect(mapBody).toContainText('Dữ liệu bản đồ', { timeout: 30000 });
  await expect(page.frameLocator('#contact-map').getByRole('region', { name: 'Bản đồ', exact: true })).toBeVisible();
  await page.locator('#contact-locations').screenshot({ path: 'test-results/contact-locations-desktop.png' });
  console.log('PASS real Google map loads for the first building query');

  for (const building of buildings.slice(1)) {
    await page.locator(`[data-building-id="${building.id}"]`).click();
    await checkSelected(building);
    expect(new URL(page.url()).searchParams.get('building')).toBe(building.id);
    await expect(page.locator('#site-loading')).toBeHidden();
  }
  await page.goBack();
  await checkSelected(buildings[3]);
  await page.goForward();
  await checkSelected(buildings[4]);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await checkSelected(buildings[4]);
  console.log('PASS five choices update map, directions, rooms and browser history');

  await page.locator('#contact-building-rooms').click();
  await expect(page.locator('.room-card')).toHaveCount(5);
  await expect(page.locator('.active-filters')).toContainText(buildings[4].name);
  console.log('PASS selected building links to its available rooms');

  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`${base}/lien-he/`, { waitUntil: 'domcontentloaded' });
    const dimensions = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(dimensions[0]).toBeLessThanOrEqual(dimensions[1] + 1);
    await page.locator(`[data-building-id="${buildings[1].id}"]`).click();
    await checkSelected(buildings[1]);
    if (width <= 800) await expect(page.locator('#contact-map-panel')).toBeFocused();
    if (width === 390) {
      await page.locator('#contact-map').scrollIntoViewIfNeeded();
      await expect(page.frameLocator('#contact-map').locator('body')).toContainText('Dữ liệu bản đồ', { timeout: 30000 });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.locator('#contact-locations').screenshot({ path: 'test-results/contact-locations-mobile.png' });
    }
  }
  console.log('PASS responsive layout and mobile map selection from 320px to 1440px');

  const plainContext = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  try {
    const plain = await plainContext.newPage();
    await plain.goto(`${base}/lien-he/`);
    await plain.locator(`[data-building-id="${buildings[2].id}"]`).click();
    await expect(plain.locator('#contact-map-name')).toHaveText(buildings[2].name);
    await expect(plain.locator('#contact-open-map')).toHaveAttribute('href', /maps\/search/);
  } finally {
    await plainContext.close();
  }
  console.log('PASS server navigation and external map links remain usable without JavaScript');

  await page.goto(base);
  await expect(page.getByText('Kéo ngang để xem thêm phòng', { exact: true })).toHaveCount(0);
  const carousel = page.locator('[data-room-carousel]').first();
  await carousel.locator('[data-room-next]').click();
  await expect.poll(() => carousel.locator('.compact-room-grid').evaluate(track => track.scrollLeft)).toBeGreaterThan(0);
  await carousel.locator('[data-room-prev]').click();
  await expect.poll(() => carousel.locator('.compact-room-grid').evaluate(track => track.scrollLeft)).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
  console.log('PASS carousel hint removed; navigation preserved; no uncaught browser errors');
} finally {
  await context.close();
  await browser.close();
}
