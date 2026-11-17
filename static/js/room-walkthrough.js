const host = document.getElementById("tour-canvas");
const startButton = document.getElementById("tour-start");
const loading = document.getElementById("tour-loading");
const fallback = document.getElementById("tour-fallback");
const positionLabel = document.getElementById("tour-position");
const cue = document.querySelector("#tour-cue span");
const mapPlayer = document.getElementById("map-player");
const keys = new Set();
let running = false;
let failed = false;
let clearMovement = () => keys.clear();

function showError(message) {
  failed = true;
  running = false;
  clearMovement();
  loading.hidden = true;
  fallback.hidden = false;
  document.getElementById("tour-error").textContent = message;
}
document.getElementById("tour-reload").addEventListener("click", () => location.reload());

try {
  const [THREE, { buildA101World }, { createWalker }] = await Promise.all([
    import("../vendor/three/three.module.js"),
    import("./a101-world.js"),
    import("./walkthrough-avatar.js"),
  ]);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xc1d0cf);
  scene.fog = new THREE.Fog(0xc1d0cf, 17, 48);
  const camera = new THREE.PerspectiveCamera(59, 1, 0.06, 80);
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  host.append(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");
  scene.add(new THREE.HemisphereLight(0xeaf3ff, 0xc2b6a0, 2.2));
  const sun = new THREE.DirectionalLight(0xffeed7, 2.7);
  sun.position.set(-3, 8, 5);
  sun.target.position.set(0, 0, -2);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -7, right: 7, top: 8, bottom: -8, near: 0.5, far: 22 });
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.025;
  scene.add(sun, sun.target);
  const frontLight = new THREE.PointLight(0xfff5de, 13, 8, 2);
  frontLight.position.set(0, 3.4, -1);
  const rearLight = new THREE.PointLight(0xffffff, 10, 7, 2);
  rearLight.position.set(0, 1.95, -4.2);
  scene.add(frontLight, rearLight);

  const world = buildA101World(THREE, scene);
  const walker = createWalker(THREE);
  const player = walker.group;
  player.position.set(world.spawn.x, 0, world.spawn.z);
  player.rotation.y = Math.PI;
  scene.add(player);
  let yaw = 0;
  let pitch = 0.25;
  let distance = 2.8;
  let lastTime = performance.now();
  let walkTime = 0;
  let cameraReady = false;
  let drag = null;
  let lastZone = "";
  let animationFrame = 0;
  const radius = 0.20;
  const speed = 1.55;
  const target = new THREE.Vector3();
  const desired = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const raycaster = new THREE.Raycaster();
  const lookTarget = new THREE.Vector3();
  const closedDoor = { minX: -0.04, maxX: 1.14, minZ: -0.07, maxZ: 0.07 };
  const touchButtons = [...document.querySelectorAll("[data-move]")];
  const dialogs = [...document.querySelectorAll("dialog")];
  const isDialogOpen = () => dialogs.some(dialog => dialog.open);

  clearMovement = () => {
    keys.clear();
    drag = null;
    host.classList.remove("dragging");
    touchButtons.forEach(button => button.classList.remove("pressed"));
  };

  function overlaps(x, z, rect) {
    const dx = x - Math.max(rect.minX, Math.min(x, rect.maxX));
    const dz = z - Math.max(rect.minZ, Math.min(z, rect.maxZ));
    return dx * dx + dz * dz < radius * radius;
  }

  function canStand(x, z) {
    // The walkable ground is the union of the corridor and the room.
    if (z > 3.35 || z < -6.6 + radius || Math.abs(x) > 3.3) return false;
    if (z < 0 && Math.abs(x) > 1.6 - radius) return false;
    if (world.obstacles.some(rect => overlaps(x, z, rect))) return false;
    const angle = world.door.rotation.y;
    const doorBounds = angle < 0.05 ? closedDoor : {
      minX: -0.04, maxX: 1.1 * Math.cos(angle) + 0.04,
      minZ: -1.1 * Math.sin(angle) - 0.04, maxZ: 0.04,
    };
    return !overlaps(x, z, doorBounds);
  }

  function reset() {
    clearMovement();
    player.position.set(world.spawn.x, 0, world.spawn.z);
    player.rotation.y = Math.PI;
    yaw = 0;
    pitch = 0.25;
    distance = 2.8;
    cameraReady = false;
    world.door.rotation.y = 0;
    if (running) host.focus({ preventScroll: true });
  }
  document.getElementById("tour-reset").addEventListener("click", reset);
  startButton.addEventListener("click", () => {
    loading.hidden = true;
    running = true;
    host.focus({ preventScroll: true });
  });

  const movementCodes = new Set(["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowLeft", "ArrowDown", "ArrowRight", "KeyQ", "KeyE"]);
  window.addEventListener("keydown", event => {
    if (!running || isDialogOpen() || event.ctrlKey || event.metaKey || event.altKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
    if (movementCodes.has(event.code)) { event.preventDefault(); keys.add(event.code); }
    if (event.code === "KeyR" && !event.repeat) { event.preventDefault(); reset(); }
  });
  window.addEventListener("keyup", event => keys.delete(event.code));
  window.addEventListener("blur", clearMovement);
  document.addEventListener("visibilitychange", () => {
    clearMovement();
    lastTime = performance.now();
    if (!document.hidden && !failed && !animationFrame) animationFrame = requestAnimationFrame(frame);
  });

  host.addEventListener("pointerdown", event => {
    if (!running || isDialogOpen() || event.button !== 0) return;
    host.focus({ preventScroll: true });
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
    host.setPointerCapture(event.pointerId);
    host.classList.add("dragging");
  });
  host.addEventListener("pointermove", event => {
    if (!drag || drag.id !== event.pointerId) return;
    yaw -= (event.clientX - drag.x) * 0.005;
    pitch = THREE.MathUtils.clamp(pitch + (event.clientY - drag.y) * 0.004, -0.13, 0.85);
    drag.x = event.clientX;
    drag.y = event.clientY;
  });
  function finishLook(event) {
    if (drag?.id !== event.pointerId) return;
    drag = null;
    host.classList.remove("dragging");
    if (host.hasPointerCapture(event.pointerId)) host.releasePointerCapture(event.pointerId);
  }
  host.addEventListener("pointerup", finishLook);
  host.addEventListener("pointercancel", finishLook);
  host.addEventListener("lostpointercapture", finishLook);
  host.addEventListener("wheel", event => {
    if (!running || isDialogOpen()) return;
    event.preventDefault();
    distance = THREE.MathUtils.clamp(distance + event.deltaY * 0.002, 1.3, 3.4);
  }, { passive: false });

  touchButtons.forEach(button => {
    button.addEventListener("pointerdown", event => {
      if (!running || isDialogOpen()) return;
      event.preventDefault();
      button.setPointerCapture(event.pointerId);
      keys.add(button.dataset.move);
      button.classList.add("pressed");
    });
    const release = () => { keys.delete(button.dataset.move); button.classList.remove("pressed"); };
    button.addEventListener("pointerup", release);
    button.addEventListener("pointercancel", release);
    button.addEventListener("lostpointercapture", release);
  });

  function openDialog(id) {
    clearMovement();
    document.getElementById(id).showModal();
  }
  document.getElementById("tour-help").addEventListener("click", () => openDialog("tour-help-dialog"));
  document.getElementById("tour-media").addEventListener("click", () => openDialog("tour-media-dialog"));
  dialogs.forEach(dialog => {
    dialog.querySelector("[data-close-dialog]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      dialog.querySelectorAll("video").forEach(video => video.pause());
      clearMovement();
      if (running) host.focus({ preventScroll: true });
    });
  });
  const fullscreen = document.getElementById("tour-fullscreen");
  if (!document.fullscreenEnabled) fullscreen.hidden = true;
  fullscreen.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.getElementById("room-tour").requestFullscreen();
    } catch { cue.textContent = "Trình duyệt chưa cho phép toàn màn hình"; }
  });
  document.addEventListener("fullscreenchange", () => {
    fullscreen.setAttribute("aria-label", document.fullscreenElement ? "Thoát toàn màn hình" : "Bật toàn màn hình");
    clearMovement();
  });

  function updateCamera(dt) {
    target.copy(player.position).add(new THREE.Vector3(0, 1.07, 0));
    const offsetHeight = Math.sin(pitch) * distance;
    const horizontal = Math.cos(pitch) * distance;
    desired.set(target.x + Math.sin(yaw) * horizontal, target.y + offsetHeight + 0.18, target.z + Math.cos(yaw) * horizontal);
    // Keep the follow camera beneath the loft when standing under it.
    if (desired.z < -2.7 && Math.abs(desired.x) < 1.7) desired.y = Math.min(desired.y, 2.02);
    desired.y = Math.max(desired.y, 0.35);
    scene.updateMatrixWorld(true);
    direction.copy(desired).sub(target);
    const length = direction.length();
    direction.normalize();
    raycaster.set(target, direction);
    raycaster.far = length;
    const collision = raycaster.intersectObjects(world.cameraObstacles, false)[0];
    if (collision) desired.copy(target).addScaledVector(direction, Math.max(0.08, collision.distance - 0.16));
    if (!cameraReady) { camera.position.copy(desired); cameraReady = true; }
    else camera.position.lerp(desired, 1 - Math.exp(-12 * dt));
    // Re-check the smoothed path so rounding a corner cannot leave the camera
    // on the far side of a wall. Hide the avatar when the camera is too close.
    direction.copy(camera.position).sub(target);
    raycaster.set(target, direction.clone().normalize());
    raycaster.far = direction.length();
    const obstruction = raycaster.intersectObjects(world.cameraObstacles, false)[0];
    if (obstruction) camera.position.copy(target).addScaledVector(direction.normalize(), Math.max(0.08, obstruction.distance - 0.16));
    player.visible = camera.position.distanceTo(target) > 0.7;
    lookTarget.copy(target).add(new THREE.Vector3(-Math.sin(yaw) * 0.18, 0.08, -Math.cos(yaw) * 0.18));
    camera.lookAt(lookTarget);
  }

  function updateHud() {
    const inside = player.position.z < -0.2;
    const zone = inside ? "Bên trong phòng A101" : "Trước cửa phòng";
    if (zone !== lastZone) {
      positionLabel.textContent = zone;
      cue.textContent = inside ? "Khám phá tầng trệt · kéo chuột để nhìn quanh" : "Đi tới cửa để vào phòng";
      lastZone = zone;
    }
    const x = 90 + player.position.x * 25;
    const y = 146 + player.position.z * (player.position.z > 0 ? 15 : 19);
    mapPlayer.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${(-yaw * 180 / Math.PI).toFixed(1)})`);
    // Position data also makes the accessible mini-map inspectable without reading WebGL internals.
    mapPlayer.dataset.x = player.position.x.toFixed(3);
    mapPlayer.dataset.z = player.position.z.toFixed(3);
  }

  function frame(now) {
    animationFrame = 0;
    if (document.hidden || failed) return;
    const dt = Math.min((now - lastTime) / 1000, 0.05);
    lastTime = now;
    walkTime += dt;
    let moved = false;
    if (running && !isDialogOpen()) {
      const forward = Number(keys.has("KeyW") || keys.has("ArrowUp")) - Number(keys.has("KeyS") || keys.has("ArrowDown"));
      const strafe = Number(keys.has("KeyD") || keys.has("ArrowRight")) - Number(keys.has("KeyA") || keys.has("ArrowLeft"));
      yaw += (Number(keys.has("KeyE")) - Number(keys.has("KeyQ"))) * dt * 1.5;
      const nearDoor = player.position.z < 0 || Math.hypot(player.position.x - 0.55, player.position.z) < 1.9;
      const doorAngle = nearDoor ? Math.PI / 2 : 0;
      world.door.rotation.y += (doorAngle - world.door.rotation.y) * (1 - Math.exp(-6 * dt));
      if (forward || strafe) {
        const length = Math.hypot(forward, strafe);
        const dx = (strafe * Math.cos(yaw) - forward * Math.sin(yaw)) / length * speed * dt;
        const dz = (-forward * Math.cos(yaw) - strafe * Math.sin(yaw)) / length * speed * dt;
        const beforeX = player.position.x;
        const beforeZ = player.position.z;
        // Axis-separated collision lets a character slide along a wall instead of getting stuck.
        if (canStand(player.position.x + dx, player.position.z)) player.position.x += dx;
        if (canStand(player.position.x, player.position.z + dz)) player.position.z += dz;
        player.position.y = player.position.z < -5.1 ? 0.15 : 0;
        moved = Math.hypot(player.position.x - beforeX, player.position.z - beforeZ) > 0.0001;
        const angle = Math.atan2(dx, dz);
        player.rotation.y += Math.atan2(Math.sin(angle - player.rotation.y), Math.cos(angle - player.rotation.y)) * (1 - Math.exp(-14 * dt));
      }
    }
    walker.animate(walkTime, moved);
    updateCamera(dt);
    updateHud();
    renderer.render(scene, camera);
    animationFrame = requestAnimationFrame(frame);
  }

  function resize() {
    const { width, height } = host.getBoundingClientRect();
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }
  new ResizeObserver(resize).observe(host);
  resize();
  renderer.domElement.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    showError("Kết nối đồ họa đã bị gián đoạn. Tải lại trang để tiếp tục tham quan.");
  });
  animationFrame = requestAnimationFrame(frame);
  startButton.disabled = false;
  startButton.textContent = "Bắt đầu tham quan →";
  document.getElementById("room-tour").dataset.ready = "true";
} catch (error) {
  console.error("Room walkthrough failed to initialize", error);
  showError("Không gian 3D chưa tải được. Hãy tải lại trang hoặc kiểm tra trình duyệt có hỗ trợ WebGL 2.");
}
