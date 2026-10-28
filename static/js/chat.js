(() => {
  const box = document.getElementById('chat-messages');
  if (!box) return;
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const state = document.getElementById('connection-state');
  const error = document.getElementById('chat-error');
  const me = box.dataset.userId;
  const imageInput = document.getElementById('chat-image-input');
  const imageButton = document.getElementById('chat-image-toggle');
  const preview = document.getElementById('chat-attachment-preview');
  let attachments = [];
  let previewUrls = [];
  let socket, reconnectTimer, syncing = false, sending = false, stopped = false;
  let cursor = box.lastElementChild?.dataset.messageId || '';
  box.scrollTop = box.scrollHeight;

  function append(data, advanceCursor = false) {
    const exists = box.querySelector(`[data-message-id="${data.id}"]`);
    if (advanceCursor) cursor = data.id;
    if (exists) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
    document.getElementById('empty-chat')?.remove();
    const item = document.createElement('article');
    item.className = 'chat-message' + (data.sender_id === me ? ' mine' : '');
    item.dataset.messageId = data.id;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    if (data.images?.length) {
      const grid = document.createElement('div');
      grid.className = 'chat-image-grid';
      data.images.forEach(image => {
        const link = document.createElement('a');
        link.className = 'chat-image-link';
        link.href = image.url;
        link.title = 'Xem ảnh lớn';
        const img = document.createElement('img');
        img.src = image.url;
        img.alt = image.name || 'Hình ảnh';
        link.append(img);
        grid.append(link);
      });
      bubble.append(grid);
    }
    if (data.content) {
      const text = document.createElement('div');
      text.className = 'chat-text';
      text.textContent = data.content;
      bubble.append(text);
    }
    const info = document.createElement('div');
    info.className = 'chat-info';
    info.textContent = `${data.sender_name} · ${data.created_at}${data.sender_id === me ? ' · Đã gửi' : ''}`;
    item.append(bubble, info);
    box.append(item);
    if (nearBottom || data.sender_id === me) box.scrollTop = box.scrollHeight;
    const card = document.querySelector('.conversation-card.selected');
    if (card) {
      card.querySelector('.conversation-main p').textContent = data.content || '📷 Hình ảnh';
      card.querySelector('time').textContent = data.created_at.split(' ')[0];
    }
    window.dispatchEvent(new Event('chat:message-added'));
  }

  function showError(text) { error.textContent = text; error.hidden = false; }
  function renderPreview() {
    previewUrls.forEach(url => URL.revokeObjectURL(url));
    previewUrls = [];
    if (!preview) return;
    preview.replaceChildren();
    preview.hidden = !attachments.length;
    attachments.forEach((file, index) => {
      const item = document.createElement('div');
      item.className = 'attachment-item';
      const img = document.createElement('img');
      const url = URL.createObjectURL(file);
      previewUrls.push(url);
      img.src = url;
      img.alt = file.name;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Bỏ ảnh ${file.name}`);
      remove.addEventListener('click', () => { if (!sending) { attachments.splice(index, 1); renderPreview(); } });
      item.append(img, remove);
      preview.append(item);
    });
    const note = document.createElement('span');
    note.className = 'attachment-note';
    note.textContent = `${attachments.length}/5 ảnh · JPG, PNG, WebP · Tối đa 10 MB/ảnh`;
    preview.append(note);
  }
  function addImages(files) {
    if (sending) return;
    const selected = Array.from(files);
    if (attachments.length + selected.length > 5) { showError('Mỗi lần gửi tối đa 5 ảnh.'); return; }
    if (selected.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
      showError('Chỉ hỗ trợ ảnh JPG, PNG và WebP.'); return;
    }
    if (selected.some(file => file.size > 10 * 1024 * 1024)) { showError('Mỗi ảnh không được vượt quá 10 MB.'); return; }
    attachments.push(...selected);
    error.hidden = true;
    renderPreview();
    input.focus();
  }
  imageButton?.addEventListener('click', () => imageInput.click());
  imageInput?.addEventListener('change', () => { addImages(imageInput.files); imageInput.value = ''; });
  input?.addEventListener('paste', event => {
    const files = Array.from(event.clipboardData?.files || []).filter(file => file.type.startsWith('image/'));
    if (files.length) { event.preventDefault(); addImages(files); }
  });
  form?.addEventListener('dragover', event => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault();
  });
  form?.addEventListener('drop', event => {
    if (event.dataTransfer?.files.length) { event.preventDefault(); addImages(event.dataTransfer.files); }
  });

  async function sync() {
    if (syncing || stopped) return;
    syncing = true;
    try {
      const url = new URL(box.dataset.updatesUrl, location.origin);
      if (cursor) url.searchParams.set('after', cursor);
      const response = await fetch(url, {headers: {Accept: 'application/json'}, cache: 'no-store', signal: AbortSignal.timeout(10000)});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error();
      const data = await response.json();
      data.messages.forEach(message => append(message, true));
      window.dispatchEvent(new CustomEvent('chat:reactions', {detail: data.reactions || {}}));
      if (socket?.readyState !== WebSocket.OPEN && form) {
        state.textContent = 'Đang đồng bộ tin nhắn';
        state.style.color = '#087b59';
      }
    } catch {
      if (socket?.readyState !== WebSocket.OPEN && form) {
        state.textContent = 'Kết nối gián đoạn, đang thử lại…';
        state.style.color = '#b45309';
      }
    } finally { syncing = false; }
  }

  function connect() {
    if (stopped || !form) return;
    try {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat/${box.dataset.conversationId}/`);
      socket.onopen = () => {
        state.textContent = 'Đã kết nối';
        state.style.color = '#087b59';
        sync();
      };
      socket.onmessage = event => {
        try { const data = JSON.parse(event.data); if (data.type === 'message') { append(data); sync(); } else if (data.type === 'reactions.updated') sync(); } catch { sync(); }
      };
      socket.onclose = () => {
        if (!stopped) { sync(); reconnectTimer = setTimeout(connect, 3000); }
      };
      socket.onerror = () => socket.close();
    } catch { reconnectTimer = setTimeout(connect, 3000); }
  }

  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const value = input.value.trim();
    if ((!value && !attachments.length) || sending) return;
    sending = true;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    if (imageButton) imageButton.disabled = true;
    error.hidden = true;
    const body = new FormData(form);
    body.set('message', value);
    body.delete('images');
    attachments.forEach(file => body.append('images', file));
    try {
      const response = await fetch(form.action, {method: 'POST', body, headers: {Accept: 'application/json'}});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error();
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Chưa gửi được tin nhắn. Vui lòng thử lại.');
      append(data.message);
      attachments = [];
      renderPreview();
      if (input.value.trim() === value) input.value = '';
      input.style.height = 'auto';
      input.focus();
      sync();
    } catch (failure) {
      showError(failure.message && failure.message !== 'Failed to fetch' ? failure.message : 'Chưa gửi được tin nhắn. Nội dung và ảnh vẫn được giữ lại, vui lòng thử lại.');
    } finally { sending = false; button.disabled = false; if (imageButton) imageButton.disabled = false; }
  });
  input?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
  });
  input?.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 130) + 'px'; });
  let timer;
  function startTimer() { clearInterval(timer); timer = setInterval(sync, 2000); }
  startTimer();
  window.addEventListener('chat:inbox-updated', sync);
  window.addEventListener('pageshow', () => { if (stopped) { stopped = false; startTimer(); connect(); sync(); } });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
  window.addEventListener('online', sync);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); clearTimeout(reconnectTimer); socket?.close(); });
  connect();
  sync();
})();
