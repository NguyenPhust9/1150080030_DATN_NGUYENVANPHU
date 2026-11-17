document.addEventListener('DOMContentLoaded', () => {
  const menuButton = document.getElementById('public-menu-toggle');
  const navigation = document.getElementById('public-nav');
  const filterButton = document.getElementById('home-filter-toggle');
  const fields = document.getElementById('home-filter-fields');
  const narrowNavigation = window.matchMedia('(max-width: 1100px)');
  const narrowFilters = window.matchMedia('(max-width: 800px)');

  function setDisclosure(button, content, open) {
    button.setAttribute('aria-expanded', String(open));
    content.hidden = !open;
  }

  // Without JavaScript the navigation and every filter stay visible.
  function syncNavigation() {
    menuButton.hidden = !narrowNavigation.matches;
    setDisclosure(menuButton, navigation, !narrowNavigation.matches);
  }
  function syncFilters() {
    filterButton.hidden = !narrowFilters.matches;
    setDisclosure(filterButton, fields, !narrowFilters.matches);
    document.querySelector('.home-filter-heading h2').hidden = narrowFilters.matches;
  }
  menuButton.addEventListener('click', () => setDisclosure(menuButton, navigation, navigation.hidden));
  filterButton.addEventListener('click', () => setDisclosure(filterButton, fields, fields.hidden));
  navigation.addEventListener('click', (event) => {
    if (narrowNavigation.matches && event.target.closest('a')) setDisclosure(menuButton, navigation, false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (narrowNavigation.matches && !navigation.hidden) {
      setDisclosure(menuButton, navigation, false);
      menuButton.focus();
    } else if (narrowFilters.matches && !fields.hidden) {
      setDisclosure(filterButton, fields, false);
      filterButton.focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (narrowNavigation.matches && !event.target.closest('.public-header')) setDisclosure(menuButton, navigation, false);
  });
  narrowNavigation.addEventListener('change', syncNavigation);
  narrowFilters.addEventListener('change', syncFilters);
  syncNavigation();
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
