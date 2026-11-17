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
  const config = JSON.parse(document.getElementById("tour-config").textContent);
  const [THREE, { buildRoomTourWorld }, { createWalker }, { createWalkthroughMotion }] = await Promise.all([
    import("../vendor/three/three.module.js"),
    import("./room-tour-world.js?v=a103-tour-1"),
    import("./walkthrough-avatar.js?v=a103-tour-1"),
    import("./walkthrough-motion.js?v=a103-tour-1"),
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
  Object.assign(sun.shadow.camera, { left: -10, right: 7, top: 8, bottom: -8, near: 0.5, far: 25 });
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.025;
  scene.add(sun, sun.target);
  const world = buildRoomTourWorld(THREE, scene, config);
  const walker = createWalker(THREE);
  const player = walker.group;
  player.position.set(world.spawn.x, 0, world.spawn.z);
  player.rotation.y = Math.PI;
  scene.add(player);
  const motion = createWalkthroughMotion(world, player.position);
  let yaw = 0;
  let pitch = 0.25;
  let distance = 2.8;
  let lastTime = performance.now();
  let walkTime = 0;
  let cameraReady = false;
  let drag = null;
  let lastZone = "";
  let animationFrame = 0;
  let currentRoom = null;
  const target = new THREE.Vector3();
  const desired = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const raycaster = new THREE.Raycaster();
  const lookTarget = new THREE.Vector3();
  const touchButtons = [...document.querySelectorAll("[data-move]")];
  const dialogs = [...document.querySelectorAll("dialog")];
  const isDialogOpen = () => dialogs.some(dialog => dialog.open);

  clearMovement = () => {
    keys.clear();
    motion.clearInput();
    drag = null;
    host.classList.remove("dragging");
    touchButtons.forEach(button => button.classList.remove("pressed"));
  };

  function requestJump() {
    if (running && !isDialogOpen()) motion.requestJump();
  }

  function reset() {
    clearMovement();
    motion.reset();
    player.rotation.y = Math.PI;
    yaw = 0;
    pitch = 0.25;
    distance = 2.8;
    cameraReady = false;
    world.rooms.forEach(room => { room.door.rotation.y = 0; });
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
    if (event.code === "Space" && !event.target.closest("button, a, [role=button]")) {
      event.preventDefault();
      if (!event.repeat) requestJump();
    }
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
  document.getElementById("tour-jump").addEventListener("click", requestJump);

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
    // Follow the occupied level so the camera can rise above the loft floor.
    desired.y = Math.min(desired.y, world.ceilingAt(desired.x, desired.z, motion.state.level) - .08);
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
    const room = world.nearestRoom(player.position.x, player.position.z);
    const inside = player.position.z < -0.2;
    const level = motion.state.level;
    const zone = level === "stairs" ? `Cầu thang · Phòng ${room.number}`
      : level === "loft" ? `Gác lửng · Phòng ${room.number}`
      : inside ? `Bên trong phòng ${room.number}` : `Trước cửa phòng ${room.number}`;
    const nearStairs = inside && level === "ground" && Math.hypot(player.position.x - (room.stairs.minX + room.stairs.maxX) / 2, player.position.z - room.stairs.bottomZ) < 1.25;
    const hint = level === "stairs" ? "Giữ W để lên · S để xuống · Space nhảy"
      : level === "loft" ? "Gác lửng · Về đầu cầu thang để xuống"
      : nearStairs ? "Tới chân cầu thang · Giữ W để lên gác"
      : inside ? "WASD di chuyển · Space để nhảy" : `Đi tới cửa ${room.number} để vào phòng`;
    if (zone !== lastZone) {
      positionLabel.textContent = zone;
      lastZone = zone;
    }
    if (cue.textContent !== hint) cue.textContent = hint;
    if (currentRoom !== room.number) {
      currentRoom = room.number;
      document.getElementById("tour-room-name").textContent = `Phòng ${currentRoom}`;
      document.querySelectorAll("[data-room-media]").forEach(panel => { panel.hidden = panel.dataset.roomMedia !== currentRoom; });
      document.getElementById("media-title").textContent = `Ảnh & video phòng ${currentRoom}`;
    }
    const x = 110 + player.position.x * 16;
    const y = 134 + player.position.z * 18;
    mapPlayer.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${(-yaw * 180 / Math.PI).toFixed(1)})`);
    // Position data also makes the accessible mini-map inspectable without reading WebGL internals.
    mapPlayer.dataset.x = player.position.x.toFixed(3);
    mapPlayer.dataset.z = player.position.z.toFixed(3);
    mapPlayer.dataset.y = player.position.y.toFixed(3);
    mapPlayer.dataset.airborne = String(motion.state.airborne);
    mapPlayer.dataset.level = level;
    mapPlayer.dataset.room = currentRoom;
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
      world.rooms.forEach(room => {
        const insideRoom = world.roomAt(player.position.x, player.position.z) === room;
        const nearDoor = insideRoom || Math.hypot(player.position.x - room.doorX, player.position.z) < 1.9;
        const doorAngle = nearDoor ? Math.PI / 2 : 0;
        room.door.rotation.y += (doorAngle - room.door.rotation.y) * (1 - Math.exp(-6 * dt));
      });
      const movement = motion.step(dt, { forward, strafe, yaw });
      moved = movement.moved;
      if (moved) {
        const angle = movement.angle;
        player.rotation.y += Math.atan2(Math.sin(angle - player.rotation.y), Math.cos(angle - player.rotation.y)) * (1 - Math.exp(-14 * dt));
      }
    }
    walker.animate(walkTime, moved, motion.state);
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
  document.getElementById("map-geometry").innerHTML =
    '<rect x="17" y="134" width="186" height="65" rx="2" class="map-floor"/><text x="110" y="184">Hành lang chung</text>' +
    world.rooms.map(room => {
      const x = 110 + room.minX * 16;
      const width = (room.maxX - room.minX) * 16;
      const loftFront = 134 + room.loft.maxZ * 18;
      const stairsX = 110 + room.stairs.minX * 16;
      const stairsY = 134 + room.stairs.topZ * 18;
      const stairsWidth = (room.stairs.maxX - room.stairs.minX) * 16;
      const stairsDepth = (room.stairs.bottomZ - room.stairs.topZ) * 18;
      return `<rect x="${x}" y="15" width="${width}" height="119" class="map-floor"/><path d="M ${x} ${loftFront} h ${width}" class="map-line"/><text x="${x + width / 2}" y="35">${room.number}</text><rect x="${stairsX}" y="${stairsY}" width="${stairsWidth}" height="${stairsDepth}" rx="2" class="map-furniture"/>`;
    }).join("");
  const roomConnections = document.querySelector(".connected-rooms");
  if (roomConnections) roomConnections.textContent = [...world.rooms].sort((a, b) => a.minX - b.minX).map(room => room.number).join(" ↔ ") + " · Cùng hành lang";
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
