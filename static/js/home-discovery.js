document.addEventListener('DOMContentLoaded', () => {
  const filterButton = document.getElementById('home-filter-toggle');
  const fields = document.getElementById('home-filter-fields');
  const narrowFilters = window.matchMedia('(max-width: 800px)');

  function setDisclosure(button, content, open) {
    button.setAttribute('aria-expanded', String(open));
    content.hidden = !open;
  }

  // Without JavaScript every filter stays visible.
  function syncFilters() {
    filterButton.hidden = !narrowFilters.matches;
    setDisclosure(filterButton, fields, !narrowFilters.matches);
    document.querySelector('.home-filter-heading h2').hidden = narrowFilters.matches;
  }
  filterButton.addEventListener('click', () => setDisclosure(filterButton, fields, fields.hidden));
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (narrowFilters.matches && !fields.hidden && document.getElementById('public-menu-toggle').getAttribute('aria-expanded') !== 'true') {
      setDisclosure(filterButton, fields, false);
      filterButton.focus();
    }
  });
  narrowFilters.addEventListener('change', syncFilters);
  syncFilters();

  const range = document.getElementById('price-filter');
  const price = document.getElementById('price-filter-value');
  function updatePrice() {
    price.textContent = `${new Intl.NumberFormat('vi-VN').format(range.value)} đ`;
    range.setAttribute('aria-valuetext', price.textContent);
  }
  range.addEventListener('input', updatePrice);
  updatePrice();
  document.getElementById('home-sort').addEventListener('change', () => {
    document.getElementById('home-filters').requestSubmit();
  });

  // Keep room links usable when an uploaded photo cannot be reached.
  document.querySelectorAll('.room-cover, .home-preview-image img').forEach((image) => {
    function showFallback() {
      image.hidden = true;
      const link = image.closest('.room-photo-link, .home-preview-image');
      if (!link || link.querySelector('.home-photo-placeholder')) return;
      const fallback = document.createElement('span');
      fallback.className = 'home-photo-placeholder';
      fallback.textContent = 'Ảnh đang cập nhật';
      link.append(fallback);
    }
    image.addEventListener('error', showFallback, { once: true });
    if (image.complete && image.naturalWidth === 0) showFallback();
  });
});
