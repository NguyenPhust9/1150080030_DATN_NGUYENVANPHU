import { chromium, expect } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
import { createServer } from 'node:http';
const template = await readFile('apps/fire_detection/templates/fire_detection/browser_monitor.html', 'utf8');
const css = await readFile('static/css/fire-monitor.css', 'utf8');
const js = await readFile('static/js/browser-fire-monitor.js', 'utf8');
const urls = { 'browser-config': '/api/config', 'browser-start': '/api/start', 'browser-stop': '/api/stop', 'browser-frame': '/api/frame', monitor: '/' };
const content = template.split('{% block content %}')[1].split('{% endblock %}')[0]
  .replace(/\{% static '([^']+)' %\}/g, '/static/$1')
  .replace(/\{% url 'fire_detection:([^']+)' %\}/g, (_, name) => urls[name])
  .replace('{% csrf_token %}', '<input name="csrfmiddlewaretoken" value="fixture-token">');
const html = '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>body{font-family:Arial;padding:24px;background:#f8fafc}.button{padding:12px;border-radius:8px}*{box-sizing:border-box}</style>' + content + '</html>';
const server = createServer((req, res) => {
  const path = new URL(req.url, 'http://local').pathname;
  res.setHeader('Content-Type', path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html');
  res.end(path.endsWith('.js') ? js : path.endsWith('.css') ? css : html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
const context = await browser.newContext({ permissions: ['camera'], viewport: { width: 1440, height: 1100 } });
await context.addInitScript(() => {
  window.cameraRequests = 0;
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  const enumerate = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
  navigator.mediaDevices.enumerateDevices = async () => [...await enumerate(), { kind: 'videoinput', deviceId: 'fixture-black-camera', label: 'Black virtual camera' }];
  navigator.mediaDevices.getUserMedia = async (...args) => {
    window.cameraRequests++; window.lastCameraConstraints = args[0];
    let stream;
    if (args[0].video?.deviceId?.exact === 'fixture-black-camera') {
      const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 240;
      const ctx = canvas.getContext('2d');
      stream = canvas.captureStream(10);
      const loop = setInterval(() => { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 320, 240); }, 100);
      const track = stream.getVideoTracks()[0]; window.blackCameraTrack = track;
      const stop = track.stop.bind(track); track.stop = () => { clearInterval(loop); stop(); };
      track.getSettings = () => ({ deviceId: 'fixture-black-camera', width: 320, height: 240 });
    } else stream = await original(...args);
    window.testStream = stream; return stream;
  };
});
let frames = 0, deliveries = 0, mode = 'fire', releaseDelivery, releaseFrame;
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/config') return route.fulfill({ json: { model_source: 'ONNX fixture', image_size: 512, fire_confidence: .25, smoke_confidence: .55, confirm_frames: 2, confirmation_window: 5, events: [] } });
  expect(route.request().headers()['x-csrftoken']).toBe('fixture-token');
  if (path === '/api/start') return route.fulfill({ json: { run_id: 'fixture-run' } });
  if (path === '/api/stop') return route.fulfill({ json: { ok: true } });
  if (path === '/api/frame') {
    frames++;
    expect(route.request().headers()['content-type']).toContain('multipart/form-data');
    if (mode === 'held') await new Promise(resolve => { releaseFrame = resolve; });
    return route.fulfill({ json: { state: mode === 'fire' ? 'alert' : 'monitoring', width: 640, height: 480, inference_ms: 150,
      detections: mode === 'fire' ? [{ label: 'fire', confidence: .9, xyxy: [100, 100, 200, 250] }] : [],
      alert: mode === 'fire' && frames === 1 ? { id: 'event-1', time: 'fixture-time', labels: ['fire'] } : null } });
  }
  throw new Error('Unexpected route: ' + path);
});
await context.route('**/camera/canh-bao/*/gui/', async route => {
  deliveries++;
  await new Promise(resolve => { releaseDelivery = resolve; });
  await route.fulfill({ json: { webhook_state: 'sent', image_url: '', persistence_state: 'unmapped' } });
});
try {
  await page.goto(origin);
  await expect(page.locator('#start-camera')).toBeEnabled();
  expect(await page.evaluate(() => window.cameraRequests)).toBe(0);
  await page.locator('#start-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'alert');
  await expect.poll(() => deliveries).toBe(1);
  await expect.poll(() => frames).toBeGreaterThan(1);
  await expect(page.locator('#event-list')).toContainText('Đang tải ảnh và gửi n8n');
  releaseDelivery();
  await expect(page.locator('#event-list')).toContainText('n8n đã nhận cảnh báo');
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: 'test-results/browser-fire-monitor.png', fullPage: true });
  await page.locator('#stop-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
  expect(await page.evaluate(() => window.testStream.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
  expect(await page.evaluate(() => window.lastCameraConstraints.video)).toBe(true);
  const physical = await page.evaluate(async () => (await navigator.mediaDevices.enumerateDevices()).find(device => device.kind === 'videoinput' && device.deviceId !== 'fixture-black-camera').deviceId);
  const beforeBlack = frames;
  await page.locator('#camera-device').selectOption('fixture-black-camera');
  await page.locator('#start-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'camera_issue');
  await expect(page.locator('#monitor-message')).toContainText('Nguồn camera đang gửi hình đen');
  expect(frames).toBe(beforeBlack);
  await page.locator('#camera-device').selectOption(physical);
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'alert');
  expect(await page.evaluate(() => window.lastCameraConstraints.video.deviceId.exact)).toBe(physical);
  expect(await page.evaluate(() => window.blackCameraTrack.readyState)).toBe('ended');
  await expect(page.locator('#camera-source')).toContainText('×');
  await page.locator('#stop-camera').click();
  mode = 'held';
  await page.locator('#start-camera').click();
  await expect.poll(() => Boolean(releaseFrame)).toBe(true);
  await page.locator('#stop-camera').click();
  releaseFrame();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
  await page.evaluate(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError'); }; });
  await page.locator('#start-camera').click();
  await expect(page.locator('#monitor-message')).toContainText('Bạn chưa cho phép camera');
  await expect(page.locator('#start-camera')).toBeEnabled();
  expect(errors).toEqual([]);
  console.log('PASS: camera defaults, exact device selection, black-stream rejection, source switching, webhook independence, cleanup and permission denial');
} finally {
  releaseFrame?.(); releaseDelivery?.();
  await browser.close(); server.close();
}

