(() => {
  const viewer = document.getElementById('chat-image-viewer');
  const image = document.getElementById('image-viewer-image');
  const stage = document.getElementById('image-viewer-stage');
  const name = document.getElementById('image-viewer-name');
  const reset = document.getElementById('image-zoom-reset');
  if (!viewer || !image || !stage) return;
  let scale = 1;

  function setScale(value) {
    scale = Math.max(.5, Math.min(4, value));
    image.style.transform = `scale(${scale})`;
    reset.textContent = `${Math.round(scale * 100)}%`;
  }
  function close() {
    viewer.close();
    image.removeAttribute('src');
    setScale(1);
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('.chat-image-link');
    if (!link) return;
    event.preventDefault();
    const thumbnail = link.querySelector('img');
    image.src = thumbnail.currentSrc || thumbnail.src || link.href;
    image.alt = thumbnail.alt || 'Hình ảnh';
    name.textContent = thumbnail.alt || 'Hình ảnh';
    setScale(1);
    viewer.showModal();
  });
  document.getElementById('image-zoom-in').addEventListener('click', () => setScale(scale + .25));
  document.getElementById('image-zoom-out').addEventListener('click', () => setScale(scale - .25));
  reset.addEventListener('click', () => setScale(1));
  document.getElementById('image-viewer-close').addEventListener('click', close);
  viewer.addEventListener('cancel', event => { event.preventDefault(); close(); });
  viewer.addEventListener('click', event => { if (event.target === viewer) close(); });
  stage.addEventListener('wheel', event => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setScale(scale + (event.deltaY < 0 ? .25 : -.25));
  }, {passive: false});
})();
