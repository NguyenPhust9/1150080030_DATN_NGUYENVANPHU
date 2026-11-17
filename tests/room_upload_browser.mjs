// Run only against tests/serve_indoor_preview.py: disposable SQLite fixtures.
// All Cloudinary traffic is intercepted; this test never uploads real assets.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const origin = 'http://127.0.0.1:8001';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const javascriptErrors = [];
const legacyUploads = [];
const saves = [];
const cloudUploads = [];
let signatureMode = 'valid';
let cloudHandler;
const signature = {
  cloud_name: 'test-cloud', api_key: 'test-key', timestamp: 1780000000,
  signature: 'test-signature', folder: 'ql-phong-cho-thue/rooms',
};
const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' };
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII=', 'base64');
const asset = (name, type = 'video', bytes = 128) => ({
  secure_url: `https://res.cloudinary.com/test-cloud/${type}/upload/${name}.${type === 'video' ? 'mp4' : 'png'}`,
  public_id: `${signature.folder}/${name}`, resource_type: type,
  format: type === 'video' ? 'mp4' : 'png', bytes,
});
async function succeed(route, data) {
  await route.fulfill({ status: 200, contentType: 'application/json', headers: cors, body: JSON.stringify(data) });
}

page.on('pageerror', error => javascriptErrors.push(error.message));
page.on('request', request => {
  const url = new URL(request.url());
  if (url.pathname === '/api/v1/cloudinary/upload/') legacyUploads.push(request.url());
  if (url.origin === origin && /^\/phong\/[^/]+\/sua\/$/.test(url.pathname) && request.method() === 'POST') {
    const body = request.postData() || '';
    saves.push({ body, fields: new URLSearchParams(body), headers: request.headers() });
  }
});
await context.route('**/api/v1/cloudinary/signature/', async route => {
  expect(route.request().method()).toBe('POST');
  expect(route.request().headers()['x-csrftoken']).toBeTruthy();
  expect(route.request().postDataBuffer()?.length || 0).toBe(0);
  if (signatureMode === 'expired') {
    await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ error: 'Forbidden' }) });
  } else if (signatureMode === 'invalid') {
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<html>Unexpected response</html>' });
  } else {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(signature) });
  }
});
await context.route(/^https:\/\/(?:[^/]+\.)?cloudinary\.com\//, async route => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.hostname !== 'api.cloudinary.com') {
    await route.fulfill({ status: 200, contentType: url.pathname.includes('/image/') ? 'image/png' : 'video/mp4', body: png, headers: cors });
    return;
  }
  if (request.method() === 'OPTIONS') {
    await route.fulfill({ status: 204, headers: { ...cors, 'access-control-allow-methods': 'POST, OPTIONS' } });
    return;
  }
  const body = request.postDataBuffer();
  const filename = body?.toString('latin1').match(/filename="([^"]+)"/)?.[1];
  cloudUploads.push({ url: request.url(), filename, bytes: body?.length || 0 });
  expect(request.method()).toBe('POST');
  expect(url.pathname).toMatch(/^\/v1_1\/test-cloud\/(video|image)\/upload$/);
  expect(body?.includes(Buffer.from('test-signature'))).toBe(true);
  expect(body?.includes(Buffer.from(signature.folder))).toBe(true);
  if (!cloudHandler) throw new Error('Unexpected Cloudinary upload');
  await cloudHandler(route, filename);
});

