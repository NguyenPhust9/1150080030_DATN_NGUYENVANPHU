// Run against tests/serve_admin_preview.py only. All fixture data lives in RAM.
// node tests/admin_design_browser.mjs
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = process.env.ADMIN_PREVIEW_ORIGIN || 'http://127.0.0.1:8005';
if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(origin).hostname)) {
  throw new Error('This test may only use an isolated local fixture.');
}
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1536, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const roomId = '00000000-0000-0000-0000-0000000003ed';
const contractId = '00000000-0000-0000-0000-000000007531';
const invoiceId = '00000000-0000-0000-0000-000000009ca4';
const originalDestinations = [
  ['Xem sơ đồ', '/so-do-phong/'], ['Tòa nhà', '/toa-nha/'], ['Phòng', '/phong/'],
  ['Khách thuê', '/khach-thue/'], ['Thống kê', '/quan-ly/'],
  ['Quản lý tài khoản', '/tai-khoan/'], ['Hợp đồng', '/hop-dong/'],
  ['Hóa đơn', '/hoa-don/'], ['Thanh toán', '/thanh-toan/'],
  ['Bản đồ trong nhà', '/ban-do-trong-nha/'], ['Gợi ý giá thuê', '/phong/'],
  ['Dịch vụ', '/dich-vu/'], ['Điện nước', '/chi-so/'], ['Giám sát cháy', '/giam-sat-chay/'],
  ['Sự cố', '/su-co/'], ['Thông báo', '/thong-bao/'],
  ['Ma trận quyền', '/tai-khoan/ma-tran-quyen/'],
  ['Lịch sử đăng nhập', '/tai-khoan/lich-su-dang-nhap/'],
  ['Hồ sơ cá nhân', '/ho-so/'], ['Đổi mật khẩu', '/doi-mat-khau/'],
];
const completed = [];

