(() => {
  const box = document.getElementById('chat-messages');
  if (!box) return;
  const input = document.getElementById('chat-input');
  const toggle = document.getElementById('emoji-toggle');
  const error = document.getElementById('chat-error');
  const closed = box.dataset.closed === 'true';
  const emojis = ['😀','😃','😁','😂','🤣','😊','🥰','😍','😘','😎','🥳','🤔','😅','😢','😭','😮','😡','🙏','👍','👎','👏','💪','👌','🤝','❤️','💙','💕','💯','🎉','✨','🔥','✅','🏠','🔑','☀️','🌙','🌸','🍀','☕','🎂'];
  const reactions = ['👍','❤️','😂','😮','😢','😡'];
  const names = ['Thích', 'Yêu thích', 'Haha', 'Ngạc nhiên', 'Buồn', 'Tức giận'];
  let anchor, messageId, selectionStart = 0, selectionEnd = 0;
  const pending = new Set();
  const picker = document.createElement('div');
  picker.className = 'emoji-picker';
  picker.hidden = true;
  picker.setAttribute('role', 'dialog');
  picker.setAttribute('aria-label', 'Chọn biểu tượng cảm xúc');
  document.body.append(picker);

  function close(restoreFocus = false) {
    picker.hidden = true;
    toggle?.setAttribute('aria-expanded', 'false');
    if (restoreFocus) anchor?.focus();
  }
  function open(target, id = null) {
    if (!picker.hidden && anchor === target) { close(); return; }
    anchor = target;
    messageId = id;
    if (!id && input) { selectionStart = input.selectionStart; selectionEnd = input.selectionEnd; }
    picker.replaceChildren();
    picker.classList.toggle('reaction-picker', !!id);
    const title = document.createElement('strong');
    title.textContent = id ? 'Thả cảm xúc' : 'Biểu tượng cảm xúc';
    picker.append(title);
    const grid = document.createElement('div');
    grid.className = 'emoji-grid';
    (id ? reactions : emojis).forEach((emoji, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = emoji;
      button.title = id ? names[index] : emoji;
      button.setAttribute('aria-label', button.title);
      button.addEventListener('click', () => {
        if (messageId) { const currentId = messageId; close(true); react(currentId, emoji); }
        else {
          if (input.value.length - (selectionEnd - selectionStart) + emoji.length > input.maxLength) return;
          input.setRangeText(emoji, selectionStart, selectionEnd, 'end');
          selectionStart = selectionEnd = input.selectionEnd;
          input.dispatchEvent(new Event('input', {bubbles: true}));
          close();
          input.focus();
        }
      });
      grid.append(button);
    });
    picker.append(grid);
    picker.hidden = false;
    toggle?.setAttribute('aria-expanded', id ? 'false' : 'true');
    const rect = target.getBoundingClientRect();
    picker.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - picker.offsetWidth - 8)) + 'px';
    picker.style.top = Math.max(8, rect.top - picker.offsetHeight - 9) + 'px';
    grid.firstElementChild?.focus();
  }
  toggle?.addEventListener('click', () => open(toggle));
  function decorate(item) {
    if (item.querySelector('.message-reactions')) return;
    if (!closed) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'message-react-button';
      button.textContent = '☺';
      button.title = 'Thả cảm xúc';
      button.setAttribute('aria-label', 'Thả cảm xúc cho tin nhắn');
      button.addEventListener('click', () => open(button, item.dataset.messageId));
      item.append(button);
    }
    const badges = document.createElement('div');
    badges.className = 'message-reactions';
    const content = document.createElement('div');
    content.className = 'message-content';
    const bubble = item.querySelector('.chat-bubble');
    bubble.before(content);
    content.append(bubble, badges);
  }
  function render(id, groups) {
    const item = box.querySelector(`[data-message-id="${id}"]`);
    if (!item) return;
    decorate(item);
    const badges = item.querySelector('.message-reactions');
    const signature = JSON.stringify(groups);
    if (badges.dataset.signature === signature) return;
    badges.dataset.signature = signature;
    badges.replaceChildren();
    groups.forEach(group => {
      const badge = document.createElement('button');
      badge.type = 'button';
      badge.className = 'reaction-badge' + (group.mine ? ' mine' : '');
      badge.textContent = `${group.emoji} ${group.count}`;
      badge.title = group.users.join(', ') + (group.mine ? ' · Bấm lại để gỡ cảm xúc của bạn' : '');
      badge.setAttribute('aria-label', badge.title);
      badge.setAttribute('aria-pressed', String(group.mine));
      badge.disabled = closed;
      badge.addEventListener('click', () => react(id, group.emoji));
      badges.append(badge);
    });
  }
  async function react(id, emoji) {
    if (pending.has(id) || closed) return;
    pending.add(id);
    try {
      const body = new FormData();
      body.set('emoji', emoji);
      body.set('csrfmiddlewaretoken', document.querySelector('#chat-form [name=csrfmiddlewaretoken]').value);
      const response = await fetch(`${box.dataset.chatBase}tin-nhan/${id}/cam-xuc/`, {
        method: 'POST', body, headers: {Accept: 'application/json'}, signal: AbortSignal.timeout(10000)
      });
      if (!response.ok) throw new Error();
      const data = await response.json();
      render(data.message_id, data.reactions);
      error.hidden = true;
    } catch {
      error.textContent = 'Chưa cập nhật được cảm xúc. Vui lòng thử lại.';
      error.hidden = false;
    } finally { pending.delete(id); }
  }
  box.querySelectorAll('[data-message-id]').forEach(decorate);
  new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
    if (node.nodeType === 1 && node.matches('[data-message-id]')) decorate(node);
  }))).observe(box, {childList: true});
  window.addEventListener('chat:reactions', event => {
    box.querySelectorAll('[data-message-id]').forEach(item => render(item.dataset.messageId, event.detail[item.dataset.messageId] || []));
  });
  document.addEventListener('click', event => { if (!picker.contains(event.target) && !anchor?.contains(event.target)) close(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !picker.hidden) { event.stopPropagation(); close(true); } });
  window.addEventListener('resize', () => close());
  box.addEventListener('scroll', () => close(), {passive: true});
})();
