/* Responsive navigation for the existing management routes. */
(() => {
  if (!document.body.classList.contains('management-app')) return;
  const sidebar = document.getElementById('admin-sidebar');
  const toggle = document.getElementById('admin-menu-toggle');
  const close = document.getElementById('admin-menu-close');
  const backdrop = document.getElementById('admin-nav-backdrop');
  const content = document.getElementById('main-content');
  if (!sidebar || !toggle || !close || !backdrop || !content) return;
  const narrow = window.matchMedia('(max-width: 1100px)');
  const focusable = container => [...container.querySelectorAll('a[href], button:not(:disabled), [tabindex="0"]')]
    .filter(element => element.getClientRects().length && !element.closest('[inert]'));

  function setMenu(open, returnFocus = false) {
    const isOpen = narrow.matches && open;
    document.body.classList.toggle('admin-nav-open', isOpen);
    toggle.setAttribute('aria-expanded', String(isOpen));
    backdrop.hidden = !isOpen;
    content.inert = isOpen;
    sidebar.inert = narrow.matches && !isOpen;
    if (narrow.matches && !isOpen) sidebar.setAttribute('aria-hidden', 'true');
    else sidebar.removeAttribute('aria-hidden');
    if (isOpen) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      close.focus({ preventScroll: true });
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      if (returnFocus && narrow.matches) toggle.focus({ preventScroll: true });
    }
  }
  document.body.classList.add('admin-enhanced');
  setMenu(false);
  toggle.addEventListener('click', () => setMenu(true));
  close.addEventListener('click', () => setMenu(false, true));
  backdrop.addEventListener('click', () => setMenu(false, true));
  narrow.addEventListener('change', () => setMenu(false));
  sidebar.addEventListener('click', event => {
    if (event.target.closest('a[href]') && narrow.matches) setMenu(false, true);
  });
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('admin-nav-open')) return;
    if (event.key === 'Escape') { event.preventDefault(); setMenu(false, true); }
    if (event.key === 'Tab') {
      const items = focusable(sidebar), first = items[0], last = items.at(-1);
      if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    }
  });
  sidebar.querySelectorAll('.nav-group').forEach((group, index) => {
    const button = group.querySelector('.nav-group-toggle');
    const links = group.querySelector('.nav-group-links');
    if (button && links) { links.id = `admin-nav-group-${index}`; button.setAttribute('aria-controls', links.id); }
  });
  sidebar.querySelectorAll('nav a.active').forEach(link => link.setAttribute('aria-current', 'page'));

  // The existing click/outside/Escape handlers remain; add keyboard menu movement.
  const trigger = document.getElementById('userPopoverTrigger');
  const popover = document.getElementById('userPopoverCard');
  if (!trigger || !popover) return;
  trigger.setAttribute('aria-controls', popover.id);
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.addEventListener('keydown', event => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    if (trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
    const items = focusable(popover);
    (event.key === 'ArrowUp' ? items.at(-1) : items[0])?.focus();
  });
  popover.addEventListener('keydown', event => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const items = focusable(popover), index = items.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  });
  popover.addEventListener('focusout', () => queueMicrotask(() => {
    if (!popover.contains(document.activeElement) && document.activeElement !== trigger) {
      popover.classList.remove('show'); trigger.setAttribute('aria-expanded', 'false');
    }
  }));
})();
