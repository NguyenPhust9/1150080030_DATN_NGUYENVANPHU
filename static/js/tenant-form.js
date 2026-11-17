(() => {
  'use strict';
  const dialog = document.querySelector('.tenant-dialog');
  if (!dialog) return;
  dialog.classList.add('enhanced');
  const tabs = [...dialog.querySelectorAll('[data-tenant-tab]')];
  const panels = [...dialog.querySelectorAll('.tenant-tab-panel')];
  const activate = id => {
    for (const tab of tabs) {
      const selected = tab.dataset.tenantTab === id;
      tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
    }
    for (const panel of panels) panel.hidden = panel.id !== id;
  };
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener('click', () => activate(tab.dataset.tenantTab));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1)
        : tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      activate(next.dataset.tenantTab); next.focus();
    });
  }
  const cards = [...dialog.querySelectorAll('.tenant-image-card')];
  const updateCount = () => {
    const count = cards.filter(card => card.querySelector('input[type=file]').files.length
      || (card.dataset.existing === 'true' && !card.querySelector('input[type=checkbox]')?.checked)).length;
    dialog.querySelector('.tenant-image-status').textContent = count
      ? `Đã có ${count}/2 ảnh CCCD · Có thể bổ sung sau` : 'Ảnh CCCD không bắt buộc';
  };
  for (const card of cards) {
    const file = card.querySelector('input[type=file]'), remove = card.querySelector('input[type=checkbox]');
    const image = card.querySelector('img'), placeholder = card.querySelector('.tenant-image-preview span');
    const clear = card.querySelector('.tenant-clear-selection');
    const original = image.getAttribute('src');
    let blobUrl;
    const refresh = () => {
      if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
      const selected = file.files[0];
      const source = selected ? (blobUrl = URL.createObjectURL(selected)) : (!remove?.checked && original);
      if (source) image.src = source; else image.removeAttribute('src');
      image.hidden = !source; placeholder.hidden = Boolean(source); clear.hidden = !selected;
      updateCount();
    };
    file.addEventListener('change', () => { if (file.files.length && remove) remove.checked = false; refresh(); });
    remove?.addEventListener('change', () => { if (remove.checked) file.value = ''; refresh(); });
    clear.addEventListener('click', () => { file.value = ''; refresh(); });
    window.addEventListener('pagehide', () => { if (blobUrl) URL.revokeObjectURL(blobUrl); });
    refresh();
  }
  // Native validation can find a required field even while its tab is hidden.
  dialog.addEventListener('invalid', event => {
    const panel = event.target.closest('.tenant-tab-panel');
    if (panel) activate(panel.id);
  }, true);
  const firstError = dialog.querySelector('.tenant-tab-panel .errorlist');
  activate(firstError?.closest('.tenant-tab-panel').id || 'tenant-info');
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') dialog.querySelector('.tenant-close').click();
    if (event.key !== 'Tab') return;
    const focusable = [...dialog.querySelectorAll('a[href],button,input,select,summary')]
      .filter(element => !element.disabled && element.tabIndex >= 0 && element.getClientRects().length);
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  });
  dialog.querySelector('.tenant-close').focus();
})();
