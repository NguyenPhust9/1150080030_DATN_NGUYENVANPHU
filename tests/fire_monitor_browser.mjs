// Isolated browser contract checks: all URLs are intercepted, no webcam or database.
import { chromium, expect } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
import { createServer } from 'node:http';

const template = await readFile('apps/fire_detection/templates/fire_detection/monitor.html', 'utf8');
const css = await readFile('static/css/fire-monitor.css', 'utf8');
const script = await readFile('static/js/fire-monitor.js', 'utf8');
const content = template.split('{% block content %}')[1].split('{% endblock %}')[0]
  .replace(/\{% static '([^']+)' %\}/g, '/static/$1')
  .replace(/\{% url 'fire_detection:(\w+)' %\}/g, '/api/$1')
  .replace('{% csrf_token %}', '<input type="hidden" name="csrfmiddlewaretoken" value="fixture-token">')
  .replace(/\{\{[^}]+\}\}/g, 'fixture');
const html = '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fire monitor — isolated test</title><style>*{box-sizing:border-box}body{font-family:Arial,sans-serif;margin:0;padding:24px;background:#f8fafc;color:#0f172a}.button{padding:12px 16px;border-radius:10px;border:1px solid #cbd5e1;background:white}.primary{background:#0284c7;color:white}</style><main>' + content + '</main></html>';
const frame = '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#13233a"/><text x="640" y="350" text-anchor="middle" font-family="Arial" font-size="38" fill="#e2e8f0">VIDEO KIỂM THỬ GIẢ LẬP</text><text x="640" y="405" text-anchor="middle" font-family="Arial" font-size="24" fill="#94a3b8">Không sử dụng camera thật</text></svg>';
const base = {
  running: false, loading: false, state: 'stopped', error: '', fps: 0,
  detections: [], events: [], camera_index: 0, model_name: 'best.pt',
  model_source: 'runs/fire_detection/fixture/weights/best.pt', image_size: 768,
  fire_confidence: .25, smoke_confidence: .55, confirm_frames: 2,
  confirmation_window: 5, frame_age_seconds: null, result_stale: true,
  persistence: { pending: 0, active: false, failed: 0, queue_capacity: 8, last_error: '' },
};
let data = { ...base };
let statusMode = 'ok', actionMode = 'ok', releaseAction = null;
const requests = [];
const browser = await chromium.launch({
  headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
// Redirect continuations can bypass Playwright routing; this isolated server
// handles that login fixture without relying on DNS or a production server.
const server = createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html' });
  response.end('<h1>Login fixture</h1>');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await context.route('**/*', async route => {
  const request = route.request();
  const url = new URL(request.url());
  requests.push({ path: url.pathname, method: request.method() });
  if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
  if (url.pathname === '/static/css/fire-monitor.css') return route.fulfill({ contentType: 'text/css', body: css });
  if (url.pathname === '/static/js/fire-monitor.js') return route.fulfill({ contentType: 'text/javascript', body: script });
  if (url.pathname === '/api/stream') return route.fulfill({ contentType: 'image/svg+xml', body: frame });
  if (url.pathname === '/login') return route.fulfill({ contentType: 'text/html', body: '<h1>Login fixture</h1>' });
  if (url.pathname === '/api/status') {
    if (statusMode === 'network') return route.abort('failed');
    if (statusMode === 'login') return route.fulfill({ status: 302, headers: { Location: '/login' } });
    if (statusMode === 'html') return route.fulfill({ status: 500, contentType: 'text/html', body: 'Server unavailable' });
    if (statusMode === 'invalid') return route.fulfill({ json: { message: 'Invalid fixture' } });
    return route.fulfill({ json: data });
  }
  if (url.pathname === '/api/start' || url.pathname === '/api/stop') {
    expect(request.method()).toBe('POST');
    expect(request.headers()['x-csrftoken']).toBe('fixture-token');
    if (actionMode === 'held') await new Promise(resolve => { releaseAction = resolve; });
    if (actionMode === 'fail') return route.fulfill({ status: 503, json: { ok: false, message: 'Lỗi thao tác giả lập' } });
    return route.fulfill({ json: { ok: true, ...data } });
  }
  return route.fulfill({ status: 404, body: 'Unexpected isolated test URL' });
});
const state = (expected) => expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', expected);
const fresh = (name = 'monitoring') => ({ ...base, running: true, state: name, fps: 12.5, frame_age_seconds: .2, result_stale: false });
await mkdir('test-results', { recursive: true });
try {
  await page.goto('http://127.0.0.1:' + server.address().port + '/');
  await state('stopped');
  await expect(page.locator('#start-camera')).toBeEnabled();
  await expect(page.locator('#stop-camera')).toBeDisabled();
  await expect(page.locator('#safety-label')).not.toContainText('An toàn');
  expect(requests.filter(x => x.path === '/api/stream' || x.method === 'POST')).toHaveLength(0);

  data = fresh();
  await state('monitoring');
  await expect(page.locator('#safety-label')).toHaveText('Chưa phát hiện lửa/khói');
  await expect(page.locator('#camera-stream')).toHaveAttribute('src', /\/api\/stream\?t=/);
  await expect(page.locator('#model-source')).toContainText('fixture/weights/best.pt');
  await expect(page.locator('#model-resolution')).toHaveText('768 px');
  await page.reload();
  await state('monitoring');
  await expect(page.locator('#camera-stream')).toBeVisible();
  expect(requests.filter(x => x.method === 'POST')).toHaveLength(0);
  await page.screenshot({ path: 'test-results/fire-monitor-running.png', fullPage: true });

  data = { ...fresh(), result_stale: true, frame_age_seconds: 15 };
  await state('stale');
  await expect(page.locator('#camera-stream')).not.toHaveAttribute('src');
  await expect(page.locator('#detection-count')).toHaveText('—');
  await expect(page.locator('#ai-state')).toContainText('Không thể kết luận');
  data = { ...fresh(), frame_age_seconds: null };
  await expect(page.locator('#frame-freshness')).toContainText('Chưa có khung hình');
  await state('stale');

  data = { ...base, state: 'starting', loading: true };
  await state('starting');
  await expect(page.locator('#start-camera')).toBeDisabled();
  await expect(page.locator('#stop-camera')).toBeEnabled();
  data = fresh('detecting');
  await state('detecting');
  await expect(page.locator('#safety-label')).toContainText('đang xác minh');
  data = { ...fresh('alert'), detections: [{ label: 'fire', confidence: .6 }], events: [
    { labels: ['fire'], time: '<img src=x onerror="window.injected=true">', image_url: 'javascript:alert(1)' },
    { labels: ['smoke'], time: '12:30', image_url: 'https://example.com/private.jpg' },
  ] };
  await state('alert');
  await expect(page.locator('#fire-banner')).toBeVisible();
  await expect(page.locator('#event-list img')).toHaveCount(0);
  await expect(page.locator('#event-list a')).toHaveCount(0);
  await expect(page.locator('#event-list')).toContainText('<img src=x');
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  await page.screenshot({ path: 'test-results/fire-monitor-alert.png', fullPage: true });

  // Local evidence must remain visible if asynchronous database persistence fails.
  for (const persistenceState of ['queued', 'saving', 'saved', 'unmapped', 'failed', 'queue_full']) {
    const failed = ['failed', 'queue_full'].includes(persistenceState);
    data = { ...fresh('alert'), detections: [{ label: 'fire', confidence: .6 }], events: [{
      id: 'fixture-alert', labels: ['fire'], time: '12:30', image_url: '',
      persistence_state: persistenceState, persistence_error: 'DO_NOT_RENDER_DATABASE_DETAIL',
    }], persistence: {
      pending: persistenceState === 'queued' ? 1 : 0,
      active: persistenceState === 'saving', failed: failed ? 1 : 0,
      queue_capacity: 8, last_error: 'DO_NOT_RENDER_DATABASE_DETAIL',
    } };
    await expect(page.locator('.event-persistence')).toHaveAttribute('data-state', persistenceState);
    await state('alert');
    await expect(page.locator('#fire-banner')).toBeVisible();
    await expect(page.locator('body')).not.toContainText('DO_NOT_RENDER_DATABASE_DETAIL');
    if (['queued', 'saving'].includes(persistenceState)) {
      await expect(page.locator('#persistence-status')).toContainText('Đang đồng bộ 1 cảnh báo');
    } else if (persistenceState === 'saved') {
      await expect(page.locator('#persistence-status')).toBeHidden();
      await expect(page.locator('.event-persistence')).toHaveText('Đã lưu vào hệ thống');
    } else {
      await expect(page.locator('#persistence-status')).toContainText('chưa lưu vào hệ thống/bản đồ');
      await expect(page.locator('.event-persistence')).toContainText('Chỉ lưu ảnh');
    }
  }
  await page.screenshot({ path: 'test-results/fire-monitor-persistence-failed.png', fullPage: true });

  data = { ...base, state: 'error', error: 'Không mở được camera (giả lập)' };
  await state('error');
  await expect(page.locator('#ai-state')).toContainText('Không mở được');
  await expect(page.locator('#camera-stream')).not.toHaveAttribute('src');
  data = fresh();
  await state('monitoring');
  statusMode = 'network';
  await state('disconnected');
  await expect(page.locator('#camera-stream')).not.toHaveAttribute('src');
  await expect(page.locator('#monitor-message')).toBeVisible();
  await expect(page.locator('.fire-monitor')).not.toHaveClass(/monitoring/);
  statusMode = 'login';
  await expect(page.locator('#monitor-message')).toContainText('Phiên đăng nhập');
  statusMode = 'html';
  await expect(page.locator('#monitor-message')).toContainText('không trả về');
  statusMode = 'invalid';
  await expect(page.locator('#monitor-message')).toContainText('không hợp lệ');
  statusMode = 'ok';
  data = { ...base };
  await state('stopped');
  await expect(page.locator('#monitor-message')).toBeHidden();

  actionMode = 'held';
  await page.locator('#start-camera').click();
  await state('starting');
  await expect(page.locator('#start-camera')).toBeDisabled();
  await expect(page.locator('#stop-camera')).toBeDisabled();
  expect(releaseAction).not.toBeNull();
  data = { ...base, loading: true, state: 'starting' };
  actionMode = 'ok';
  releaseAction();
  await expect(page.locator('#stop-camera')).toBeEnabled();
  data = fresh();
  await state('monitoring');

  actionMode = 'held';
  releaseAction = null;
  await page.locator('#stop-camera').click();
  await state('stopping');
  await expect(page.locator('#start-camera')).toBeDisabled();
  await expect(page.locator('#stop-camera')).toBeDisabled();
  data = { ...base, running: true, state: 'stopping' };
  actionMode = 'ok';
  releaseAction();
  await state('stopping');
  data = { ...base };
  await state('stopped');
  actionMode = 'fail';
  await page.locator('#start-camera').click();
  await expect(page.locator('#monitor-message')).toHaveText('Lỗi thao tác giả lập');
  await state('disconnected');
  actionMode = 'ok';
  await state('stopped');

  data = fresh();
  await state('monitoring');
  await page.locator('#camera-stream').dispatchEvent('error');
  await state('disconnected');
  await expect(page.locator('#camera-stream')).not.toHaveAttribute('src');
  await expect(page.locator('#ai-state')).toContainText('Luồng hình ảnh');
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring', { timeout: 8000 });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/fire-monitor-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  console.log('PASS: isolated fire UI states, freshness, reload recovery, config, XSS, network/auth/invalid JSON, controls, stream retry, asynchronous persistence, mobile, no page errors.');
  console.log('Real camera, alert persistence, and database were not accessed.');
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
