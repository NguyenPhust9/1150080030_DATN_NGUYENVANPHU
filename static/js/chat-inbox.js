(() => {
  const shell = document.querySelector('.messenger');
  if (!shell) return;
  const list = shell.querySelector('.conversation-list');
  const search = document.getElementById('conversation-search');
  let socket, timer, retry, busy = false, stopped = false;
  let fingerprint = '';
  let heartbeat;
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function render(items) {
    const active = items.find(item => item.id === shell.dataset.activeId);
    const peerStatus = document.getElementById('peer-presence');
    if (active?.presence && peerStatus) {
      peerStatus.textContent = active.presence.label;
      peerStatus.classList.toggle('online', active.presence.online);
      document.querySelector('.chat-head > .conversation-avatar')?.classList.toggle('is-online', active.presence.online);
    }
    const signature = JSON.stringify(items);
    if (signature === fingerprint) return;
    fingerprint = signature;
    const oldScroll = list.scrollTop;
    const oldFirst = list.querySelector('.conversation-card')?.getAttribute('href');
    const focused = list.contains(document.activeElement) ? document.activeElement.getAttribute('href') : null;
    const fragment = document.createDocumentFragment();
    items.forEach(item => {
      const card = el('a', 'conversation-card' + (item.id === shell.dataset.activeId ? ' selected' : ''));
      card.href = `${shell.dataset.chatBase}${item.id}/`;
      card.dataset.search = `${item.name} ${item.subject}`;
      const avatar = el('span', 'conversation-avatar', Array.from(item.name)[0]?.toUpperCase() || '?');
      avatar.classList.toggle('is-online', !!item.presence?.online);
      const main = el('div', 'conversation-main');
      const title = el('div', 'conversation-title');
      title.append(el('strong', '', item.name), el('time', '', item.time));
      main.append(title, el('p', '', item.preview));
      if (item.presence) {
        const presence = el('span', 'conversation-presence' + (item.presence.online ? ' online' : ''), item.presence.label);
        title.after(presence);
      }
      card.append(avatar, main);
      if (item.unread) card.append(el('span', 'unread-dot', String(item.unread)));
      fragment.append(card);
    });
    if (!items.length) fragment.append(el('div', 'inbox-empty', 'Chưa có cuộc trò chuyện. Bấm nút soạn tin để bắt đầu.'));
    const empty = el('p', 'inbox-empty', 'Không tìm thấy cuộc trò chuyện.');
    empty.id = 'search-empty';
    empty.hidden = true;
    fragment.append(empty);
    list.replaceChildren(fragment);
    shell.querySelector('.inbox-label span').textContent = items.length;
    const newFirst = list.querySelector('.conversation-card')?.getAttribute('href');
    list.scrollTop = oldFirst !== newFirst ? 0 : oldScroll;
    if (focused) Array.from(list.querySelectorAll('a')).find(a => a.getAttribute('href') === focused)?.focus({preventScroll:true});
    search.dispatchEvent(new Event('input'));
  }
  async function sync() {
    if (busy || stopped) return;
    busy = true;
    try {
      const response = await fetch(shell.dataset.inboxUrl, {
        headers: {Accept: 'application/json'}, cache: 'no-store', signal: AbortSignal.timeout(10000)
      });
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) return;
      const data = await response.json();
      render(data.conversations);
    } catch { /* Retry automatically, preserving the current list. */ }
    finally { busy = false; }
  }
  function connect() {
    if (stopped) return;
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat/inbox/`);
    socket.onopen = () => {
      clearInterval(heartbeat);
      const ping = () => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type: 'presence.ping'})); };
      ping();
      heartbeat = setInterval(ping, 20000);
      sync();
    };
    socket.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'call.signal' || data.type === 'call.error') {
          window.dispatchEvent(new CustomEvent('chat:call-signal', {detail: data}));
          return;
        }
        sync(); window.dispatchEvent(new Event('chat:inbox-updated'));
      } catch { sync(); }
    };
    socket.onclose = () => { clearInterval(heartbeat); if (!stopped) retry = setTimeout(connect, 3000); };
    socket.onerror = () => socket.close();
  }
  function start() {
    stopped = false;
    clearInterval(timer);
    timer = setInterval(sync, 2000);
    connect();
    sync();
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
  window.addEventListener('online', sync);
  window.chatCallSend = payload => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({type: 'call.signal', ...payload}));
    return true;
  };
  window.addEventListener('chat:message-added', sync);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); clearInterval(heartbeat); clearTimeout(retry); socket?.close(); });
  window.addEventListener('pageshow', () => { if (stopped) start(); });
  start();
})();
