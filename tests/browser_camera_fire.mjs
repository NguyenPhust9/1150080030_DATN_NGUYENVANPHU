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
  window.beepCount = 0;
  const Audio = window.AudioContext;
  window.AudioContext = class extends Audio {
    createOscillator() { window.beepCount++; return super.createOscillator(); }
  };
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  window.blackCamera = false;
  navigator.mediaDevices.enumerateDevices = async () => [
    { kind: 'videoinput', deviceId: 'fixture-eshare', label: 'EShare Virtual Camera' },
    { kind: 'videoinput', deviceId: 'fixture-hd', label: 'HD User Facing (0408:4061)' },
    { kind: 'videoinput', deviceId: 'fixture-obs', label: 'OBS Virtual Camera' },
  ];
  navigator.mediaDevices.getUserMedia = async (...args) => {
    window.cameraRequests++; window.lastCameraConstraints = args[0];
    if (args[0].video?.deviceId?.exact !== 'fixture-hd') throw new Error('Opened a camera other than HD User Facing');
    let stream;
    if (window.blackCamera) {
      const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 240;
      const ctx = canvas.getContext('2d');
      stream = canvas.captureStream(10);
      const loop = setInterval(() => { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 320, 240); }, 100);
      const track = stream.getVideoTracks()[0]; window.blackCameraTrack = track;
      const stop = track.stop.bind(track); track.stop = () => { clearInterval(loop); stop(); };
    } else stream = await original({ video: true, audio: false });
    const track = stream.getVideoTracks()[0], settings = track.getSettings();
    Object.defineProperty(track, 'label', { value: 'HD User Facing (0408:4061)' });
    track.getSettings = () => ({ ...settings, deviceId: 'fixture-hd' });
    window.testStream = stream; return stream;
  };
});
let frames = 0, deliveries = 0, mode = 'fire', releaseDelivery, releaseFrame;
const page = await context.newPage();
const errors = [];
const frameTimings = [], activeFrames = new Set();
let maxConcurrentFrames = 0;
page.on('request', request => {
  if (new URL(request.url()).pathname !== '/api/frame') return;
  activeFrames.add(request); maxConcurrentFrames = Math.max(maxConcurrentFrames, activeFrames.size);
});
for (const event of ['requestfinished', 'requestfailed']) page.on(event, request => activeFrames.delete(request));
page.on('pageerror', error => errors.push(error.message));
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/config') return route.fulfill({ json: { model_source: 'ONNX fixture', image_size: 512, fire_confidence: .25, smoke_confidence: .55, confirm_frames: 2, confirmation_window: 5, events: [] } });
  expect(route.request().headers()['x-csrftoken']).toBe('fixture-token');
  if (path === '/api/start') return route.fulfill({ json: { run_id: 'fixture-run' } });
  if (path === '/api/stop') return route.fulfill({ json: { ok: true } });
  if (path === '/api/frame') {
    frames++;
    const timing = { mode, requestedAt: performance.now(), fulfilledAt: null }; frameTimings.push(timing);
    expect(route.request().headers()['content-type']).toContain('multipart/form-data');
    if (mode === 'held') await new Promise(resolve => { releaseFrame = resolve; });
    if (mode === 'delayed') await new Promise(resolve => setTimeout(resolve, 550));
    timing.fulfilledAt = performance.now();
    return route.fulfill({ json: { state: mode === 'fire' || mode === 'recent' ? 'alert' : 'monitoring', current_state: mode === 'recent' ? 'recent_alert' : undefined, width: 640, height: 480, inference_ms: 150,
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
async function verifyHDOnly({ hidden = false, preferred = true, cancel = false }) {
  const fixture = await browser.newContext({ permissions: ['camera'] });
  await fixture.addInitScript(({ hidden, preferred, cancel }) => {
    // A touch-enabled Windows laptop must keep the desktop HD-only rule.
    Object.defineProperty(navigator, 'maxTouchPoints', { value: 5 });
    let permitted = !hidden;
    window.cameraConstraints = []; window.cameraTracks = [];
    const cameras = [
      { kind: 'videoinput', deviceId: 'fixture-default', label: 'EShare Virtual Camera' },
      ...(preferred ? [{ kind: 'videoinput', deviceId: 'fixture-hd', label: 'HD User Facing (0408:4061)' }] : []),
      { kind: 'videoinput', deviceId: 'fixture-obs', label: 'OBS Virtual Camera' },
    ];
    navigator.mediaDevices.enumerateDevices = async () => cameras.map(device => ({ ...device, label: permitted ? device.label : '' }));
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => {
      window.cameraConstraints.push(constraints);
      const id = constraints.video?.deviceId?.exact || 'fixture-default';
      if (cancel && id === 'fixture-hd') await new Promise(resolve => { window.releasePreferredCamera = resolve; });
      const stream = await getUserMedia({ video: true, audio: false });
      permitted = true;
      const track = stream.getVideoTracks()[0], settings = track.getSettings();
      Object.defineProperty(track, 'label', { value: cameras.find(device => device.deviceId === id).label });
      track.getSettings = () => ({ ...settings, deviceId: id });
      window.cameraTracks.push(track);
      return stream;
    };
  }, { hidden, preferred, cancel });
  let starts = 0, frameCount = 0;
  await fixture.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/config') return route.fulfill({ json: { model_source: 'fixture', image_size: 512, fire_confidence: .25, smoke_confidence: .55, confirm_frames: 2, confirmation_window: 5, events: [] } });
    if (path === '/api/start') { starts++; return route.fulfill({ json: { run_id: 'preferred-fixture' } }); }
    if (path === '/api/stop') return route.fulfill({ json: { ok: true } });
    if (path === '/api/frame') {
      frameCount++;
      return route.fulfill({ json: { state: 'monitoring', detections: [], width: 640, height: 480, inference_ms: 10 } });
    }
    throw new Error('Unexpected fixture route: ' + path);
  });
  const cameraPage = await fixture.newPage();
  try {
    await cameraPage.goto(origin);
    await expect(cameraPage.locator('#camera-device')).toHaveText('HD User Facing');
    await expect(cameraPage.locator('#switch-camera')).toBeHidden();
    await expect(cameraPage.locator('select#camera-device, #camera-device option')).toHaveCount(0);
    await expect(cameraPage.locator('.fire-monitor')).not.toContainText(/EShare|OBS/);
    expect(await cameraPage.evaluate(() => window.cameraConstraints)).toEqual([]);
    await cameraPage.locator('#start-camera').click();
    if (cancel) {
      await expect.poll(() => cameraPage.evaluate(() => Boolean(window.releasePreferredCamera))).toBe(true);
      await cameraPage.locator('#stop-camera').click();
      await cameraPage.evaluate(() => window.releasePreferredCamera());
      await expect.poll(() => cameraPage.evaluate(() => window.cameraTracks.length)).toBe(2);
      await expect.poll(() => cameraPage.evaluate(() => window.cameraTracks.every(track => track.readyState === 'ended'))).toBe(true);
      expect(starts).toBe(0); expect(frameCount).toBe(0);
      await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
      return;
    }
    if (!preferred) {
      await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'error');
      await expect(cameraPage.locator('#monitor-message')).toContainText('Không tìm thấy camera HD User Facing');
      expect(await cameraPage.evaluate(() => window.cameraConstraints)).toEqual(hidden ? [{ video: true, audio: false }] : []);
      expect(await cameraPage.evaluate(() => window.cameraTracks.every(track => track.readyState === 'ended'))).toBe(true);
      expect(starts).toBe(0); expect(frameCount).toBe(0);
      expect(await cameraPage.locator('#browser-camera').evaluate(video => video.srcObject)).toBe(null);
      return;
    }
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring');
    const requests = await cameraPage.evaluate(() => window.cameraConstraints);
    expect(requests.at(-1).video).toEqual({ deviceId: { exact: 'fixture-hd' } });
    expect(requests).toHaveLength(hidden ? 2 : 1);
    expect(starts).toBe(1);
    if (hidden) expect(await cameraPage.evaluate(() => window.cameraTracks[0].readyState)).toBe('ended');
    await expect(cameraPage.locator('#camera-source')).toContainText('HD User Facing');
    await cameraPage.locator('#stop-camera').click();
    await expect.poll(() => cameraPage.evaluate(() => window.cameraTracks.every(track => track.readyState === 'ended'))).toBe(true);
  } finally {
    await fixture.close();
  }
}
async function verifyMobileCamera(profile) {
  const fixture = await browser.newContext({ permissions: ['camera'], userAgent: profile.userAgent, viewport: { width: 390, height: 844 } });
  await fixture.addInitScript(({ platform }) => {
    Object.defineProperty(navigator, 'platform', { value: platform });
    Object.defineProperty(navigator, 'maxTouchPoints', { value: 5 });
    window.mobileRequests = []; window.mobileTracks = [];
    window.rejectCamera = false; window.holdCamera = false;
    navigator.mediaDevices.enumerateDevices = async () => { throw new Error('Mobile should select by facingMode'); };
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => {
      window.mobileRequests.push(constraints);
      if (window.rejectCamera) throw new DOMException('Missing facing mode', 'OverconstrainedError');
      if (window.holdCamera) await new Promise(resolve => { window.releaseMobileCamera = resolve; });
      if (window.mobileTracks.some(track => track.readyState === 'live')) throw new Error('Previous camera was not stopped');
      const stream = await original({ video: true, audio: false });
      const track = stream.getVideoTracks()[0];
      const facing = constraints.video.facingMode.exact || constraints.video.facingMode.ideal;
      Object.defineProperty(track, 'label', { value: facing === 'user' ? 'Front camera' : 'Back camera' });
      track.getSettings = () => ({ facingMode: facing });
      window.mobileTracks.push(track);
      return stream;
    };
  }, profile);
  let frameCount = 0, starts = 0;
  await fixture.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/config') return route.fulfill({ json: { model_source: 'fixture', image_size: 512, fire_confidence: .25, smoke_confidence: .55, confirm_frames: 2, confirmation_window: 5, events: [] } });
    if (path === '/api/start') { starts++; return route.fulfill({ json: { run_id: 'mobile-' + starts } }); }
    if (path === '/api/stop') return route.fulfill({ json: { ok: true } });
    if (path === '/api/frame') {
      frameCount++;
      return route.fulfill({ json: { state: 'monitoring', detections: [], width: 640, height: 480, inference_ms: 10 } });
    }
    throw new Error('Unexpected mobile route: ' + path);
  });
  const cameraPage = await fixture.newPage();
  const mobileErrors = [];
  cameraPage.on('pageerror', error => mobileErrors.push(error.message));
  try {
    await cameraPage.goto(origin);
    await expect(cameraPage.locator('#camera-device')).toHaveText('Camera sau');
    await expect(cameraPage.locator('#switch-camera')).toBeVisible();
    await expect(cameraPage.locator('#switch-camera')).toBeDisabled();
    expect(await cameraPage.evaluate(() => window.mobileRequests)).toEqual([]);
    await cameraPage.locator('#start-camera').click();
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring');
    expect(await cameraPage.evaluate(() => window.mobileRequests[0])).toEqual({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    await expect(cameraPage.locator('#camera-source')).toContainText('Back camera');
    await cameraPage.locator('#switch-camera').click();
    await expect(cameraPage.locator('#camera-device')).toHaveText('Camera trước');
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring');
    expect(await cameraPage.evaluate(() => window.mobileRequests.at(-1).video)).toEqual({ facingMode: { exact: 'user' } });
    expect(await cameraPage.evaluate(() => window.mobileTracks[0].readyState)).toBe('ended');
    await expect(cameraPage.locator('#camera-source')).toContainText('Front camera');
    await cameraPage.locator('#switch-camera').click();
    await expect(cameraPage.locator('#camera-device')).toHaveText('Camera sau');
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring');
    expect(await cameraPage.evaluate(() => window.mobileRequests.at(-1).video)).toEqual({ facingMode: { exact: 'environment' } });
    expect(starts).toBe(3);
    // A phone without the requested alternate camera must report the failure.
    await cameraPage.evaluate(() => { window.rejectCamera = true; });
    await cameraPage.locator('#switch-camera').click();
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'error');
    await expect(cameraPage.locator('#monitor-message')).toContainText('Thiết bị không có camera trước/sau đã chọn');
    expect(starts).toBe(3);
    expect(await cameraPage.evaluate(() => window.mobileTracks.every(track => track.readyState === 'ended'))).toBe(true);
    // Stop during camera acquisition must prevent AI start and release the late stream.
    await cameraPage.evaluate(() => { window.rejectCamera = false; window.holdCamera = true; });
    await cameraPage.locator('#start-camera').click();
    await expect.poll(() => cameraPage.evaluate(() => Boolean(window.releaseMobileCamera))).toBe(true);
    await cameraPage.locator('#stop-camera').click();
    const before = frameCount;
    await cameraPage.evaluate(() => window.releaseMobileCamera());
    await expect.poll(() => cameraPage.evaluate(() => window.mobileTracks.length)).toBe(4);
    await expect.poll(() => cameraPage.evaluate(() => window.mobileTracks.every(track => track.readyState === 'ended'))).toBe(true);
    expect(starts).toBe(3); expect(frameCount).toBe(before);
    await expect(cameraPage.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
    expect(mobileErrors).toEqual([]);
  } finally {
    await fixture.close();
  }
}
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
  expect(await page.evaluate(() => window.beepCount)).toBe(1);
  mode = 'recent';
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'recent_alert');
  await expect(page.locator('.fire-monitor')).toHaveClass(/\balert\b/);
  await expect(page.locator('#ai-state')).toContainText('Khung hình mới chưa xác nhận lại lửa/khói');
  await expect(page.locator('#detection-count')).toHaveText('0');
  expect(deliveries).toBe(1);
  mode = 'fire';
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'alert');
  expect(await page.evaluate(() => window.beepCount)).toBe(1);
  expect(deliveries).toBe(1);
  mode = 'delayed';
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'monitoring');
  await expect.poll(async () => Number((await page.locator('#fps-label').textContent()).match(/Tổng ([\d.]+)/)?.[1] || 0)).toBeGreaterThanOrEqual(.5);
  await expect.poll(async () => parseFloat(await page.locator('#frame-freshness').textContent())).toBeGreaterThanOrEqual(.5);
  await expect(page.locator('#frame-freshness')).not.toContainText('Vừa cập nhật');
  await expect.poll(() => frameTimings.filter(timing => timing.mode === 'delayed' && timing.fulfilledAt !== null).length).toBeGreaterThanOrEqual(2);
  const slowFrameIndex = frameTimings.findIndex(timing => timing.mode === 'delayed');
  expect(frameTimings[slowFrameIndex + 1].requestedAt - frameTimings[slowFrameIndex].fulfilledAt).toBeLessThan(400);
  expect(maxConcurrentFrames).toBe(1);
  mode = 'fire';
  await page.locator('#stop-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
  expect(await page.evaluate(() => window.testStream.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
  expect(await page.evaluate(() => window.lastCameraConstraints.video)).toEqual({ deviceId: { exact: 'fixture-hd' } });
  const beforeBlack = frames;
  await page.evaluate(() => { window.blackCamera = true; });
  await page.locator('#start-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'camera_issue');
  await expect(page.locator('#monitor-message')).toContainText('Camera HD User Facing đang gửi hình đen');
  expect(frames).toBe(beforeBlack);
  await page.locator('#stop-camera').click();
  expect(await page.evaluate(() => window.blackCameraTrack.readyState)).toBe('ended');
  await page.evaluate(() => { window.blackCamera = false; });
  await page.locator('#start-camera').click();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'alert');
  expect(await page.evaluate(() => window.lastCameraConstraints.video.deviceId.exact)).toBe('fixture-hd');
  await expect(page.locator('#camera-source')).toContainText('×');
  await page.locator('#stop-camera').click();
  mode = 'held';
  await page.locator('#start-camera').click();
  await expect.poll(() => Boolean(releaseFrame)).toBe(true);
  await page.locator('#stop-camera').click();
  const stoppedFrames = frames;
  releaseFrame();
  await expect(page.locator('.fire-monitor')).toHaveAttribute('data-state', 'stopped');
  await page.waitForTimeout(450);
  expect(frames).toBe(stoppedFrames);
  expect(maxConcurrentFrames).toBe(1);
  await page.evaluate(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError'); }; });
  await page.locator('#start-camera').click();
  await expect(page.locator('#monitor-message')).toContainText('Bạn chưa cho phép camera');
  await expect(page.locator('#start-camera')).toBeEnabled();
  expect(errors).toEqual([]);
  await verifyHDOnly({});
  await verifyHDOnly({ hidden: true });
  await verifyHDOnly({ preferred: false });
  await verifyHDOnly({ hidden: true, preferred: false });
  await verifyHDOnly({ hidden: true, cancel: true });
  await verifyMobileCamera({ userAgent: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36', platform: 'Linux armv8l' });
  await verifyMobileCamera({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1', platform: 'iPhone' });
  await verifyMobileCamera({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15', platform: 'MacIntel' });
  console.log('PASS: Android/iPhone/iPad rear camera preference, front/back switching, release before reopen, unsupported camera and startup cancellation; touch desktop remains HD-only');
  console.log('PASS: HD User Facing only, hidden-name permission bootstrap and cleanup, missing-HD errors before/after permission, startup cancellation, recent-alert display, capture-to-response age, prompt serial sampling after delayed response, black-stream rejection, webhook independence, cleanup and permission denial');
} finally {
  releaseFrame?.(); releaseDelivery?.();
  await browser.close(); server.close();
}

