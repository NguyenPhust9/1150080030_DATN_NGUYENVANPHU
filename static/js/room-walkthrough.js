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
  const [THREE, { buildRoomTourWorld }, { createWalker }, { createWalkthroughMotion }, { createBuildingNavigation }] = await Promise.all([
    import("../vendor/three/three.module.js"),
    import("./room-tour-world.js?v=enclosed-entry-1"),
    import("./walkthrough-avatar.js?v=a105-tour-1"),
    import("./walkthrough-motion.js?v=enclosed-entry-1"),
    import("./building-tour-navigation.js?v=building-tour-1"),
  ]);
  const scene = new THREE.Scene();
  // Keep the courtyard and neighbouring skyline visible from upper floors.
  scene.background = new THREE.Color(0xc8e2ef);
  scene.fog = new THREE.Fog(0xc8e2ef, 40, 145);
  const camera = new THREE.PerspectiveCamera(59, 1, 0.06, 190);
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
  Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 8, bottom: -8, near: 0.5, far: 30 });
  sun.shadow.bias = -0.0003;
  sun.shadow.normalBias = 0.025;
  scene.add(sun, sun.target);
  let activeFloor = config.entryFloor;
  let traveling = false;
  let worldGroup = new THREE.Group();
  scene.add(worldGroup);
  let world = buildRoomTourWorld(THREE, worldGroup, { ...config, activeFloor });
  let corridorCenterX = (world.bounds.minX + world.bounds.maxX) / 2;
  sun.position.x = corridorCenterX - 3;
  sun.target.position.x = corridorCenterX;
  const walker = createWalker(THREE);
  const player = walker.group;
  player.position.set(world.spawn.x, 0, world.spawn.z);
  player.rotation.y = Math.PI;
  scene.add(player);
  let motion = createWalkthroughMotion(world, player.position);
  let yaw = 0;
  let pitch = 0.25;
  let firstPerson = false;
  const savedPitch = { first: 0, third: 0.25 };
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
  const isDialogOpen = () => traveling || dialogs.some(dialog => dialog.open);
  const viewButton = document.getElementById("tour-view");
  const tour = document.getElementById("room-tour");
  let mapScaleX = 186 / (world.bounds.maxX - world.bounds.minX + .6);
  const mapX = x => 110 + (x - corridorCenterX) * mapScaleX;
  const mapZ = z => !world.entrance ? 134 + z * 18
    : z <= 3.7 ? 104 + z * 13 : 152.1 + (z - 3.7) * 1.5;
  tour.dataset.viewMode = "third-person";
  tour.dataset.floor = activeFloor;
  const roomDetails = new Map(config.roomDetails.map(room => [room.number, room]));
  const nearElevator = () => motion.state.level === 'ground' && !motion.state.airborne && !!world.elevator
    && Math.hypot(player.position.x - world.elevator.x, player.position.z - world.elevator.z) < 2;

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

  function toggleView() {
    if (!running || isDialogOpen()) return;
    clearMovement();
    savedPitch[firstPerson ? "first" : "third"] = pitch;
    firstPerson = !firstPerson;
    pitch = savedPitch[firstPerson ? "first" : "third"];
    cameraReady = false;
    tour.dataset.viewMode = firstPerson ? "first-person" : "third-person";
    viewButton.setAttribute("aria-pressed", String(firstPerson));
    const label = firstPerson ? "Góc nhìn thứ ba" : "Góc nhìn thứ nhất";
    viewButton.querySelector("span").textContent = label;
    viewButton.title = `${label} (V)`;
    host.focus({ preventScroll: true });
  }
  viewButton.addEventListener("click", toggleView);

  function reset() {
    clearMovement();
    motion.reset();
    player.rotation.y = Math.PI;
    yaw = 0;
    savedPitch.first = 0;
    savedPitch.third = 0.25;
    pitch = firstPerson ? savedPitch.first : savedPitch.third;
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
    if (event.code === "KeyV" && !event.repeat) { event.preventDefault(); toggleView(); }
    if (event.code === "KeyM" && !event.repeat) { event.preventDefault(); navigation.openMap(); }
    if (event.code === "KeyF" && !event.repeat) { event.preventDefault(); navigation.openElevator(); }
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
    pitch = THREE.MathUtils.clamp(pitch + (event.clientY - drag.y) * 0.004, firstPerson ? -1.15 : -0.13, firstPerson ? 1.15 : 0.85);
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
    if (firstPerson) return;
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
    if (traveling) return;
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
  const navigation = createBuildingNavigation({
    config, openDialog,
    onDestination: room => {
      clearMovement();
      world.setDestination(room?.number ?? null, { x: player.position.x, z: player.position.z });
      renderMiniMap(room);
    },
    onFloor: floor => travelToFloor(floor),
  });

  async function travelToFloor(floor) {
    if (traveling || floor === activeFloor || !nearElevator() || !config.floors.includes(floor)) return;
    traveling = true;
    clearMovement();
    const transfer = document.getElementById('tour-transfer');
    transfer.hidden = false;
    document.getElementById('transfer-label').textContent = `Tầng ${activeFloor} → Tầng ${floor}`;
    tour.dataset.traveling = 'true';
    try {
      await new Promise(resolve => setTimeout(resolve, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 100 : 750));
      const destination = navigation.destination;
      const floorEntry = destination?.floor === floor ? destination.number
        : config.roomDetails.find(room => room.floor === floor).number;
      const nextGroup = new THREE.Group();
      let nextWorld;
      try {
        nextWorld = buildRoomTourWorld(THREE, nextGroup, { ...config, activeFloor: floor, entryRoom: floorEntry });
      } catch (error) {
        nextGroup.traverse(object => { object.geometry?.dispose(); });
        throw error;
      }
      scene.remove(worldGroup);
      world.dispose?.();
      worldGroup = nextGroup;
      world = nextWorld;
      scene.add(worldGroup);
      activeFloor = floor;
      tour.dataset.floor = floor;
      corridorCenterX = (world.bounds.minX + world.bounds.maxX) / 2;
      mapScaleX = 186 / (world.bounds.maxX - world.bounds.minX + .6);
      sun.position.x = corridorCenterX - 3;
      sun.target.position.x = corridorCenterX;
      motion = createWalkthroughMotion(world, player.position);
      motion.reset();
      player.position.set(world.elevator.spawn.x, world.elevator.spawn.y, world.elevator.spawn.z);
      yaw = 0;
      pitch = firstPerson ? 0 : .25;
      player.rotation.y = Math.PI;
      cameraReady = false;
      currentRoom = null;
      lastZone = '';
      world.setDestination(destination?.number ?? null, { x: player.position.x, z: player.position.z });
      renderMiniMap(destination);
      updateConnections();
      await new Promise(resolve => requestAnimationFrame(resolve));
      transfer.hidden = true;
    } catch (error) {
      console.error('Unable to change tour floor', error);
      transfer.hidden = true;
      showError('Chưa chuyển được tầng. Hãy tải lại để tiếp tục tham quan.');
    } finally {
      traveling = false;
      tour.dataset.traveling = 'false';
      lastTime = performance.now();
      if (running && !failed) host.focus({ preventScroll: true });
    }
  }
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
    if (firstPerson) {
      // Keep the eye inside the collision body so walls and low ceilings stay
      // solid. Follow jump/stair height directly, without orbit-camera lag.
      camera.position.copy(player.position);
      camera.position.y += 1.27;
      lookTarget.set(
        camera.position.x - Math.sin(yaw) * Math.cos(pitch),
        camera.position.y - Math.sin(pitch),
        camera.position.z - Math.cos(yaw) * Math.cos(pitch),
      );
      camera.lookAt(lookTarget);
      player.visible = false;
      cameraReady = false;
      return;
    }
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
    const inside = !!world.roomAt(player.position.x, player.position.z) && player.position.z < -0.2;
    const atElevator = nearElevator();
    const outside = !!world.entrance && player.position.z > 3.8;
    const atEntrance = !!world.entrance && !outside && player.position.z > .3
      && Math.abs(player.position.x - world.entrance.x) < 1.5;
    const level = motion.state.level;
    const zone = level === "stairs" ? `Cầu thang · Phòng ${room.number}`
      : level === "loft" ? `Gác lửng · Phòng ${room.number}`
      : outside ? 'Lối đi ngoài sân · Cổng chính' : atEntrance ? 'Sảnh vào tòa nhà'
      : atElevator ? `Thang máy · Tầng ${activeFloor}` : inside ? `Bên trong phòng ${room.number}` : `Trước cửa phòng ${room.number}`;
    const nearStairs = inside && !!room.stairs && level === "ground" && Math.hypot(player.position.x - (room.stairs.minX + room.stairs.maxX) / 2, player.position.z - room.stairs.bottomZ) < 1.25;
    const hint = level === "stairs" ? "Giữ W để lên · S để xuống · Space nhảy"
      : level === "loft" ? "Gác lửng · Về đầu cầu thang để xuống"
      : nearStairs ? "Tới chân cầu thang · Giữ W để lên gác"
      : outside ? 'Theo lối đi có mái che để vào sảnh tòa nhà'
      : atEntrance ? 'Vào hành lang để tới phòng · Lối ra sân ở phía cửa chính'
      : atElevator ? "Nhấn F hoặc nút thang máy để chọn tầng"
      : inside ? "WASD di chuyển · Space để nhảy" : `Đi tới cửa ${room.number} để vào phòng`;
    if (zone !== lastZone) {
      positionLabel.textContent = zone;
      lastZone = zone;
    }
    if (cue.textContent !== hint) cue.textContent = hint;
    if (currentRoom !== room.number) {
      currentRoom = room.number;
      document.querySelectorAll("[data-room-media]").forEach(panel => { panel.hidden = panel.dataset.roomMedia !== currentRoom; });
      document.getElementById("media-title").textContent = `Ảnh & video phòng ${currentRoom}`;
    }
    const modelNote = !inside ? 'Cảnh quan minh họa · Bố trí mô phỏng'
      : roomDetails.get(currentRoom)?.profile === 'generic'
        ? 'Nội thất mô phỏng cơ bản · Chưa dựng theo tư liệu'
        : 'Phỏng dựng từ ảnh và video · Kích thước ước lượng';
    const noteElement = document.getElementById('tour-model-note');
    if (noteElement.textContent !== modelNote) noteElement.textContent = modelNote;
    const heading = outside ? 'Sân tòa nhà' : atEntrance ? 'Sảnh tòa nhà'
      : atElevator ? `Thang máy · Tầng ${activeFloor}` : `Phòng ${currentRoom}`;
    if (document.getElementById('tour-room-name').textContent !== heading) document.getElementById('tour-room-name').textContent = heading;
    navigation.update({ floor: activeFloor, room: currentRoom, inside, nearElevator: atElevator && !traveling });
    const x = mapX(player.position.x);
    const y = mapZ(player.position.z);
    mapPlayer.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${(-yaw * 180 / Math.PI).toFixed(1)})`);
    // Position data also makes the accessible mini-map inspectable without reading WebGL internals.
    mapPlayer.dataset.x = player.position.x.toFixed(3);
    mapPlayer.dataset.z = player.position.z.toFixed(3);
    mapPlayer.dataset.y = player.position.y.toFixed(3);
    mapPlayer.dataset.airborne = String(motion.state.airborne);
    mapPlayer.dataset.level = level;
    mapPlayer.dataset.room = currentRoom;
    mapPlayer.dataset.floor = activeFloor;
    mapPlayer.dataset.zone = outside ? 'outside' : atEntrance ? 'entrance' : inside ? 'room' : atElevator ? 'elevator' : 'corridor';
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
  function renderMiniMap(destination = navigation.destination) {
    const escapeXml = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[char]));
    const hallTop = mapZ(0), hallBottom = mapZ(3.7);
    let markup = `<rect x="${mapX(world.corridorBounds.minX)}" y="${hallTop}" width="${(world.corridorBounds.maxX - world.corridorBounds.minX) * mapScaleX}" height="${hallBottom - hallTop}" rx="2" class="map-floor"/><text x="110" y="${hallBottom - 8}">Hành lang</text>`;
    if (world.entrance) {
      const { path, porch } = world.enclosure;
      for (const area of [porch, path]) markup += `<rect x="${mapX(area.minX)}" y="${mapZ(area.minZ)}" width="${(area.maxX - area.minX) * mapScaleX}" height="${mapZ(area.maxZ) - mapZ(area.minZ)}" class="map-floor"/>`;
      markup += `<text x="${mapX(world.entrance.x)}" y="${hallBottom + 12}">Lối vào</text><text x="${mapX(world.landscape.centerX)}" y="211">Cổng chính</text>`;
      if (destination) markup += `<path d="M ${mapX(world.landscape.centerX)} ${mapZ(33)} V${mapZ(6.1)} H${mapX(world.entrance.x)} V${mapZ(2.4)} H${mapX(world.rooms.find(room => room.number === destination.number)?.doorX ?? world.elevator.x)}" class="map-route"/>`;
    }
    markup += world.rooms.map(room => {
      const x = mapX(room.minX), width = (room.maxX - room.minX) * mapScaleX;
      const roomClass = destination?.number === room.number ? 'map-destination' : 'map-floor';
      let detail = '';
      if (room.loft && room.stairs) {
        detail = `<path d="M ${x} ${mapZ(room.loft.maxZ)} h ${width}" class="map-line"/><rect x="${mapX(room.stairs.minX)}" y="${mapZ(room.stairs.topZ)}" width="${(room.stairs.maxX - room.stairs.minX) * mapScaleX}" height="${mapZ(room.stairs.bottomZ) - mapZ(room.stairs.topZ)}" rx="2" class="map-furniture"/>`;
      } else detail = `<rect x="${x + width * .14}" y="${mapZ(-4.4)}" width="${width * .45}" height="${mapZ(-2.2) - mapZ(-4.4)}" rx="2" class="map-furniture"/>`;
      return `<rect x="${x}" y="${mapZ(-6.6)}" width="${width}" height="${hallTop - mapZ(-6.6)}" class="${roomClass}"/><text x="${x + width / 2}" y="${mapZ(-6.6) + 20}">${escapeXml(room.number)}</text>${detail}`;
    }).join('');
    if (world.elevator) {
      const lift = world.elevator;
      markup += `<rect x="${mapX(lift.minX)}" y="${mapZ(lift.minZ)}" width="${(lift.maxX - lift.minX) * mapScaleX}" height="${mapZ(lift.maxZ) - mapZ(lift.minZ)}" rx="2" class="map-elevator"/><text x="${mapX(lift.x)}" y="${mapZ(lift.z) - 4}">⇅</text>`;
      if (destination) {
        const targetRoom = world.rooms.find(room => room.number === destination.number);
        const x = targetRoom ? mapX(targetRoom.doorX) : mapX(player.position.x);
        const liftX = mapX(lift.x), hallY = mapZ(2.4);
        markup += `<path d="M ${x} ${targetRoom ? mapZ(-.72) : hallY} V${hallY} H${liftX}" class="map-route"/>`;
      }
    }
    document.getElementById('map-geometry').innerHTML = markup;
  }
  function updateConnections() {
    const roomConnections = document.querySelector('.connected-rooms');
    if (roomConnections) roomConnections.textContent = [...world.rooms].sort((a, b) => a.minX - b.minX).map(room => room.number).join(' ↔ ') + ' · Cùng hành lang';
  }
  renderMiniMap();
  updateConnections();
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
