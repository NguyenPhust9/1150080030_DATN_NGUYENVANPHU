document.addEventListener('DOMContentLoaded', () => {
  const button = document.getElementById('public-menu-toggle');
  const navigation = document.getElementById('public-nav');
  if (!button || !navigation) return;
  const narrow = window.matchMedia('(max-width: 1100px)');

  function setOpen(open) {
    button.setAttribute('aria-expanded', String(open));
    navigation.hidden = !open;
  }
  function sync() {
    button.hidden = !narrow.matches;
    setOpen(!narrow.matches);
  }
  button.addEventListener('click', () => setOpen(navigation.hidden));
  navigation.addEventListener('click', (event) => {
    if (narrow.matches && event.target.closest('a')) setOpen(false);
  });
  document.addEventListener('click', (event) => {
    if (narrow.matches && !event.target.closest('.public-header')) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && narrow.matches && !navigation.hidden) {
      setOpen(false);
      button.focus();
    }
  });
  narrow.addEventListener('change', sync);
  sync();
});
