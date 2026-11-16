(() => {
  'use strict';
  const root = document.querySelector('.fire-monitor');
  if (!root) return;
  const find = (id) => root.querySelector('#' + id);
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value
    || document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
  const stream = find('camera-stream');
  const startButton = find('start-camera');
  const stopButton = find('stop-camera');
  const labels = {
    stopped: 'Đã dừng giám sát',
    starting: 'Đang khởi động camera và AI…',
    stopping: 'Đang dừng camera…',
    monitoring: 'Chưa phát hiện lửa/khói',
    detecting: 'Có dấu hiệu — đang xác minh',
    alert: 'CẢNH BÁO LỬA / KHÓI',
    error: 'Lỗi giám sát',
    disconnected: 'Mất kết nối giám sát',
    stale: 'Chưa có kết quả mới',
  };
  let snapshot = null, pending = '', timer = null, disposed = false, requestVersion = 0;
  let previousAlert = false, audioContext = null, streamFailed = false, lastStreamAttempt = 0, lastEvents = '';

  const hideStream = () => {
    stream.classList.remove('active');
    stream.removeAttribute('src');
  };
  const updateButtons = (state) => {
    const active = Boolean(snapshot?.running || snapshot?.loading || snapshot?.state === 'stopping');
    startButton.disabled = Boolean(pending || !snapshot || active || state === 'disconnected');
    stopButton.disabled = Boolean(pending || !active || state === 'stopping');
    root.setAttribute('aria-busy', String(Boolean(pending)));
  };
  const setState = (state, message = '') => {
    root.dataset.state = state;
    for (const name of ['monitoring', 'alert', 'detecting']) root.classList.toggle(name, state === name);
    find('camera-state').textContent = labels[state] || labels.error;
    find('ai-state').textContent = message || labels[state] || labels.error;
    find('safety-label').textContent = labels[state] || labels.error;
    find('camera-placeholder-title').textContent = state === 'stopped' ? 'Camera chưa hoạt động' : labels[state] || labels.error;
    find('camera-placeholder-text').textContent = message || (state === 'stopped'
      ? 'Nhấn “Bắt đầu giám sát” để mở webcam.' : 'Không có hình ảnh trực tiếp mới để hiển thị.');
    updateButtons(state);
  };
  const showMessage = (message) => {
    find('monitor-message').textContent = message;
    find('monitor-message').hidden = !message;
  };
  const beep = () => {
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.18, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.8);
      oscillator.connect(gain).connect(audioContext.destination);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.8);
    } catch (_) {
      // Browsers may block sound until a user gesture; visual alerts remain.
    }
  };
  const safeImageUrl = (value) => {
    if (typeof value !== 'string' || !value) return null;
    try {
      const url = new URL(value, window.location.href);
      return ['http:', 'https:'].includes(url.protocol) && url.origin === window.location.origin ? url.href : null;
    } catch (_) { return null; }
  };
  const renderEvents = (list) => {
    const items = Array.isArray(list) ? list.slice(0, 10) : [];
    const signature = JSON.stringify(items);
    if (signature === lastEvents) return;
    lastEvents = signature;
    const fragment = document.createDocumentFragment();
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'Chưa có cảnh báo trong phiên này.';
      fragment.append(empty);
    }
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      const url = safeImageUrl(item.image_url);
      const entry = document.createElement(url ? 'a' : 'div');
      entry.className = 'event-item';
      if (url) {
        entry.href = url;
        entry.target = '_blank';
        entry.rel = 'noopener noreferrer';
        const image = document.createElement('img');
        image.src = url;
        image.alt = 'Ảnh cảnh báo lửa hoặc khói';
        image.loading = 'lazy';
        entry.append(image);
      }
      const detail = document.createElement('span');
      const title = document.createElement('strong');
      const eventLabels = Array.isArray(item.labels) ? item.labels : [];
      title.textContent = eventLabels.map((label) => label === 'fire' ? 'Lửa' : label === 'smoke' ? 'Khói' : '')
        .filter(Boolean).join(', ') || 'Cảnh báo';
      const time = document.createElement('small');
      time.textContent = String(item.time || '');
      detail.append(title, time);
      const persistenceLabels = {
        queued: 'Đã lưu ảnh · Chờ đồng bộ',
        saving: 'Đã lưu ảnh · Đang đồng bộ',
        saved: 'Đã lưu vào hệ thống',
        unmapped: 'Chỉ lưu ảnh · Camera chưa gắn với bản đồ',
        failed: 'Chỉ lưu ảnh · Đồng bộ thất bại',
        queue_full: 'Chỉ lưu ảnh · Hàng đợi đồng bộ đầy',
      };
      if (Object.hasOwn(persistenceLabels, item.persistence_state)) {
        const persistence = document.createElement('small');
        persistence.className = 'event-persistence';
        persistence.dataset.state = item.persistence_state;
        // Never expose raw database exceptions or connection credentials.
        persistence.textContent = persistenceLabels[item.persistence_state];
        detail.append(persistence);
      }
      const webhookLabels = {
        disabled: 'Chưa bật gửi n8n', queued: 'n8n: Đang chờ gửi',
        sending: 'n8n: Đang tải ảnh và gửi', sent: 'n8n đã nhận cảnh báo',
        failed: 'n8n: Chưa xác nhận nhận được · Kiểm tra kết nối', queue_full: 'n8n: Hàng đợi đầy',
      };
      if (Object.hasOwn(webhookLabels, item.webhook_state)) {
        const delivery = document.createElement('small');
        delivery.textContent = webhookLabels[item.webhook_state];
        detail.append(delivery);
      }
      entry.append(detail);
      fragment.append(entry);
    }
    find('event-list').replaceChildren(fragment);
  };
  const renderPersistence = (data) => {
    const notice = find('persistence-status');
    const events = Array.isArray(data.events) ? data.events : [];
    const incomplete = events.some((event) => event && ['failed', 'unmapped', 'queue_full'].includes(event.persistence_state));
    const statistics = data.persistence || {};
    const waiting = Number.isFinite(statistics.pending) ? Math.max(0, statistics.pending) : 0;
    const pendingCount = waiting + (statistics.active ? 1 : 0);
    const failed = Number.isFinite(statistics.failed) ? Math.max(0, statistics.failed) : 0;
    const warning = incomplete || failed > 0;
    notice.classList.toggle('warning', warning);
    notice.textContent = warning
      ? 'Có cảnh báo mới chỉ lưu ảnh trên máy chủ, chưa lưu vào hệ thống/bản đồ. Xem trạng thái từng cảnh báo.'
      : pendingCount > 0 ? 'Đang đồng bộ ' + pendingCount + ' cảnh báo. Ảnh đã được lưu trên máy chủ.' : '';
    notice.hidden = !notice.textContent;
  };
  const renderConfig = (data) => {
    find('model-source').textContent = data.model_source || data.model_name || 'Chưa xác định';
    find('camera-source').textContent = 'Webcam ' + (data.camera_index ?? '—');
    find('model-resolution').textContent = data.image_size ? data.image_size + ' px' : '—';
    const percentage = (value) => Number.isFinite(value) ? Math.round(value * 100) + '%' : '—';
    find('model-thresholds').textContent = 'Lửa ' + percentage(data.fire_confidence) + ' · Khói ' + percentage(data.smoke_confidence);
    find('model-confirmation').textContent = data.confirm_frames && data.confirmation_window
      ? data.confirm_frames + ' / ' + data.confirmation_window + ' khung hình' : '—';
  };
  const attachStream = () => {
    if (stream.getAttribute('src')) return;
    if (streamFailed && Date.now() - lastStreamAttempt < 5000) return;
    lastStreamAttempt = Date.now();
    streamFailed = false;
    stream.src = root.dataset.streamUrl + '?t=' + lastStreamAttempt;
    stream.classList.add('active');
  };
  const render = (data) => {
    snapshot = data;
    renderConfig(data);
    renderEvents(data.events);
    renderPersistence(data);
    const frameAge = data.frame_age_seconds;
    const fresh = data.result_stale === false && Number.isFinite(frameAge) && frameAge <= 10;
    let state = data.state === 'safe' ? 'monitoring' : data.state;
    if (!Object.hasOwn(labels, state)) state = 'error';
    if (['monitoring', 'detecting', 'alert'].includes(state) && (!data.running || !fresh)) state = 'stale';
    if (pending) state = pending;
    const visibleResult = Boolean(data.running && fresh && !pending);
    find('fps-label').textContent = visibleResult && Number.isFinite(data.fps) ? data.fps + ' FPS' : '— FPS';
    find('detection-count').textContent = visibleResult && Array.isArray(data.detections) ? data.detections.length : '—';
    find('frame-freshness').textContent = Number.isFinite(frameAge) ? frameAge.toFixed(1) + ' giây trước' : 'Chưa có khung hình được phân tích';
    if (visibleResult && !['error', 'stopping', 'stopped'].includes(state)) attachStream();
    else hideStream();
    if (streamFailed && visibleResult) state = 'disconnected';
    const message = state === 'error' ? data.error || 'Không đọc được trạng thái AI.'
      : state === 'stale' ? 'Không có kết quả mới. Không thể kết luận khu vực an toàn.'
        : state === 'disconnected' ? 'Luồng hình ảnh bị ngắt; đang thử kết nối lại.' : '';
    setState(state, message);
    if (state === 'alert' && !previousAlert) beep();
    previousAlert = state === 'alert';
  };
  const requestJson = async (url, options = {}) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, {
        ...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { Accept: 'application/json', ...options.headers },
      });
      if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error('Phiên đăng nhập hết hạn hoặc bạn không có quyền. Hãy tải lại trang và đăng nhập.');
      }
      if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error('Máy chủ không trả về trạng thái AI hợp lệ. Hãy tải lại trang.');
      }
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.message || data.error || 'Thao tác thất bại (HTTP ' + response.status + ').');
      if (typeof data.state !== 'string' || typeof data.running !== 'boolean') {
        throw new Error('Trạng thái giám sát không hợp lệ. Không thể xác nhận kết quả AI.');
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Máy chủ phản hồi quá chậm. Chưa nhận được kết quả giám sát mới.');
      throw error;
    } finally { clearTimeout(timeout); }
  };
  const disconnected = (error) => {
    hideStream();
    previousAlert = false;
    find('fps-label').textContent = '— FPS';
    find('detection-count').textContent = '—';
    find('frame-freshness').textContent = 'Không nhận được dữ liệu mới';
    const message = error instanceof TypeError
      ? 'Không kết nối được máy chủ. Đang tự thử lại; không có kết quả giám sát mới.' : error.message;
    setState('disconnected', message);
    showMessage(message);
  };
  const poll = async () => {
    if (disposed) return;
    const version = requestVersion;
    if (!pending) {
      try {
        const data = await requestJson(root.dataset.statusUrl);
        if (!disposed && version === requestVersion && !pending) { render(data); showMessage(''); }
      } catch (error) {
        if (!disposed && version === requestVersion && !pending) disconnected(error);
      }
    }
    // An action schedules its own poll; a superseded request must not create a second loop.
    if (!disposed && version === requestVersion) timer = setTimeout(poll, 1000);
  };
  const controlCamera = async (action) => {
    if (pending || disposed) return;
    pending = action === 'start' ? 'starting' : 'stopping';
    requestVersion += 1;
    clearTimeout(timer);
    hideStream();
    showMessage('');
    setState(pending);
    try {
      const data = await requestJson(root.dataset[action + 'Url'], { method: 'POST', headers: { 'X-CSRFToken': csrf } });
      pending = '';
      if (!disposed) render(data);
    } catch (error) {
      pending = '';
      if (!disposed) disconnected(error);
    } finally {
      if (!disposed) { clearTimeout(timer); timer = setTimeout(poll, 1000); }
    }
  };
  stream.addEventListener('error', () => {
    if (disposed || !stream.getAttribute('src')) return;
    streamFailed = true;
    hideStream();
    setState('disconnected', 'Luồng hình ảnh bị ngắt; đang thử kết nối lại.');
  });
  startButton.addEventListener('click', () => controlCamera('start'));
  stopButton.addEventListener('click', () => controlCamera('stop'));
  window.addEventListener('pagehide', () => {
    disposed = true;
    clearTimeout(timer);
    hideStream();
    // Leaving this page must not silently stop monitoring for other operators.
    audioContext?.close().catch(() => {});
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) { disposed = false; poll(); }
  });
  poll();
})();
