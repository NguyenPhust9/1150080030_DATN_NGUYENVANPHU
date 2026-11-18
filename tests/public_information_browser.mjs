// Use only with the isolated tests/serve_public_home_preview.py fixture.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const base = 'http://127.0.0.1:8005';
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir('test-results', { recursive: true });

async function checkWidth() {
  const sizes = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sizes[0]).toBeLessThanOrEqual(sizes[1] + 1);
}

try {
  await page.goto(base);
  await page.locator('#public-nav a[href="/ve-chung-toi/"]').click();
  await expect(page).toHaveURL(`${base}/ve-chung-toi/`);
  await expect(page.locator('h1')).toContainText('Tìm phòng dễ hơn');
  await expect(page.locator('#public-nav [aria-current="page"]')).toHaveCount(1);
  await expect(page.locator('#public-nav [aria-current="page"]')).toHaveAttribute('href', '/ve-chung-toi/');
  await page.screenshot({ path: 'test-results/about-desktop.png', fullPage: true });

  await page.locator('#public-nav a[href="/lien-he/"]').click();
  await expect(page).toHaveURL(`${base}/lien-he/`);
  await expect(page.locator('#public-nav [aria-current="page"]')).toHaveAttribute('href', '/lien-he/');
  await expect(page.locator('.info-contact-card a[href="tel:0902966704"]').first()).toBeVisible();
  await expect(page.locator('.info-contact-card a[href="mailto:1150080030@sv.hcmunre.edu.vn"]').first()).toBeVisible();
  await expect(page.locator('form')).toHaveCount(0);
  const faq = page.locator('.info-faq details').first();
  await faq.locator('summary').click();
  await expect(faq).toHaveAttribute('open', '');
  await faq.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(faq).not.toHaveAttribute('open');
  await page.evaluate(() => {
    document.activeElement.blur();
    window.scrollTo({ top: 0, behavior: 'instant' });
  });
  await page.screenshot({ path: 'test-results/contact-desktop.png', fullPage: true });
  console.log('PASS desktop navigation, active tab, contact targets and accessible FAQ');

  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    for (const path of ['/ve-chung-toi/', '/lien-he/']) {
      await page.goto(base + path);
      await checkWidth();
      const menu = page.locator('#public-menu-toggle');
      if (await menu.isVisible()) {
        await menu.click();
        await expect(page.locator('#public-nav a')).toHaveCount(4);
        await expect(page.locator('#public-nav a[href="/ve-chung-toi/"]')).toBeVisible();
        await expect(page.locator('#public-nav a[href="/lien-he/"]')).toBeVisible();
        await checkWidth();
        await page.keyboard.press('Escape');
        await expect(page.locator('#public-nav')).toBeHidden();
        await expect(menu).toBeFocused();
      }
      if (width === 390) {
        const name = path.includes('ve-chung-toi') ? 'about' : 'contact';
        await page.screenshot({ path: `test-results/${name}-mobile.png`, fullPage: true });
      }
    }
    console.log(`PASS both information pages and menu at ${width}px`);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}/ve-chung-toi/`);
  await page.locator('#public-menu-toggle').click();
  await page.locator('#public-nav a[href="/lien-he/"]').click();
  await expect(page.locator('h1')).toContainText('hỗ trợ sử dụng');
  await page.locator('.info-callout a').click();
  await expect(page).toHaveURL(`${base}/phong-cho-thue/`);
  await expect(page.locator('.room-card')).toHaveCount(12);
  console.log('PASS mobile menu navigation and return to room search');

  const noJs = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  try {
    const plain = await noJs.newPage();
    await plain.goto(`${base}/lien-he/`);
    await expect(plain.locator('#site-loading')).toBeHidden();
    await expect(plain.locator('#public-nav a[href="/ve-chung-toi/"]')).toBeVisible();
    await plain.locator('.info-faq summary').first().click();
    await expect(plain.locator('.info-faq details').first()).toHaveAttribute('open', '');
    await plain.locator('#public-nav a[href="/ve-chung-toi/"]').click();
    await expect(plain).toHaveURL(`${base}/ve-chung-toi/`);
  } finally {
    await noJs.close();
  }
  console.log('PASS native navigation and FAQ without JavaScript');
  expect(errors).toEqual([]);
  console.log('PASS no uncaught JavaScript errors');
} finally {
  await context.close();
  await browser.close();
}