async function login(target, username = 'admin-preview') {
  await target.goto(`${origin}/dang-nhap/`);
  await target.locator('[name=username]').fill(username);
  await target.locator('[name=password]').fill('local-preview-only');
  await target.locator('button[type=submit]').click();
  await target.waitForURL(url => !url.pathname.includes('dang-nhap'));
}
async function noPageOverflow(target = page) {
  expect(await target.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
async function capture(label) {
  if (process.env.ADMIN_CAPTURE === '0') return;
  await expect(page.locator('#site-loading')).toHaveCSS('visibility', 'hidden');
  await expect(page.locator('#site-loading')).toHaveCSS('opacity', '0');
  await page.screenshot({ path: `test-results/admin-after-${label}.png`, fullPage: true });
}
function pass(label) { completed.push(label); console.log(`PASS: ${label}`); }

try {
  await mkdir('test-results', { recursive: true });
  await login(page);
  await page.goto(`${origin}/quan-ly/`);
  await expect(page.locator('body')).toHaveClass(/management-app/);
  for (const [label, href] of originalDestinations) {
    await expect(page.locator('.sidebar nav').getByRole('link', { name: label, exact: true })).toHaveAttribute('href', href);
  }
  for (const href of new Set(originalDestinations.map(([, href]) => href))) {
    const response = await context.request.get(origin + href);
    expect(response.status(), href).toBe(200);
  }
  await expect(page.locator('.topbar-alerts a[href="/thong-bao/"]')).toBeVisible();
  await expect(page.locator('.topbar-alerts a[href="/tro-chuyen/"]')).toBeVisible();
  await expect(page.locator('.topbar-alerts a[href="/thong-bao/"] b')).toHaveText('1');
  pass('All 20 original navigation links, permission destinations, alerts and chat remain');

  const stats = page.locator('.dashboard-stats-grid .stat');
  await expect(stats).toHaveCount(6);
  await expect(stats.nth(0)).toContainText('25');
  await expect(stats.nth(1)).toContainText('15');
  await expect(stats.nth(2)).toContainText('10');
  await expect(stats.nth(3)).toContainText('10');
  await expect(stats.nth(4)).toContainText('17.965.000');
  await expect(stats.nth(5)).toContainText('3');
  await expect(page.locator('.chart-month')).toHaveCount(6);
  await expect(page.locator('.chart-bar')).toHaveCount(12);
  const barHeights = await page.locator('.chart-bar').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().height));
  expect(barHeights.every(height => height > 40)).toBe(true);
  await expect(page.locator('.chart-summary')).toHaveCount(6);
  await expect(page.locator('.dashboard-panels .dashboard-table tbody tr')).toHaveCount(16);
  await expect(page.locator('.dashboard-panels a.table-code-link')).toHaveCount(16);
  await noPageOverflow();
  await capture('desktop');
  pass('Six live metrics, six chart months with both series, invoice/contract table data and links');

  const group = page.locator('.nav-group').first();
  const groupToggle = group.locator('.nav-group-toggle');
  await groupToggle.click();
  await expect(group).not.toHaveClass(/is-open/);
  await groupToggle.click();
  await expect(group).toHaveClass(/is-open/);
  const profile = page.locator('#userPopoverTrigger');
  const popover = page.locator('#userPopoverCard');
  await profile.click();
  await expect(profile).toHaveAttribute('aria-expanded', 'true');
  await expect(popover).toBeVisible();
  for (const href of ['/doi-mat-khau/', '/ho-so/', '/tai-khoan/lich-su-dang-nhap/']) {
    await expect(popover.locator(`a[href="${href}"]`)).toBeVisible();
  }
  await expect(popover.locator('form')).toHaveAttribute('method', 'post');
  await expect(popover.locator('input[name=csrfmiddlewaretoken]')).toHaveCount(1);
  await profile.focus();
  await page.keyboard.press('ArrowDown');
  await expect(popover.locator('a[href="/doi-mat-khau/"]')).toBeFocused();
  await page.keyboard.press('End');
  await expect(popover.locator('.user-popover-logout-btn')).toBeFocused();
  await page.keyboard.press('Home');
  await expect(popover.locator('a[href="/doi-mat-khau/"]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(profile).toHaveAttribute('aria-expanded', 'false');
  await expect(profile).toBeFocused();
  pass('Collapsible sections, account menu, Escape/focus return and CSRF-protected logout');

  await page.goto(`${origin}/toa-nha/`);
  await capture('buildings');
  await page.goto(`${origin}/so-do-phong/`);
  await capture('room-map');
  await page.goto(`${origin}/phong/${roomId}/goi-y-gia/`);
  await capture('price-suggestion');

  await page.goto(`${origin}/phong/`);
  await expect(page.locator('.pagination')).toBeVisible();
  await capture('rooms');
  await page.locator('.room-filters [name=q]').fill('A105');
  await page.locator('.room-filters button[type=submit]').click();
  await expect(page.locator('table tbody tr')).toHaveCount(1);
  await expect(page.locator('table tbody')).toContainText('A105');
  await expect(page.getByRole('link', { name: 'Tham quan 3D', exact: true })).toHaveAttribute('href', `/phong/${roomId}/tham-quan/`);
  await expect(page.getByRole('link', { name: 'Gợi ý giá', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Xóa lọc', exact: true }).click();
  await page.locator('.room-filters [name=building]').selectOption('00000000-0000-0000-0000-000000000001');
  await page.locator('.room-filters button[type=submit]').click();
  await expect(page.locator('table tbody tr')).toHaveCount(5);
  await page.goto(`${origin}/phong/${roomId}/sua/`);
  await expect(page.locator('#id_number')).toHaveValue('A105');
  await expect(page.locator('.room-form-tabs button')).toHaveCount(3);
  await expect(page.getByRole('link', { name: 'Tham quan 3D phòng A105' })).toBeVisible();
  await capture('room-form');
  await page.locator('[data-tab=images]').click();
  await expect(page.locator('[data-panel=images]')).toBeVisible();
  await expect(page.locator('[data-panel=images] .media-preview img').first()).toBeVisible();
  await expect(page.locator('[name=primary-choice]').first()).toBeVisible();
  await expect(page.locator('#room-images')).toHaveAttribute('multiple', '');
  await page.locator('[data-tab=videos]').click();
  await expect(page.locator('[data-panel=videos] video').first()).toBeVisible();
  await expect(page.locator('[data-panel=videos] [name=delete_media]').first()).toBeVisible();
  await expect(page.locator('#room-videos')).toHaveAttribute('accept', /video\/mp4/);
  await page.locator('[data-tab=info]').click();
  const description = await page.locator('#id_description').inputValue();
  await page.locator('#id_description').fill(`${description} Kiểm tra giao diện quản trị.`);
  await page.locator('#save-room').click();
  await expect(page).toHaveURL(`${origin}/phong/`);
  await page.goto(`${origin}/phong/${roomId}/sua/`);
  await expect(page.locator('#id_description')).toHaveValue(`${description} Kiểm tra giao diện quản trị.`);
  await page.locator('#id_description').fill(description);
  await page.locator('#save-room').click();
  pass('Room search/building filter/pagination, A105 tour/pricing, media tabs and persisted edit');

  await page.goto(`${origin}/hop-dong/`);
  await page.locator('.room-filters [name=status]').selectOption('active');
  await page.locator('.room-filters button[type=submit]').click();
  await expect(page.locator('table tbody tr')).toHaveCount(10);
  await page.goto(`${origin}/hop-dong/${contractId}/`);
  for (const action of ['gia-han', 'cham-dut', 'thanh-vien/them', 'dich-vu/them']) {
    await expect(page.locator(`form[action$="/${action}/"]`)).toHaveAttribute('method', 'post');
  }
  await page.goto(`${origin}/hoa-don/`);
  await expect(page.getByRole('link', { name: 'Lập hóa đơn hàng loạt' })).toBeVisible();
  await page.locator('.room-filters [name=status]').selectOption('overdue');
  await page.locator('.room-filters button[type=submit]').click();
  await expect(page.locator('table tbody tr')).toHaveCount(3);
  await page.goto(`${origin}/hoa-don/${invoiceId}/`);
  await expect(page.locator('a[href^="/thanh-toan/ghi-nhan/"]').first()).toBeVisible();
  await expect(page.locator('form[action$="/huy/"]').first()).toHaveAttribute('method', 'post');
  for (const route of ['/hop-dong/them/', '/hoa-don/them/', '/hoa-don/tao-hang-loat/', '/thanh-toan/ghi-nhan/']) {
    const response = await page.goto(origin + route);
    expect(response.status()).toBe(200);
    await expect(page.locator('main form[method=post]:not(.user-popover-logout-form)').first()).toBeVisible();
  }
  await page.goto(`${origin}/hop-dong/them/`);
  await capture('contract-form');
  pass('Contract/invoice filters, renew/terminate/member/service actions and billing/payment forms');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/quan-ly/`);
  const menuToggle = page.locator('#admin-menu-toggle');
  const sidebar = page.locator('#admin-sidebar');
  await expect(menuToggle).toBeVisible();
  await expect(menuToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(sidebar).toHaveAttribute('inert', '');
  await noPageOverflow();
  await capture('mobile');
  await menuToggle.click();
  await expect(menuToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(sidebar).not.toHaveAttribute('inert', '');
  await expect.poll(() => page.evaluate(() => document.querySelector('#admin-sidebar').contains(document.activeElement))).toBe(true);
  // Shift+Tab from the first control wraps to a focusable item in the drawer.
  await page.locator('#admin-menu-close').focus();
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => document.querySelector('#admin-sidebar').contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(menuToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(menuToggle).toBeFocused();
  await menuToggle.click();
  await page.locator('#admin-nav-backdrop').click({ position: { x: 370, y: 400 }, force: true });
  await expect(menuToggle).toHaveAttribute('aria-expanded', 'false');
  await menuToggle.click();
  await sidebar.getByRole('link', { name: 'Phòng', exact: true }).click();
  await expect(page).toHaveURL(`${origin}/phong/`);
  await expect(menuToggle).toHaveAttribute('aria-expanded', 'false');
  await noPageOverflow();
  const tableWrap = page.locator('.table-wrap').first();
  expect(await tableWrap.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
  await tableWrap.evaluate(node => { node.scrollLeft = node.scrollWidth; });
  expect(await tableWrap.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  await capture('rooms-mobile');
  for (const [label, route] of [
    ['room-form-mobile', `/phong/${roomId}/sua/`],
    ['contract-form-mobile', '/hop-dong/them/'],
    ['invoices-mobile', '/hoa-don/'],
    ['invoice-detail-mobile', `/hoa-don/${invoiceId}/`],
    ['contract-detail-mobile', `/hop-dong/${contractId}/`],
    ['buildings-mobile', '/toa-nha/'],
    ['room-map-mobile', '/so-do-phong/'],
    ['price-suggestion-mobile', `/phong/${roomId}/goi-y-gia/`],
    ['profile-mobile', '/ho-so/'],
  ]) {
    await page.goto(origin + route);
    await noPageOverflow();
    await capture(label);
  }
  pass('390px mobile: focus-trapped drawer, Escape/backdrop/link close, scrollable tables and forms');

  for (const width of [320, 768, 1100, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${origin}/quan-ly/`);
    await noPageOverflow();
    for (const item of await page.locator('.dashboard-stats-grid .stat strong').all()) {
      expect(await item.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    }
  }
  pass('320/768/1100/1280px: dashboard metrics fit and document does not overflow');

  for (const role of ['owner', 'staff', 'tenant']) {
    const roleContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const rolePage = await roleContext.newPage();
    await login(rolePage, `${role}-preview`);
    if (role === 'tenant') {
      await rolePage.goto(`${origin}/nguoi-thue/`);
      await expect(rolePage.locator('body')).not.toHaveClass(/management-app/);
      await expect(rolePage.locator('.sidebar nav a')).toHaveCount(10);
      await expect(rolePage.locator('.sidebar a[href="/nguoi-thue/phong/"]')).toBeVisible();
      await expect(rolePage.locator('.sidebar a[href="/tai-khoan/"]')).toHaveCount(0);
      await expect(rolePage.locator('link[href*="admin-shell.css"]')).toHaveCount(0);
    } else {
      await rolePage.goto(`${origin}/phong/`);
      await expect(rolePage.locator('body')).toHaveClass(/management-app/);
      await expect(rolePage.locator('table tbody')).toContainText('A105');
      if (role === 'staff') {
        // Staff may read the existing permission matrix, but cannot manage users.
        await expect(rolePage.locator('.sidebar a[href="/tai-khoan/ma-tran-quyen/"]')).toHaveCount(1);
        await expect(rolePage.locator('.sidebar a[href="/tai-khoan/"]')).toHaveCount(0);
        await expect(rolePage.getByRole('link', { name: 'Gợi ý giá', exact: true })).toHaveCount(0);
      }
    }
    await roleContext.close();
  }
  pass('Admin/owner/staff permissions and existing tenant interface remain separate');

  const noScriptContext = await browser.newContext({
    javaScriptEnabled: false, viewport: { width: 390, height: 844 },
    storageState: await context.storageState(),
  });
  const noScriptPage = await noScriptContext.newPage();
  await noScriptPage.goto(`${origin}/quan-ly/`);
  await expect(noScriptPage.locator('.sidebar nav').getByRole('link', { name: 'Phòng', exact: true })).toBeVisible();
  await expect(noScriptPage.locator('#site-loading')).toBeHidden();
  await expect(noScriptPage.locator('.chart-bar')).toHaveCount(12);
  expect(await noScriptPage.locator('.chart-bar').evaluateAll(nodes => nodes.every(node => node.getBoundingClientRect().height > 40))).toBe(true);
  await noPageOverflow(noScriptPage);
  await noScriptPage.locator('.sidebar nav').getByRole('link', { name: 'Phòng', exact: true }).click();
  await expect(noScriptPage).toHaveURL(`${origin}/phong/`);
  await noScriptContext.close();
  pass('Navigation and chart numbers/bars remain usable with JavaScript disabled');

  await page.setViewportSize({ width: 1536, height: 1000 });
  await page.goto(`${origin}/quan-ly/`);
  await page.locator('#userPopoverTrigger').click();
  await page.locator('.user-popover-logout-form button[type=submit]').click();
  await expect(page).toHaveURL(/dang-nhap/);
  pass('Actual logout succeeds for local fixture');
  expect(errors).toEqual([]);
  console.log(`PASS: ${completed.length} admin regression groups; no uncaught browser errors.`);
} finally {
  await browser.close();
}
