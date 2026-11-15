(() => {
  const overlay = document.getElementById("site-loading");
  if (!overlay) return;
  const hide = () => overlay.classList.add("is-hidden");
  const show = () => overlay.classList.remove("is-hidden");

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hide, { once: true });
  } else {
    hide();
  }
  window.addEventListener("pageshow", hide);

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.target === "_blank" || link.hasAttribute("download")) return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || (url.pathname === window.location.pathname && url.search === window.location.search && url.hash)) return;
    window.setTimeout(show, 400);
  });

  document.addEventListener("submit", (event) => {
    if (event.defaultPrevented || !event.target.checkValidity()) return;
    window.setTimeout(show, 400);
  });
})();
