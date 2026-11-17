document.addEventListener("DOMContentLoaded", () => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  document.querySelectorAll("[data-room-carousel]").forEach((carousel) => {
    const track = carousel.querySelector(".compact-room-grid");
    const controls = carousel.querySelector(".room-carousel-controls");
    const previous = carousel.querySelector("[data-room-prev]");
    const next = carousel.querySelector("[data-room-next]");
    let pointer = null;
    let suppressClick = false;

    function updateControls() {
      const limit = track.scrollWidth - track.clientWidth;
      controls.hidden = limit <= 1;
      previous.disabled = track.scrollLeft <= 1;
      next.disabled = track.scrollLeft >= limit - 1;
    }

    function pageSize() {
      const card = track.querySelector(".room-card");
      const styles = getComputedStyle(track);
      const step = card.getBoundingClientRect().width + parseFloat(styles.columnGap);
      const width = track.clientWidth - parseFloat(styles.paddingLeft) - parseFloat(styles.paddingRight);
      return Math.max(1, Math.floor((width + parseFloat(styles.columnGap)) / step)) * step;
    }

    function scrollPage(direction) {
      track.scrollBy({ left: direction * pageSize(), behavior: reducedMotion.matches ? "instant" : "smooth" });
    }

    previous.addEventListener("click", () => scrollPage(-1));
    next.addEventListener("click", () => scrollPage(1));
    track.addEventListener("scroll", updateControls, { passive: true });
    new ResizeObserver(updateControls).observe(track);

    track.addEventListener("keydown", (event) => {
      if (event.target !== track) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        scrollPage(event.key === "ArrowLeft" ? -1 : 1);
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        track.scrollTo({ left: event.key === "Home" ? 0 : track.scrollWidth, behavior: reducedMotion.matches ? "instant" : "smooth" });
      }
    });

    // Touch and trackpad gestures use native scrolling; only mouse dragging needs handling.
    track.addEventListener("pointerdown", (event) => {
      suppressClick = false;
      if (event.pointerType !== "mouse" || event.button !== 0 || event.target.closest("button")) return;
      if (event.clientY >= track.getBoundingClientRect().top + track.clientHeight) return;
      pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, left: track.scrollLeft, dragging: false };
    });

    track.addEventListener("pointermove", (event) => {
      if (!pointer || event.pointerId !== pointer.id) return;
      const deltaX = event.clientX - pointer.x;
      if (!pointer.dragging) {
        if (Math.abs(deltaX) < 6 || Math.abs(deltaX) <= Math.abs(event.clientY - pointer.y)) return;
        pointer.dragging = true;
        suppressClick = true;
        track.setPointerCapture(event.pointerId);
        track.classList.add("is-dragging");
      }
      event.preventDefault();
      track.scrollLeft = pointer.left - deltaX;
    });

    function finishDrag(event) {
      if (!pointer || event.pointerId !== pointer.id) return;
      pointer = null;
      track.classList.remove("is-dragging");
      if (track.hasPointerCapture(event.pointerId)) track.releasePointerCapture(event.pointerId);
    }

    track.addEventListener("pointerup", finishDrag);
    track.addEventListener("pointercancel", finishDrag);
    track.addEventListener("lostpointercapture", finishDrag);
    track.addEventListener("pointerleave", (event) => {
      if (pointer && !pointer.dragging) finishDrag(event);
    });
    track.addEventListener("dragstart", (event) => event.preventDefault());
    track.addEventListener("click", (event) => {
      if (!suppressClick || event.detail === 0) return;
      event.preventDefault();
      event.stopPropagation();
      suppressClick = false;
    }, true);

    updateControls();
  });
});
