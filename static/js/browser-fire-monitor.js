(() => {
  'use strict';
  const root = document.querySelector('.fire-monitor');
  if (!root) return;
  const find = id => root.querySelector('#' + id);
  const video = find('browser-camera'), overlay = find('detection-overlay');
  const start = find('start-camera'), stop = find('stop-camera'), cameraSelect = find('camera-device');
  const probe = document.createElement('canvas'); probe.width = 32; probe.height = 24;
  const probeContext = probe.getContext('2d', { willReadFrequently: true });
  const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  const capture = document.createElement('canvas');
  let stream = null, generation = 0, runId = '', sequence = 0, timer = null;
  let controller = null, lastResult = 0, running = false, starting = false, disposed = false;
  let wasAlert = false, audio = null, failures = 0, blackFrames = 0;
  const events = new Map();
  const labels = {
    stopped: 'Đã dừng giám sát', starting: 'Đang mở camera và kết nối AI…',
    monitoring: 'Chưa phát hiện lửa/khói', detecting: 'Đang xác minh dấu hiệu lửa/khói…',
    alert: 'CẢNH BÁO LỬA / KHÓI', camera_issue: 'Camera đang trả về hình đen', stale: 'Chưa có kết quả AI mới', error: 'Lỗi giám sát',
  };
  function state(value, message = '') {
    root.dataset.state = value;
    for (const name of ['monitoring', 'detecting', 'alert']) root.classList.toggle(name, name === value);
    find('camera-state').textContent = labels[value];
    find('ai-state').textContent = message || labels[value];
    find('safety-label').textContent = labels[value];
    find('camera-placeholder-title').textContent = labels[value];
    find('camera-placeholder-text').textContent = message || 'Bấm “Bắt đầu giám sát” và cho phép sử dụng camera.';
    start.disabled = starting || running;
    stop.disabled = !starting && !running;
    cameraSelect.disabled = starting;
    root.setAttribute('aria-busy', String(starting));
    if (value !== 'alert') wasAlert = false;
  }
  function message(text = '') {
    find('monitor-message').textContent = text;
    find('monitor-message').hidden = !text;
  }
  async function refreshCameras(activeId = '') {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const selected = activeId || cameraSelect.value;
    const devices = (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput' && device.deviceId);
    const choices = [new Option('Camera mặc định của trình duyệt', '')];
    devices.forEach((device, index) => choices.push(new Option(device.label || 'Camera ' + (index + 1), device.deviceId)));
    cameraSelect.replaceChildren(...choices);
    if (devices.some(device => device.deviceId === selected)) cameraSelect.value = selected;
  }
  function blackFrame() {
    probeContext.drawImage(video, 0, 0, probe.width, probe.height);
    const pixels = probeContext.getImageData(0, 0, probe.width, probe.height).data;
    let highest = 0, total = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      const value = Math.max(pixels[i], pixels[i + 1], pixels[i + 2]);
      highest = Math.max(highest, value); total += value;
    }
    return highest < 8 && total / (pixels.length / 4) < 3;
  }
  async function waitForVideoFrame(version) {
    const deadline = Date.now() + 8000;
    while (version === generation && !disposed && Date.now() < deadline) {
      const track = stream?.getVideoTracks()[0];
      if (!track || track.readyState !== 'live') throw new Error('Camera đã ngắt kết nối. Hãy chọn lại camera.');
      if (!track.muted && video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('Camera chưa trả về hình ảnh. Hãy chọn đúng webcam hoặc đóng ứng dụng đang dùng camera.');
  }
  function beep() {
    try {
      audio ||= new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audio.createOscillator(), gain = audio.createGain();
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.1, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.5);
      oscillator.connect(gain).connect(audio.destination);
      oscillator.start(); oscillator.stop(audio.currentTime + 0.5);
    } catch (_) { /* Visual alerts remain available when audio is blocked. */ }
  }
  async function request(url, options = {}, timeout = 45000) {
    const cancel = new AbortController();
    const expires = setTimeout(() => cancel.abort(), timeout);
    if (options.frame) controller = cancel;
    try {
      const response = await fetch(url, {
        method: options.body ? 'POST' : 'GET', body: options.body,
        credentials: 'same-origin', cache: 'no-store', signal: cancel.signal,
        headers: { Accept: 'application/json', 'X-CSRFToken': csrf },
      });
      if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error('Phiên đăng nhập đã hết hạn hoặc không có quyền. Hãy tải lại trang.');
      }
      if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Máy chủ chưa trả được kết quả AI. Hãy thử lại.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Không nhận được kết quả (HTTP ' + response.status + ').');
      return data;
    } finally { clearTimeout(expires); if (controller === cancel) controller = null; }
  }
  function body(fields) {
    const data = new FormData();
    for (const [key, value] of Object.entries(fields)) data.append(key, value);
    return data;
  }
  function drawBoxes(data) {
    overlay.width = data.width; overlay.height = data.height;
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.font = '18px sans-serif'; ctx.lineWidth = 3;
    for (const item of data.detections || []) {
      const [x1, y1, x2, y2] = item.xyxy;
      ctx.strokeStyle = item.label === 'fire' ? '#ff493c' : '#ffb72b'; ctx.fillStyle = ctx.strokeStyle;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.fillText((item.label === 'fire' ? 'Lửa' : 'Khói') + ' ' + Math.round(item.confidence * 100) + '%', x1, Math.max(20, y1 - 5));
    }
  }
  function renderEvents() {
    const fragment = document.createDocumentFragment();
    const deliveryLabels = { pending: 'Chờ gửi ảnh', sending: 'Đang tải ảnh và gửi n8n', sent: 'n8n đã nhận cảnh báo',
      disabled: 'Đã lưu ảnh · Chưa cấu hình n8n', failed: 'Chưa xác nhận n8n đã nhận · Kiểm tra workflow', expired: 'Yêu cầu gửi đã hết hạn', unknown: 'Chưa xác nhận kết quả gửi · Kiểm tra n8n' };
    const entries = [...events.values()].reverse().slice(0, 10);
    for (const item of entries) {
      let url = null;
      try { const parsed = new URL(item.image_url); if (parsed.protocol === 'https:' && parsed.hostname === 'res.cloudinary.com') url = parsed.href; } catch (_) { /* No image yet. */ }
      const entry = document.createElement(url ? 'a' : 'div'); entry.className = 'event-item';
      if (url) {
        entry.href = url; entry.target = '_blank'; entry.rel = 'noopener noreferrer';
        const image = document.createElement('img'); image.src = url; image.alt = 'Ảnh cảnh báo'; image.loading = 'lazy'; entry.append(image);
      }
      const detail = document.createElement('span'), title = document.createElement('strong');
      title.textContent = (item.labels || []).map(name => name === 'fire' ? 'Lửa' : 'Khói').join(', ');
      const time = document.createElement('small'); time.textContent = item.time || '';
      const delivery = document.createElement('small'); delivery.textContent = deliveryLabels[item.webhook_state] || 'Đang xử lý';
      detail.append(title, time, delivery); entry.append(detail); fragment.append(entry);
    }
    if (!entries.length) { const empty = document.createElement('p'); empty.textContent = 'Chưa có cảnh báo.'; fragment.append(empty); }
    find('event-list').replaceChildren(fragment);
  }
  async function deliver(alert, blob) {
    const item = { ...alert, webhook_state: 'sending', image_url: '' };
    events.set(alert.id, item); renderEvents();
    try {
      const data = body({ image: blob });
      Object.assign(item, await request(root.dataset.deliveryBase + alert.id + '/gui/', { body: data }, 60000));
    } catch (_) { item.webhook_state = 'failed'; }
    renderEvents();
  }
  async function frame(version) {
    if (!running || disposed || version !== generation) return;
    try {
      if (!video.videoWidth || video.readyState < 2) { timer = setTimeout(() => frame(version), 300); return; }
      if (stream?.getVideoTracks()[0]?.muted || blackFrame()) {
        blackFrames += 1; lastResult = 0;
        overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
        find('detection-count').textContent = '—'; find('fps-label').textContent = '—';
        find('frame-freshness').textContent = 'Chưa có hình ảnh hợp lệ';
        if (blackFrames >= 3) {
          const text = 'Nguồn camera đang gửi hình đen. Chọn webcam khác ở mục Camera; kiểm tra nắp che và đóng ứng dụng Camera Windows.';
          state('camera_issue', text); message(text);
        } else state('starting', 'Đang chờ hình ảnh từ camera…');
        timer = setTimeout(() => frame(version), 750);
        return;
      }
      blackFrames = 0;
      const scale = Math.min(1, 1280 / video.videoWidth, 720 / video.videoHeight);
      capture.width = Math.round(video.videoWidth * scale); capture.height = Math.round(video.videoHeight * scale);
      capture.getContext('2d').drawImage(video, 0, 0, capture.width, capture.height);
      const blob = await new Promise(resolve => capture.toBlob(resolve, 'image/jpeg', 0.8));
      if (!blob || blob.size > 1024 * 1024) throw new Error('Không tạo được khung hình dưới 1 MB.');
      if (!running || version !== generation) return;
      const data = await request(root.dataset.frameUrl, { frame: true, body: body({ image: blob, run_id: runId, sequence: ++sequence }) });
      if (!running || disposed || version !== generation) return;
      lastResult = Date.now(); failures = 0;
      state(data.state); message(); drawBoxes(data);
      find('detection-count').textContent = String(data.detections.length);
      find('fps-label').textContent = 'AI ' + (data.inference_ms / 1000).toFixed(2) + ' giây/khung';
      find('frame-freshness').textContent = 'Vừa cập nhật';
      if (data.state === 'alert' && !wasAlert) beep();
      wasAlert = data.state === 'alert';
      if (data.alert) void deliver(data.alert, blob);
    } catch (error) {
      if (!running || version !== generation || disposed) return;
      failures += 1;
      const text = error.name === 'AbortError' ? 'Nhận diện phản hồi quá chậm. Chưa có kết quả mới.' : error.message;
      state('stale', text); message(text); overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
      if (failures >= 3) { stopCamera(); state('error', text); return; }
    }
    if (running && version === generation && !disposed) timer = setTimeout(() => frame(version), 750);
  }
  function stopCamera() {
    const oldId = runId;
    generation += 1; running = false; starting = false; runId = ''; clearTimeout(timer); controller?.abort();
    stream?.getTracks().forEach(track => track.stop()); stream = null; video.srcObject = null; video.classList.remove('active');
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
    lastResult = 0; wasAlert = false; find('detection-count').textContent = '—'; find('fps-label').textContent = '—';
    find('frame-freshness').textContent = 'Đã dừng camera'; state('stopped');
    if (oldId) return request(root.dataset.stopUrl, { body: body({ run_id: oldId }) }).catch(() => {});
    return Promise.resolve();
  }
  async function startCamera() {
    if (starting || running || disposed) return;
    starting = true; const version = ++generation; state('starting'); message();
    let acquired = null;
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Cần trình duyệt hỗ trợ camera và địa chỉ HTTPS hoặc localhost.');
      const selectedId = cameraSelect.value;
      const constraints = selectedId ? { deviceId: { exact: selectedId } } : true;
      acquired = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
      if (version !== generation || disposed) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream = acquired; video.muted = true; video.srcObject = stream; await video.play(); video.classList.add('active');
      await waitForVideoFrame(version);
      if (version !== generation || disposed) { acquired.getTracks().forEach(track => track.stop()); return; }
      const track = stream.getVideoTracks()[0];
      const settings = track.getSettings();
      find('camera-source').textContent = (track.label || 'Camera đã chọn') + ' · ' + video.videoWidth + '×' + video.videoHeight;
      await refreshCameras(settings.deviceId || selectedId);
      if (version !== generation || disposed) { acquired.getTracks().forEach(track => track.stop()); return; }
      const data = await request(root.dataset.startUrl, { body: new FormData() });
      if (version !== generation || disposed) { acquired.getTracks().forEach(track => track.stop()); return; }
      runId = data.run_id; sequence = 0; failures = 0; blackFrames = 0; starting = false; running = true; lastResult = 0;
      stream.getVideoTracks()[0]?.addEventListener('ended', () => { if (running) { stopCamera(); message('Camera đã ngắt kết nối.'); } });
      state('starting'); void frame(version);
    } catch (error) {
      acquired?.getTracks().forEach(track => track.stop());
      if (version !== generation || disposed) return;
      stopCamera();
      const text = error.name === 'NotAllowedError' ? 'Bạn chưa cho phép camera. Hãy cấp quyền camera cho website trong trình duyệt.'
        : error.name === 'NotFoundError' ? 'Không tìm thấy camera trên thiết bị.'
        : error.name === 'NotReadableError' ? 'Không mở được camera. Hãy đóng ứng dụng khác đang sử dụng camera.'
        : error.name === 'OverconstrainedError' ? 'Camera đã chọn không còn khả dụng. Hãy chọn camera khác.' : error.message;
      state('error', text); message(text);
    }
  }
  cameraSelect.addEventListener('change', async () => {
    if (!running) return;
    const stopped = stopCamera(); const version = generation;
    await stopped;
    if (version === generation && !disposed) void startCamera();
  });
  navigator.mediaDevices?.addEventListener?.('devicechange', () => { void refreshCameras().catch(() => {}); });
  void refreshCameras().catch(() => {});
  start.addEventListener('click', startCamera); stop.addEventListener('click', () => { stopCamera(); message(); });
  const freshness = setInterval(() => {
    if (!running || !lastResult) return;
    const age = (Date.now() - lastResult) / 1000;
    find('frame-freshness').textContent = age.toFixed(1) + ' giây trước';
    if (age > 10) { state('stale', 'Không có kết quả AI mới. Không thể kết luận khu vực an toàn.'); overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height); }
  }, 1000);
  window.addEventListener('pagehide', () => { disposed = true; stopCamera(); clearInterval(freshness); audio?.close().catch(() => {}); });
  window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
  state('stopped'); renderEvents();
  void request(root.dataset.configUrl).then(data => {
    find('model-source').textContent = data.model_source;
    find('model-resolution').textContent = data.image_size + ' px';
    find('model-thresholds').textContent = 'Lửa ' + Math.round(data.fire_confidence * 100) + '% · Khói ' + Math.round(data.smoke_confidence * 100) + '%';
    find('model-confirmation').textContent = data.confirm_frames + ' / ' + data.confirmation_window + ' khung hình';
    for (const event of [...(data.events || [])].reverse()) events.set(event.id, event);
    renderEvents();
  }).catch(error => message(error.message));
})();