await mkdir('test-results', { recursive: true });
try {
  await page.goto(`${origin}/dang-nhap/`);
  await page.locator('[name="username"]').fill('indoor-preview');
  await page.locator('[name="password"]').fill('local-preview-only');
  await page.locator('button[type="submit"]').click();
  await expect(page.locator('.sidebar')).toBeVisible();
  await page.goto(`${origin}/phong/`);
  const editHref = await page.locator('a[href^="/phong/"][href$="/sua/"]').first().getAttribute('href');
  expect(editHref).toBeTruthy();
  async function openTab(tab = 'videos') {
    await page.goto(`${origin}${editHref}`);
    await page.locator(`.room-form-tabs [data-tab="${tab}"]`).click();
  }
  function assertMetadataSave(save, count) {
    expect(save.headers['content-type']).toContain('application/x-www-form-urlencoded');
    expect(Buffer.byteLength(save.body)).toBeLessThan(8192);
    expect(JSON.parse(save.fields.get('media_payload'))).toHaveLength(count);
    expect(save.fields.get('csrfmiddlewaretoken')).toBeTruthy();
    expect(save.fields.get('number')).toBeTruthy();
  }

  // 6 MiB exceeds Vercel's request-body limit; only the mock Cloudinary endpoint receives it.
  await openTab();
  const largeSize = 6 * 1024 * 1024;
  await page.locator('#room-videos').setInputFiles({ name: 'large-tour.mp4', mimeType: 'video/mp4', buffer: Buffer.alloc(largeSize, 7) });
  let releaseLarge;
  const pendingLarge = new Promise(resolve => { releaseLarge = resolve; });
  cloudHandler = async route => { await pendingLarge; await succeed(route, asset('large-tour', 'video', largeSize)); };
  await page.locator('#save-room').click();
  await expect.poll(() => cloudUploads.length).toBe(1);
  await expect(page.locator('#upload-progress')).toBeVisible();
  await expect(page.locator('#upload-message')).toContainText('large-tour.mp4');
  await expect(page.locator('#save-room')).toBeDisabled();
  await expect(page.locator('[name="number"]')).toBeDisabled();
  await expect(page.locator('#room-videos')).toBeDisabled();
  await expect(page.locator('#room-create-form')).toHaveAttribute('aria-busy', 'true');
  expect(cloudUploads[0].url).toBe('https://api.cloudinary.com/v1_1/test-cloud/video/upload');
  expect(cloudUploads[0].bytes).toBeGreaterThan(largeSize);
  expect(saves).toHaveLength(0);
  await page.screenshot({ path: 'test-results/room-upload-progress.png', fullPage: true });
  releaseLarge();
  await expect(page).toHaveURL(`${origin}/phong/`);
  assertMetadataSave(saves.at(-1), 1);
  await openTab();
  await expect(page.locator('h3', { hasText: 'Video hiện có' })).toBeVisible();
  await expect(page.locator(`video[src="${asset('large-tour').secure_url}"]`)).toHaveCount(1);
  console.log('PASS: 6 MiB direct upload, visible progress, locked fields, metadata-only save and SQLite persistence');

  // A network reset must preserve the selected file and allow a retry.
  await page.locator('#room-videos').setInputFiles({ name: 'network-error.mp4', mimeType: 'video/mp4', buffer: Buffer.alloc(128, 8) });
  const savesBeforeFailure = saves.length;
  cloudHandler = route => route.abort('connectionreset');
  await page.locator('#save-room').click();
  await expect(page.locator('#upload-status')).toHaveClass(/error/);
  await expect(page.locator('#upload-message')).toContainText('bị ngắt');
  await expect(page.locator('#upload-message')).toContainText('bấm Lưu để thử lại');
  await expect(page.locator('#save-room')).toBeEnabled();
  await expect(page.locator('[name="number"]')).toBeEnabled();
  expect(await page.locator('#room-videos').evaluate(input => input.files.length)).toBe(1);
  expect(saves).toHaveLength(savesBeforeFailure);
  await page.screenshot({ path: 'test-results/room-upload-network-error.png', fullPage: true });
  console.log('PASS: connection reset gives actionable Vietnamese error and preserves file for retry');

  // The first successful file must not be uploaded again when a later file fails.
  await openTab();
  await page.locator('#room-videos').setInputFiles([
    { name: 'retry-first.mp4', mimeType: 'video/mp4', buffer: Buffer.alloc(128, 1) },
    { name: 'retry-second.mp4', mimeType: 'video/mp4', buffer: Buffer.alloc(128, 2) },
  ]);
  let secondAttempts = 0;
  cloudHandler = async (route, filename) => {
    if (filename === 'retry-second.mp4' && ++secondAttempts === 1) await route.abort('connectionreset');
    else await succeed(route, asset(filename.replace('.mp4', '')));
  };
  await page.locator('#save-room').click();
  await expect(page.locator('#upload-status')).toHaveClass(/error/);
  expect(await page.locator('#room-videos').evaluate(input => input.files.length)).toBe(2);
  await expect(page.locator('#video-previews .media-preview')).toHaveCount(2);
  await page.locator('#save-room').click();
  await expect(page).toHaveURL(`${origin}/phong/`);
  expect(cloudUploads.filter(upload => upload.filename === 'retry-first.mp4')).toHaveLength(1);
  expect(cloudUploads.filter(upload => upload.filename === 'retry-second.mp4')).toHaveLength(2);
  assertMetadataSave(saves.at(-1), 2);
  await openTab();
  await expect(page.locator(`video[src="${asset('retry-first').secure_url}"]`)).toHaveCount(1);
  await expect(page.locator(`video[src="${asset('retry-second').secure_url}"]`)).toHaveCount(1);
  console.log('PASS: partial-success retry retains files and avoids uploading successful file twice');

  for (const mode of ['expired', 'invalid']) {
    await openTab();
    signatureMode = mode;
    const uploadsBefore = cloudUploads.length;
    const savesBefore = saves.length;
    await page.locator('#room-videos').setInputFiles({ name: `${mode}.mp4`, mimeType: 'video/mp4', buffer: Buffer.alloc(128, 3) });
    await page.locator('#save-room').click();
    await expect(page.locator('#upload-message')).toContainText(mode === 'expired' ? 'đăng nhập lại' : 'Thông tin tải tệp không hợp lệ');
    await expect(page.locator('#save-room')).toBeEnabled();
    expect(cloudUploads).toHaveLength(uploadsBefore);
    expect(saves).toHaveLength(savesBefore);
    expect(await page.locator('#room-videos').evaluate(input => input.files.length)).toBe(1);
  }
  signatureMode = 'valid';
  console.log('PASS: expired session and malformed signature stop before Cloudinary upload');

  await openTab('images');
  await page.locator('#room-images').setInputFiles([
    { name: 'cover-first.png', mimeType: 'image/png', buffer: png },
    { name: 'cover-second.png', mimeType: 'image/png', buffer: png },
  ]);
  await page.locator('#image-previews input[value="new:1"]').check();
  cloudHandler = (route, filename) => succeed(route, asset(filename.replace('.png', ''), 'image', png.length));
  await page.locator('#save-room').click();
  await expect(page).toHaveURL(`${origin}/phong/`);
  assertMetadataSave(saves.at(-1), 2);
  expect(saves.at(-1).fields.get('primary_image')).toBe('new:1');
  expect(cloudUploads.filter(upload => upload.url.endsWith('/image/upload'))).toHaveLength(2);
  await openTab('images');
  await expect(page.locator(`.media-preview:has(img[src="${asset('cover-second', 'image').secure_url}"]) input[name="primary-choice"]`)).toBeChecked();
  await expect(page.locator(`.media-preview:has(img[src="${asset('cover-first', 'image').secure_url}"]) input[name="primary-choice"]`)).not.toBeChecked();
  console.log('PASS: direct image uploads and primary-image selection persist');

  expect(legacyUploads).toEqual([]);
  expect(javascriptErrors).toEqual([]);
  console.log('PASS: no legacy upload requests, no unmocked Cloudinary traffic, no JavaScript errors');
} finally {
  await browser.close();
}
