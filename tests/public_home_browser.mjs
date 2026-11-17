// Run tests/serve_public_home_preview.py first. This suite only uses localhost.
// Visual capture is separate so review rounds can be coordinated deliberately.
import { chromium, expect } from '@playwright/test';

const base = process.env.PUBLIC_HOME_PREVIEW_URL || 'http://127.0.0.1:8005';
if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname)) {
  throw new Error('The public-home browser suite requires an isolated loopback fixture.');
}
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const firstBuilding = 'Tòa nhà An Tâm';
const secondBuilding = 'Tòa nhà Bình An';
const log = message => console.log(`PASS ${message}`);

async function home() {
  await page.goto(`${base}/`);
  await expect(page.locator('.building-block')).toHaveCount(5);
}

async function noOverflow(label) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    page: document.documentElement.scrollWidth,
  }));
  expect(dimensions.page, `${label}: document must not scroll horizontally`).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function applyFilters() {
  await page.locator('#home-filters button[type="submit"]').click();
  await expect(page).toHaveURL(/\/phong-cho-thue\/\?/);
}

try {
  await home();
  await expect(page.locator('.room-card')).toHaveCount(35);
  await expect(page.locator('.room-card').filter({ hasText: /[ABCDE]401/ })).toHaveCount(0);
  await noOverflow('desktop');
  await expect(page.locator('.guest-search [name="q"]')).toBeVisible();
  await expect(page.locator('.guest-search [name="building"]')).toBeVisible();
  await expect(page.locator('.guest-search [name="min_price"]')).toBeVisible();
  await expect(page.locator('.guest-search [name="max_price"]')).toBeVisible();
  await expect(page.locator('.hero-assurance')).toBeVisible();
  const nav = page.locator('#public-nav');
  await expect(nav.locator('a[href="/"]')).toBeVisible();
  await expect(nav.locator('a[href="/phong-cho-thue/"]')).toBeVisible();
  await expect(nav.locator('a[href="/#gioi-thieu"]')).toBeVisible();
  await expect(nav.locator('a[href="#lien-he"]')).toBeVisible();
  await expect(page.locator('.login-cta')).toBeVisible();
  await expect(page.locator('.public-footer a[href^="tel:"]')).toHaveAttribute('href', 'tel:0902966704');
  await expect(page.locator('.public-footer a[href^="mailto:"]')).toHaveAttribute('href', 'mailto:1150080030@sv.hcmunre.edu.vn');
  log('all public sections, navigation, contact links and 35 available rooms retained');

  const carousel = page.locator('[data-room-carousel]').first();
  const track = carousel.locator('.compact-room-grid');
  const scroll = () => track.evaluate(element => element.scrollLeft);
  await expect(carousel.locator('[data-room-prev]')).toBeDisabled();
  await carousel.locator('[data-room-next]').click();
  await expect.poll(scroll).toBeGreaterThan(100);
  await carousel.locator('[data-room-prev]').click();
  await expect.poll(scroll).toBeLessThanOrEqual(1);
  await track.focus();
  await page.keyboard.press('End');
  await expect(carousel.locator('[data-room-next]')).toBeDisabled();
  await page.keyboard.press('Home');
  await expect.poll(scroll).toBeLessThanOrEqual(1);
  await page.keyboard.press('ArrowRight');
  await expect.poll(scroll).toBeGreaterThan(100);
  await page.keyboard.press('Home');
  await expect.poll(scroll).toBeLessThanOrEqual(1);
  const box = await track.boundingBox();
  const originalUrl = page.url();
  await page.mouse.move(box.x + box.width * .7, box.y + 80);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .25, box.y + 80, { steps: 12 });
  await page.mouse.up();
  await expect.poll(scroll).toBeGreaterThan(100);
  expect(page.url()).toBe(originalUrl);
  log('carousel next/previous, keyboard navigation and mouse dragging without unwanted room navigation');

  await home();
  const favorite = page.locator('[data-favorite-room]').first();
  const favoriteId = await favorite.getAttribute('data-favorite-room');
  await favorite.click();
  await expect(favorite).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#favorite-count')).toHaveText('1');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('ql_phong_favorites')))).toEqual([favoriteId]);
  await page.reload();
  await expect(page.locator('[data-favorite-room]').first()).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.favorite-link').click();
  await expect(page).toHaveURL(/favorites=1/);
  await expect(page.locator('.room-card')).toHaveCount(1);
  await page.locator('[data-favorite-room]').click();
  await expect(page.locator('#favorite-count')).toHaveText('0');
  await expect(page.locator('.room-grid .empty-state')).toBeVisible();
  log('favorites saved across reload, favorites page and removal');

  await home();
  await page.locator('.guest-search [name="q"]').fill('A104');
  await page.locator('.guest-search button[type="submit"]').click();
  await expect(page.locator('.room-card')).toHaveCount(1);
  await expect(page.locator('.room-body h3')).toHaveText('Phòng A104');
  await page.locator('.room-body h3 a').click();
  await expect(page).toHaveURL(/\/phong-cho-thue\/[0-9a-f-]+\/$/);
  await expect(page.locator('h1')).toContainText('A104');
  log('hero keyword search and room detail navigation');

  await home();
  await page.locator('.guest-search [name="building"]').selectOption({ label: firstBuilding });
  await page.locator('.guest-search [name="min_price"]').fill('2800000');
  await page.locator('.guest-search [name="max_price"]').fill('3000000');
  await page.locator('.guest-search button[type="submit"]').click();
  await expect(page.locator('.room-card')).toHaveCount(3);
  await expect(page.locator('.room-body h3')).toHaveText(['Phòng A102', 'Phòng A103', 'Phòng A104']);
  log('hero building and minimum/maximum price filtering');

  await home();
  await page.locator('#home-filters [name="district"]').selectOption('Quận 3');
  await page.locator('#home-filters input[name="building"]').filter({ visible: true }).first().check();
  await page.locator('#home-filters input[name="amenity"][value="Máy lạnh"]').check();
  await page.locator('#home-filters input[name="amenity"][value="Wi-Fi"]').check();
  await page.locator('#price-filter').fill('3000000');
  await expect(page.locator('#price-filter-value')).toHaveText('3.000.000 đ');
  await applyFilters();
  await expect(page.locator('.room-body h3')).toHaveText(['Phòng A102', 'Phòng A104']);
  expect(new URL(page.url()).searchParams.getAll('amenity')).toEqual(['Máy lạnh', 'Wi-Fi']);
  log('district, building, two amenities and price range combined');

  await home();
  await page.locator('#home-filters input[name="building"]').nth(0).check();
  await page.locator('#home-filters input[name="building"]').nth(1).check();
  await applyFilters();
  expect(new URL(page.url()).searchParams.getAll('building')).toEqual([firstBuilding, secondBuilding]);
  await expect(page.locator('.result-count strong')).toHaveText('20');
  await expect(page.locator('.room-card')).toHaveCount(12);
  await expect(page.locator('.pagination a').last()).toHaveAttribute('href', /page=2/);
  await page.locator('.pagination a').last().click();
  await expect(page.locator('.room-card')).toHaveCount(8);
  expect(new URL(page.url()).searchParams.getAll('building')).toEqual([firstBuilding, secondBuilding]);
  log('multiple-building selection and pagination preserve filters');

  await home();
  await page.locator('#home-sort').selectOption('price_asc');
  await expect(page).toHaveURL(/sort=price_asc/);
  const prices = await page.locator('.room-price strong').allTextContents();
  const amounts = prices.map(price => Number(price.replace(/\D/g, '')));
  expect(amounts).toEqual([...amounts].sort((left, right) => left - right));
  await home();
  await page.locator('#home-sort').selectOption('price_desc');
  await expect(page).toHaveURL(/sort=price_desc/);
  const descending = (await page.locator('.room-price strong').allTextContents()).map(price => Number(price.replace(/\D/g, '')));
  expect(descending).toEqual([...descending].sort((left, right) => right - left));
  log('homepage sorting routes to ascending/descending room results');

  await home();
  await page.locator('.view-building').first().click();
  await expect(page.locator('.result-count strong')).toHaveText('12');
  await expect(page.locator('.room-body h3')).toHaveText([
    'Phòng A101', 'Phòng A102', 'Phòng A103', 'Phòng A104', 'Phòng A105',
    'Phòng A201', 'Phòng A202', 'Phòng A203', 'Phòng A204', 'Phòng A205',
    'Phòng A301', 'Phòng A302',
  ]);
  log('view-all building link shows every available room');

  await home();
  await page.locator('.guest-search [name="building"]').selectOption({ label: firstBuilding });
  await page.locator('.guest-search [name="max_price"]').fill('3500500');
  expect(await page.locator('.guest-search [name="max_price"]').evaluate(input => input.validity.valid)).toBe(true);
  await page.locator('.guest-search button[type="submit"]').click();
  expect(new URL(page.url()).searchParams.get('max_price')).toBe('3500500');
  await expect(page.locator('.room-card')).toHaveCount(9);
  log('arbitrary whole-dong price submits without an unintended 1000-dong step restriction');

  const unavailablePhoto = '**/static/home-reference-A101/**';
  const abortPhoto = route => route.abort('failed');
  await page.route(unavailablePhoto, abortPhoto);
  await home();
  const failedCard = page.locator('.room-card').first();
  await expect(failedCard.locator('.room-cover')).toBeHidden();
  await expect(failedCard.locator('.home-photo-placeholder')).toHaveText('Ảnh đang cập nhật');
  await expect(page.locator('.home-room-preview .home-photo-placeholder')).toHaveText('Ảnh đang cập nhật');
  await expect(page.locator('.home-room-preview')).toHaveAttribute('href', /\/phong-cho-thue\/[0-9a-f-]+\/$/);
  await failedCard.locator('.room-photo-link').click();
  await expect(page.locator('h1')).toContainText('A101');
  await page.unroute(unavailablePhoto, abortPhoto);
  log('failed uploaded photos show fallback while room and hero links remain usable');

  await page.setViewportSize({ width: 390, height: 844 });
  await home();
  const mobileMenu = page.locator('#public-menu-toggle');
  await mobileMenu.click();
  await page.locator('#public-nav a').first().focus();
  await page.keyboard.press('Escape');
  await expect(page.locator('#public-nav')).toBeHidden();
  await expect(mobileMenu).toHaveAttribute('aria-expanded', 'false');
  await expect(mobileMenu).toBeFocused();
  const mobileFilter = page.locator('#home-filter-toggle');
  await mobileFilter.click();
  await page.locator('#home-filter-fields [name="district"]').focus();
  await page.keyboard.press('Escape');
  await expect(page.locator('#home-filter-fields')).toBeHidden();
  await expect(mobileFilter).toHaveAttribute('aria-expanded', 'false');
  await expect(mobileFilter).toBeFocused();
  log('Escape closes mobile menu/filter and returns keyboard focus to their buttons');

  for (const width of [320, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await home();
    await noOverflow(`${width}px homepage`);
    const menu = page.locator('#public-menu-toggle');
    if (await menu.isVisible()) {
      await menu.click();
      await expect(menu).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('#public-nav a').first()).toBeVisible();
      await noOverflow(`${width}px open menu`);
      await menu.click();
      await expect(menu).toHaveAttribute('aria-expanded', 'false');
    }
    const toggle = page.locator('#home-filter-toggle');
    if (await toggle.isVisible()) {
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('#home-filter-fields [name="district"]')).toBeVisible();
      await noOverflow(`${width}px open filters`);
      await page.locator('#home-filters [name="district"]').selectOption('Bình Thạnh');
      await applyFilters();
      await expect(page.locator('.result-count strong')).toHaveText('8');
      await noOverflow(`${width}px filtered results`);
    }
    log(`responsive layout, menu and filter interaction at ${width}px`);
  }

  await page.setViewportSize({ width: 1366, height: 600 });
  await home();
  await page.locator('#home-filters [name="district"]').selectOption('Quận 3');
  await applyFilters();
  await expect(page.locator('.result-count strong')).toHaveText('12');
  log('desktop filter submit remains reachable on a short 1366 x 600 laptop viewport');

  const noScriptContext = await browser.newContext({
    viewport: { width: 390, height: 844 }, javaScriptEnabled: false,
  });
  try {
    const noScriptPage = await noScriptContext.newPage();
    await noScriptPage.goto(`${base}/`);
    await expect(noScriptPage.locator('#site-loading')).toBeHidden();
    await expect(noScriptPage.locator('#public-nav')).toBeVisible();
    await expect(noScriptPage.locator('#home-filter-fields')).toBeVisible();
    await noScriptPage.locator('#public-nav a[href="/phong-cho-thue/"]').click();
    await expect(noScriptPage).toHaveURL(`${base}/phong-cho-thue/`);
    await noScriptPage.goto(`${base}/`);
    await noScriptPage.locator('#home-filters [name="district"]').selectOption('Bình Thạnh');
    await noScriptPage.locator('#home-filters button[type="submit"]').click();
    await expect(noScriptPage.locator('.result-count strong')).toHaveText('8');
    log('JavaScript disabled: navigation and visible filters work through normal links and GET form submission');
  } finally {
    await noScriptContext.close();
  }
  expect(errors).toEqual([]);
  log('no uncaught browser errors');
} finally {
  await context.close();
  await browser.close();
}
