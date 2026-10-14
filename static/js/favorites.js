document.addEventListener("DOMContentLoaded", () => {
  const storageKey = "ql_phong_favorites";
  let favorites = [];

  try {
    favorites = JSON.parse(localStorage.getItem(storageKey) || "[]");
  } catch (error) {
    favorites = [];
  }

  favorites = [...new Set(favorites.map(String))];
  const buttons = [...document.querySelectorAll("[data-favorite-room]")];
  const count = document.getElementById("favorite-count");

  function updateFavoriteUi() {
    buttons.forEach((button) => {
      const active = favorites.includes(button.dataset.favoriteRoom);
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.title = active ? "Bỏ khỏi yêu thích" : "Lưu phòng yêu thích";
    });
    if (count) count.textContent = favorites.length;
  }

  buttons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const roomId = button.dataset.favoriteRoom;
      const index = favorites.indexOf(roomId);
      if (index >= 0) favorites.splice(index, 1);
      else favorites.push(roomId);
      localStorage.setItem(storageKey, JSON.stringify(favorites));
      updateFavoriteUi();

      if (new URLSearchParams(location.search).get("favorites") === "1") {
        button.closest(".room-card")?.remove();
        updateFavoriteResult();
      }
    });
  });

  function updateFavoriteResult() {
    const visible = document.querySelectorAll(".room-card").length;
    const result = document.querySelector(".result-count");
    if (result) result.innerHTML = `Đã lưu <strong>${visible}</strong> phòng yêu thích`;
    const grid = document.querySelector(".room-grid");
    if (grid && visible === 0) {
      grid.innerHTML = '<div class="empty-state">Bạn chưa lưu phòng yêu thích nào.</div>';
    }
  }

  if (new URLSearchParams(location.search).get("favorites") === "1") {
    document.querySelectorAll(".room-card").forEach((card) => {
      if (!favorites.includes(card.dataset.roomId)) card.remove();
    });
    updateFavoriteResult();
  }

  updateFavoriteUi();
});
