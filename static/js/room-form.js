document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("room-create-form");
  if (!form) return;
  const tabs = [...document.querySelectorAll(".room-form-tabs button")];
  const panels = [...document.querySelectorAll(".room-tab-content")];
  const status = document.getElementById("upload-status");
  const message = document.getElementById("upload-message");
  const progress = document.getElementById("upload-progress");
  const save = document.getElementById("save-room");
  const uploadedFiles = new WeakMap();
  let busy = false;

  function showTab(tab) {
    tabs.forEach(item => item.classList.toggle("active", item === tab));
    panels.forEach(panel => panel.classList.toggle("active", panel.dataset.panel === tab.dataset.tab));
  }
  tabs.forEach(tab => tab.addEventListener("click", () => showTab(tab)));
  // Make required fields focusable when saving from a media tab.
  form.addEventListener("invalid", event => {
    const panel = event.target.closest(".room-tab-content");
    const tab = tabs.find(item => item.dataset.tab === panel?.dataset.panel);
    if (tab) showTab(tab);
  }, true);

  function bindPicker(zone) {
    const input = document.getElementById(zone.dataset.target);
    const isImage = input.id === "room-images";
    const preview = document.getElementById(isImage ? "image-previews" : "video-previews");
    const selected = [];
    let previewUrls = [];
    function syncFiles() {
      const transfer = new DataTransfer();
      selected.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
    }
    function render(primaryFile) {
      preview.replaceChildren();
      previewUrls.forEach(url => URL.revokeObjectURL(url));
      previewUrls = [];
      selected.forEach((file, index) => {
        const item = document.createElement("div");
        item.className = "media-preview";
        const url = URL.createObjectURL(file);
        previewUrls.push(url);
        const media = document.createElement(isImage ? "img" : "video");
        media.src = url;
        if (isImage) media.alt = "Ảnh xem trước";
        else { media.controls = true; media.preload = "metadata"; }
        item.append(media);
        if (isImage) {
          const label = document.createElement("label");
          const radio = document.createElement("input");
          radio.type = "radio";
          radio.name = "primary-choice";
          radio.value = `new:${index}`;
          radio.checked = file === primaryFile;
          label.append(radio, " Ảnh chính");
          item.append(label);
        }
        const name = document.createElement("span");
        name.textContent = file.name;
        name.title = file.name;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "remove-media";
        remove.textContent = "×";
        remove.title = "Bỏ tệp này";
        remove.setAttribute("aria-label", `Bỏ ${file.name}`);
        remove.addEventListener("click", () => {
          if (busy) return;
          const primary = selectedPrimary();
          selected.splice(index, 1);
          syncFiles();
          render(primary);
        });
        item.append(name, remove);
        preview.append(item);
      });
    }
    function selectedPrimary() {
      const value = preview.querySelector('input[name="primary-choice"]:checked')?.value;
      return value ? selected[Number(value.split(":")[1])] : null;
    }
    zone.addEventListener("click", event => {
      if (!busy && !event.target.closest("input")) input.click();
    });
    input.addEventListener("change", () => {
      const primary = selectedPrimary();
      [...input.files].forEach(file => {
        if (!selected.some(current => current.name === file.name && current.size === file.size && current.lastModified === file.lastModified)) {
          selected.push(file);
        }
      });
      syncFiles();
      render(primary);
    });
  }
  document.querySelectorAll(".upload-zone").forEach(bindPicker);

  async function getSignature() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(form.dataset.uploadSignatureUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
        signal: controller.signal,
      });
      if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error("Phiên đăng nhập đã hết hạn hoặc bạn không có quyền tải tệp. Vui lòng đăng nhập lại.");
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error || "Không chuẩn bị được phiên tải tệp. Vui lòng thử lại.");
      if (!data?.cloud_name || !data.api_key || !data.timestamp || !data.signature || !data.folder) {
        throw new Error("Thông tin tải tệp không hợp lệ. Vui lòng thử lại.");
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError" || error instanceof TypeError) {
        throw new Error("Không kết nối được máy chủ để chuẩn bị tải tệp. Kiểm tra mạng rồi bấm Lưu để thử lại.");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function upload(file, type, index, total) {
    if (!file.size) throw new Error(`Tệp ${file.name} rỗng. Vui lòng chọn tệp khác.`);
    message.textContent = `Đang chuẩn bị tải tệp ${index}/${total}: ${file.name}...`;
    progress.hidden = true;
    const signature = await getSignature();
    const body = new FormData();
    body.append("file", file);
    ["api_key", "timestamp", "signature", "folder"].forEach(key => body.append(key, signature[key]));
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", `https://api.cloudinary.com/v1_1/${encodeURIComponent(signature.cloud_name)}/${type}/upload`);
      request.timeout = 10 * 60 * 1000;
      request.responseType = "json";
      progress.value = 0;
      progress.hidden = false;
      message.textContent = `Đang tải tệp ${index}/${total}: ${file.name} — 0%`;
      request.upload.addEventListener("progress", event => {
        if (!event.lengthComputable) return;
        const percent = Math.min(100, Math.round(event.loaded / event.total * 100));
        progress.value = percent;
        message.textContent = percent === 100
          ? `Đã gửi tệp ${index}/${total}: ${file.name}. Đang chờ xác nhận lưu trữ...`
          : `Đang tải tệp ${index}/${total}: ${file.name} — ${percent}%`;
      });
      request.addEventListener("load", () => {
        const data = request.response;
        if (request.status < 200 || request.status >= 300) {
          const detail = data?.error?.message || (request.status === 413 ? "Tệp vượt dung lượng dịch vụ lưu trữ cho phép." : `Lỗi dịch vụ lưu trữ (${request.status}).`);
          reject(new Error(`Không tải được ${file.name}: ${detail} Bấm Lưu để thử lại.`));
          return;
        }
        if (!data?.secure_url?.startsWith("https://res.cloudinary.com/") || !data.public_id || data.resource_type !== type) {
          reject(new Error(`Chưa nhận được xác nhận lưu ${file.name}. Vui lòng thử lại.`));
          return;
        }
        resolve({ media_type: type, url: data.secure_url, public_id: data.public_id, format: data.format || "", bytes: data.bytes || file.size });
      });
      request.addEventListener("error", () => reject(new Error(`Kết nối khi tải ${file.name} bị ngắt. Kiểm tra mạng rồi bấm Lưu để thử lại.`)));
      request.addEventListener("timeout", () => reject(new Error(`Tải ${file.name} quá thời gian chờ. Kiểm tra mạng rồi bấm Lưu để thử lại.`)));
      request.addEventListener("abort", () => reject(new Error(`Đã dừng tải ${file.name}. Bấm Lưu để thử lại.`)));
      request.send(body);
    });
  }

  form.addEventListener("submit", async event => {
    if (busy) { event.preventDefault(); return; }
    document.getElementById("primary-image").value = form.querySelector('input[name="primary-choice"]:checked')?.value || "";
    const files = [
      ...[...document.getElementById("room-images").files].map(file => ({ file, type: "image" })),
      ...[...document.getElementById("room-videos").files].map(file => ({ file, type: "video" })),
    ];
    if (!files.length) return;
    event.preventDefault();
    busy = true;
    const controls = [...form.querySelectorAll("button, input, select, textarea")].filter(control => !control.disabled);
    controls.forEach(control => { control.disabled = true; });
    form.setAttribute("aria-busy", "true");
    status.hidden = false;
    status.classList.remove("error");
    try {
      const results = [];
      for (const [index, { file, type }] of files.entries()) {
        let result = uploadedFiles.get(file);
        if (!result) {
          result = await upload(file, type, index + 1, files.length);
          uploadedFiles.set(file, result);
        }
        results.push(result);
      }
      document.getElementById("media-payload").value = JSON.stringify(results);
      progress.value = 100;
      progress.hidden = false;
      message.textContent = "Tải lên hoàn tất. Đang lưu thông tin phòng...";
      // Restore named controls so the final request includes cover/deletion choices.
      controls.forEach(control => { control.disabled = false; });
      save.disabled = true;
      HTMLFormElement.prototype.submit.call(form);
    } catch (error) {
      message.textContent = error.message;
      status.classList.add("error");
      progress.hidden = true;
      controls.forEach(control => { control.disabled = false; });
      form.removeAttribute("aria-busy");
      busy = false;
    }
  });
});
