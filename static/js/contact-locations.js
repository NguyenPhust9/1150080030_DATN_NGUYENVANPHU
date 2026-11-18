document.addEventListener('DOMContentLoaded', () => {
  const locations = document.querySelector('[data-contact-locations]');
  if (!locations) return;
  const choices = [...locations.querySelectorAll('[data-building-id]')];
  const map = document.getElementById('contact-map');
  const panel = document.getElementById('contact-map-panel');
  const name = document.getElementById('contact-map-name');
  const address = document.getElementById('contact-map-address');
  const directions = document.getElementById('contact-directions');
  const rooms = document.getElementById('contact-building-rooms');
  const openMap = document.getElementById('contact-open-map');
  const mobile = window.matchMedia('(max-width: 800px)');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function select(choice) {
    const data = choice.dataset;
    choices.forEach(item => {
      if (item === choice) item.setAttribute('aria-current', 'location');
      else item.removeAttribute('aria-current');
    });
    name.textContent = data.buildingName;
    address.textContent = data.buildingAddress;
    map.title = `Bản đồ tham khảo ${data.buildingName} — ${data.buildingAddress}`;
    if (map.getAttribute('src') !== data.mapEmbedUrl) map.src = data.mapEmbedUrl;
    directions.href = data.directionsUrl;
    rooms.href = data.roomsUrl;
    openMap.href = data.mapUrl;
  }

  choices.forEach(choice => choice.addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (!choice.hasAttribute('aria-current')) {
      select(choice);
      history.pushState(null, '', choice.href);
    }
    if (mobile.matches) {
      panel.focus({ preventScroll: true });
      panel.scrollIntoView({ block: 'start', behavior: reducedMotion.matches ? 'instant' : 'smooth' });
    }
  }));

  window.addEventListener('popstate', () => {
    const id = new URLSearchParams(window.location.search).get('building');
    select(choices.find(choice => choice.dataset.buildingId === id) || choices[0]);
  });
});
