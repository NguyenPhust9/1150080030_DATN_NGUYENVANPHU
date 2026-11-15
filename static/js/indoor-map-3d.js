import * as THREE from "three";
import { OrbitControls } from "../vendor/three/OrbitControls.js";

// Coordinates and paths come from Django. Rendering never invents route segments.
const $ = (selector) => document.querySelector(selector);
const host = $("#map-canvas-host");
let data = JSON.parse($("#indoor-scene-data").textContent);
let selectedId = data.route.start_id;
let renderer, scene, camera, controls, resizeObserver, animation;
let geometry, routeGroup, graphGroup;
let view = "3d";
let labels = [], pickables = [], floors = new Map();
let requestNumber = 0, pendingRoute, mutationBusy = false;
const labelHost = $("#map-labels");
const colors = { room: 0xe3e1d9, corridor: 0xf6f7f8, exit: 0xc9e5da, stairs: 0xdbe1e7, other: 0xe4e9e8 };
const status = (message, error = false) => {
  $("#map-status").textContent = message;
  $("#map-status").classList.toggle("is-error", error);
};
const element = (tag, text, className) => {
  const item = document.createElement(tag);
  if (text) item.textContent = text;
  if (className) item.className = className;
  return item;
};
const icon = (name) => {
  const item = element("i");
  item.dataset.lucide = name;
  return item;
};
const refreshIcons = () => window.lucide?.createIcons();
const nodeFor = (id) => data.nodes.find((node) => node.id === id);
const zoneFor = (id) => data.zones.find((zone) => zone.node_id === id) ||
  data.zones.find((zone) => {
    const node = nodeFor(id);
    return node && zone.kind === node.kind && node.x >= zone.x && node.x <= zone.x + zone.width &&
      node.y >= zone.y && node.y <= zone.y + zone.height;
  });
const destinations = () => data.nodes.filter((node) => ["room", "exit", "stairs"].includes(node.kind))
  .sort((a, b) => Number(a.kind !== "room") - Number(b.kind !== "room") || a.label.localeCompare(b.label, "vi", { numeric: true }));
const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase();
const world = (x, y, height = 0) => new THREE.Vector3(x - data.map.width / 2, height, y - data.map.height / 2);
const material = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.86, metalness: 0 });
function box(parent, x, y, w, d, h, color, base = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material(color));
  mesh.position.copy(world(x + w / 2, y + d / 2, base + h / 2));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
function cylinder(parent, x, y, radius, height, color, base = 0) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 16), material(color));
  mesh.position.copy(world(x, y, base + height / 2));
  mesh.castShadow = true;
  parent.add(mesh);
  return mesh;
}
function line(parent, points, color, width = 2) {
  if (points.length < 2) return;
  // One straight cylinder per segment avoids smoothing a route across a wall.
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i], length = a.distanceTo(b);
    if (!length) continue;
    const segment = new THREE.Mesh(new THREE.CylinderGeometry(width, width, length, 8), material(color));
    segment.position.copy(a).add(b).multiplyScalar(0.5);
    segment.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    parent.add(segment);
  }
}
function disposeGroup(group) {
  if (!group) return;
  group.traverse((object) => {
    object.geometry?.dispose();
    if (Array.isArray(object.material)) object.material.forEach((m) => m.dispose());
    else object.material?.dispose();
  });
  group.clear();
}
function wall(x, y, w, d, height = 45) {
  box(geometry, x, y, w, d, height, 0xfafaf7, 4);
  box(geometry, x, y, w, d, 1.8, 0xa8b3ba, height + 4);
}
function roomWalls(zone) {
  const { x, y, width: w, height: d, door } = zone;
  wall(x - 3, y - 3, 6, d + 6);
  wall(x + w - 3, y - 3, 6, d + 6);
  for (const side of ["north", "south"]) {
    const yy = side === "north" ? y - 3 : y + d - 3;
    if (door?.side === side) {
      const left = door.x - door.width / 2, right = door.x + door.width / 2;
      wall(x, yy, Math.max(1, left - x), 6);
      wall(right, yy, Math.max(1, x + w - right), 6);
      box(geometry, left, yy - 3, door.width, 12, 1, 0xc4a77e, 4.5);
      // Open leaf and its quarter-circle swing make the doorway legible.
      const direction = side === "south" ? -1 : 1;
      box(geometry, left, yy + (direction < 0 ? -door.width : 0), 2, door.width, 24, 0xd5b991, 5);
      const points = [];
      for (let i = 0; i <= 16; i++) {
        const angle = i / 16 * Math.PI / 2;
        points.push(world(left + Math.cos(angle) * door.width, yy + direction * Math.sin(angle) * door.width, 5.6));
      }
      const arc = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: 0xb4a48f }));
      geometry.add(arc);
    } else wall(x, yy, w, 6);
  }
  // A glazed strip on the exterior wall; heights are schematic, not surveyed.
  const windowY = door?.side === "north" ? y + d - 4 : y - 4;
  box(geometry, x + w * .24, windowY, w * .52, 8, 18, 0xb5d3dc, 21);
  for (let i = 0; i <= 4; i++) box(geometry, x + w * (.24 + i * .13), windowY - 1, 2, 10, 22, 0xf4f6f5, 19);
}
function furnishings(zone) {
  const { x, y, width: w, height: d } = zone;
  const north = zone.door?.side !== "north";
  const far = north ? y + 15 : y + d - 102;
  // Scaled studio furniture, left/right of the clear door-to-room-center aisle.
  const bedW = Math.min(65, w * .28), bedX = x + 13;
  box(geometry, bedX, far, bedW, 88, 9, 0xb6a187, 5);
  box(geometry, bedX + 2, far + 2, bedW - 4, 83, 8, 0xfdfdfb, 14);
  box(geometry, bedX + 2, far + 35, bedW - 4, 50, 3, 0x9db3c2, 22);
  box(geometry, bedX + 8, far + 8, bedW - 16, 18, 5, 0xf4eee4, 22);
  const deskX = x + w - Math.min(65, w * .27) - 12;
  box(geometry, deskX, far, Math.min(65, w * .27), 28, 3, 0xd1b692, 24);
  box(geometry, deskX + 3, far + 2, 3, 24, 19, 0xb9ab97, 5);
  box(geometry, x + w - 18, far + 2, 3, 24, 19, 0xb9ab97, 5);
  box(geometry, deskX + 17, far + 7, 25, 3, 15, 0x607481, 27);
  box(geometry, deskX + 16, far + 38, 26, 24, 4, 0x819696, 15);
  box(geometry, deskX + 16, far + 59, 26, 3, 22, 0x819696, 15);
  // Kitchen / storage unit adjacent to the entry, leaving the route unobstructed.
  const entryY = north ? y + d - 40 : y + 12;
  box(geometry, x + w - 76, entryY, 62, 25, 25, 0xc8b493, 5);
  box(geometry, x + w - 78, entryY - 1, 66, 27, 3, 0xf1f0ec, 30);
  box(geometry, x + w - 65, entryY + 5, 20, 15, 1, 0x9babb1, 33);
  plant(x + 22, north ? y + d - 25 : y + 25);
}
function plant(x, y) {
  cylinder(geometry, x, y, 9, 13, 0xd7d0bf, 4);
  const leaves = new THREE.Mesh(new THREE.IcosahedronGeometry(15, 1), material(0x7f9d86));
  leaves.position.copy(world(x, y, 29));
  leaves.scale.y = 1.25;
  leaves.castShadow = true;
  geometry.add(leaves);
}
function addLabel(text, x, y, kind, nodeId, zoneId, height = 65) {
  const button = element(nodeId ? "button" : "span", text, "map-poi-label");
  if (nodeId) {
    button.type = "button";
    button.dataset.nodeId = nodeId;
    button.addEventListener("click", () => choose(nodeId));
  } else button.classList.add("is-utility");
  if (kind === "exit") button.classList.add("is-exit");
  labelHost.append(button);
  labels.push({ element: button, point: world(x, y, height), nodeId, zoneId });
}
function buildGeometry() {
  geometry = new THREE.Group();
  scene.add(geometry);
  const bounds = data.zones.reduce((b, z) => ({
    x: Math.min(b.x, z.x), y: Math.min(b.y, z.y),
    right: Math.max(b.right, z.x + z.width), bottom: Math.max(b.bottom, z.y + z.height),
  }), { x: data.map.width, y: data.map.height, right: 0, bottom: 0 });
  if (data.zones.length) box(geometry, bounds.x - 14, bounds.y - 14, bounds.right - bounds.x + 28, bounds.bottom - bounds.y + 28, 12, 0xc9d0d5, -12);
  for (const zone of data.zones) {
    const floor = box(geometry, zone.x, zone.y, zone.width, zone.height, 4, colors[zone.kind] || colors.other);
    floor.userData.zoneId = zone.id;
    floors.set(zone.id, floor);
    pickables.push(floor);
    if (zone.kind === "room") {
      roomWalls(zone);
      if (data.map.is_demo && zone.door && zone.width >= 120) furnishings(zone);
      addLabel(zone.room_number || zone.name, zone.x + zone.width / 2, zone.y + zone.height / 2, "room", zone.node_id, zone.id);
    } else if (zone.kind === "stairs") {
      if (data.map.is_demo) {
        for (let i = 0; i < 10; i++) box(geometry, zone.x + 23, zone.y + 10 + i * 10, zone.width - 46, 10, 4 + i * 4, 0xf0f3f4, 4);
        wall(zone.x + 14, zone.y + 8, 4, zone.height - 16, 45);
        wall(zone.x + zone.width - 18, zone.y + 8, 4, zone.height - 16, 45);
      }
      addLabel("Cầu thang", zone.x + zone.width / 2, zone.y + zone.height / 2, "stairs", null, zone.id, 65);
    } else if (zone.kind === "exit") {
      const node = data.nodes.find((n) => n.kind === "exit" && n.x >= zone.x && n.x <= zone.x + zone.width && n.y >= zone.y && n.y <= zone.y + zone.height);
      addLabel(node?.label || zone.name, zone.x + zone.width / 2, zone.y + zone.height / 2, "exit", node?.id, zone.id, 42);
      box(geometry, zone.x + 8, zone.y + 8, 4, zone.height - 16, 1, 0x6db395, 5);
    } else if (zone.kind === "other" && data.map.is_demo) {
      box(geometry, zone.x + 22, zone.y + 70, 72, 35, 16, 0x91a7a2, 5);
      box(geometry, zone.x + 22, zone.y + 96, 72, 9, 25, 0x91a7a2, 5);
      box(geometry, zone.x + zone.width - 94, zone.y + 70, 72, 35, 16, 0x91a7a2, 5);
      cylinder(geometry, zone.x + zone.width / 2, zone.y + 86, 23, 13, 0xd5bd98, 5);
      plant(zone.x + 22, zone.y + zone.height - 24);
      plant(zone.x + zone.width - 22, zone.y + zone.height - 24);
      addLabel(zone.name, zone.x + zone.width / 2, zone.y + zone.height - 35, "other", null, zone.id, 30);
    }
  }
  for (const device of data.devices) {
    cylinder(geometry, device.x, device.y, 5, 17, 0xcb6b56, 5);
    box(geometry, device.x - 5, device.y - 2, 10, 4, 3, 0x536270, 22);
  }
  for (const c of data.cameras) {
    box(geometry, c.x - 7, c.y - 5, 14, 10, 8, c.active ? 0x657b8d : 0xa7acb0, 46);
    box(geometry, c.x - 2, c.y - 2, 4, 4, 42, 0xa4afb9, 4);
  }
  graphGroup = new THREE.Group(); scene.add(graphGroup);
  routeGroup = new THREE.Group(); scene.add(routeGroup);
}
function paintState() {
  for (const zone of data.zones) {
    const floor = floors.get(zone.id);
    if (floor) floor.material.color.setHex(zone.hazard ? 0xe9a28d : (zone.node_id === selectedId ? 0xbecbfa : colors[zone.kind] || colors.other));
  }
  labels.forEach((label) => {
    label.element.classList.toggle("is-selected", Boolean(label.nodeId && label.nodeId === selectedId));
    label.element.classList.toggle("is-hazard", Boolean(data.zones.find((z) => z.id === label.zoneId)?.hazard));
  });
  if (renderer) {
    disposeGroup(routeGroup);
    disposeGroup(graphGroup);
    const nodes = new Map(data.nodes.map((n) => [n.id, n]));
    for (const edge of data.edges) {
      const a = nodes.get(edge.start), b = nodes.get(edge.end);
      if (a && b) line(graphGroup, [world(a.x, a.y, 8), world(b.x, b.y, 8)], edge.blocked ? 0xd87f66 : 0xb4bdce, 1.2);
    }
    for (const n of data.nodes) cylinder(graphGroup, n.x, n.y, 4, 2, n.blocked ? 0xd87f66 : 0x8899bd, 8);
    graphGroup.visible = $("#map-show-graph").checked;
    const points = data.route.points.map((p) => world(p.x, p.y, 10));
    line(routeGroup, points, 0x5265df, 4);
    if (points.length) {
      const first = data.route.points[0], last = data.route.points.at(-1);
      cylinder(routeGroup, first.x, first.y, 11, 2, 0xffffff, 10);
      cylinder(routeGroup, first.x, first.y, 7, 3, 0x5265df, 12);
      cylinder(routeGroup, last.x, last.y, 10, 3, 0x2c9a7c, 11);
      for (let i = 1; i < points.length; i++) {
        const delta = points[i].clone().sub(points[i - 1]);
        if (delta.length() < 35) continue;
        const arrow = new THREE.Mesh(new THREE.ConeGeometry(8, 16, 3), material(0xffffff));
        arrow.position.copy(points[i - 1]).add(points[i]).multiplyScalar(.5);
        arrow.position.y = 13;
        arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), delta.normalize());
        routeGroup.add(arrow);
      }
    }
  } else drawFallback();
  renderDirectory();
  renderSummary();
  document.querySelectorAll("[data-hazard-form]").forEach((form) => {
    form.querySelector("button").textContent = data.zones.find((z) => z.id === form.dataset.zoneId)?.simulation ? "Bỏ chặn" : "Chặn thử";
  });
}
function renderDirectory() {
  const directory = $("#map-directory");
  directory.replaceChildren();
  const query = normalize($("#map-search").value);
  const nodes = destinations().filter((node) => normalize(node.label).includes(query));
  $("#map-directory-count").textContent = String(nodes.length);
  $("#map-directory-empty").hidden = nodes.length > 0;
  for (const node of nodes) {
    const button = element("button", "", "indoor-directory-item");
    button.type = "button"; button.dataset.nodeId = node.id;
    button.classList.toggle("is-selected", selectedId === node.id);
    button.classList.toggle("is-exit", node.kind === "exit");
    button.classList.toggle("is-hazard", node.blocked);
    const badge = element("span", "", "indoor-directory-icon");
    badge.append(icon(node.kind === "exit" ? "log-out" : "door-open"));
    const copy = element("span", "", "indoor-directory-copy");
    copy.append(element("strong", node.label), element("small", node.blocked ? "Đang bị chặn" : zoneFor(node.id)?.status || "Điểm thoát trên tầng"));
    button.append(badge, copy);
    button.addEventListener("click", () => choose(node.id));
    directory.append(button);
  }
  refreshIcons();
}
function renderSummary() {
  const route = data.route;
  $("#route-summary").hidden = !route.start_id;
  $("#route-destination").textContent = route.found ? route.exit_label : "Không có tuyến khả dụng";
  $("#route-distance").textContent = route.found ? (route.distance_m !== null ? "Khoảng " + route.distance_m + " m · tỉ lệ giả định" : "Chưa hiệu chuẩn khoảng cách") : route.reason;
  const steps = $("#route-steps");
  steps.replaceChildren();
  // Keep doors, origin and destination; compress internal corridor junctions.
  route.points.filter((p, i) => i === 0 || i === route.points.length - 1 || p.label.startsWith("Cửa phòng")).forEach((point) => steps.append(element("li", point.label)));
  status(route.start_id ? route.reason : "Chọn phòng trên bản đồ hoặc danh sách để xem đường đi.", Boolean(route.start_id && !route.found));
}
function choose(id) {
  const node = nodeFor(id);
  if (!node) return;
  selectedId = id;
  const panel = $("#map-selection"); panel.hidden = false; panel.replaceChildren();
  panel.append(element("h3", node.label), element("p", node.blocked ? "Vị trí đang nằm trong vùng chặn." : zoneFor(id)?.status || "Điểm định tuyến trong tầng"));
  const actions = element("div", "", "selection-actions");
  for (const [text, field] of [["Đi từ đây", "start"], ["Đến đây", "end"]]) {
    const button = element("button", text);
    button.type = "button";
    button.addEventListener("click", () => {
      $("#" + field).value = id;
      if ($("#start").value) requestRoute();
      else status("Hãy chọn thêm điểm bắt đầu.");
    });
    actions.append(button);
  }
  panel.append(actions);
  paintState();
  if (!$("#start").value) {
    $("#start").value = id;
    requestRoute();
  } else status("Đã chọn " + node.label + ". Chọn Đi từ đây hoặc Đến đây trong bảng thông tin.");
}
async function readResponse(response) {
  if (!response.ok || !response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error("Không tải được bản đồ. Kiểm tra kết nối hoặc đăng nhập lại.");
  }
  return response.json();
}
function clearRoute() {
  data.route = { ...data.route, start_id: $("#start").value, end_id: $("#end").value,
    found: false, points: [], distance_m: null, exit_label: "", reason: "Đang cập nhật tuyến đường…" };
  paintState();
}
async function requestRoute() {
  if (mutationBusy) return;
  const number = ++requestNumber;
  pendingRoute?.abort();
  pendingRoute = new AbortController();
  clearRoute();
  status("Đang tính đường đi…");
  const url = new URL(location.href);
  url.search = new URLSearchParams({ start: $("#start").value, end: $("#end").value, format: "json" }).toString();
  try {
    const next = await readResponse(await fetch(url, { signal: pendingRoute.signal, credentials: "same-origin", cache: "no-store" }));
    if (number !== requestNumber) return;
    data = next; selectedId = data.route.start_id;
    paintState();
    url.searchParams.delete("format");
    history.replaceState(null, "", url);
  } catch (error) {
    if (error.name !== "AbortError" && number === requestNumber) status("Không tải được tuyến đường. Kiểm tra kết nối hoặc đăng nhập lại.", true);
  }
}
function drawFallback() {
  const fallback = $("#map-fallback"); fallback.hidden = false;
  $("#indoor-map-3d").hidden = true; labelHost.hidden = true;
  fallback.replaceChildren();
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 " + data.map.width + " " + data.map.height);
  svg.setAttribute("aria-label", "Mặt bằng 2D dự phòng");
  const add = (tag, attrs) => {
    const el = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
    svg.append(el); return el;
  };
  for (const zone of data.zones) {
    const rect = add("rect", { x: zone.x, y: zone.y, width: zone.width, height: zone.height, fill: zone.hazard ? "#efb5a6" : zone.node_id === selectedId ? "#c7d2ff" : "#" + (colors[zone.kind] || colors.other).toString(16).padStart(6, "0"), stroke: "#a7b3bf", "stroke-width": 4 });
    if (zone.node_id) { rect.style.cursor = "pointer"; rect.addEventListener("click", () => choose(zone.node_id)); }
    add("text", { x: zone.x + zone.width / 2, y: zone.y + zone.height / 2, "text-anchor": "middle", fill: "#536174", "font-size": 15 }).textContent = zone.room_number || zone.name;
  }
  if (data.route.found) add("polyline", { points: data.route.points.map((p) => p.x + "," + p.y).join(" "), fill: "none", stroke: "#5265df", "stroke-width": 7, "stroke-linejoin": "round" });
  fallback.append(svg, element("p", "WebGL không khả dụng · Đang dùng mặt bằng 2D dự phòng."));
}
function updateLabels() {
  const width = host.clientWidth, height = host.clientHeight;
  const occupied = [];
  // Prioritize selected rooms; hide overlapping utility labels at small sizes.
  for (const label of [...labels].sort((a, b) => Number(b.nodeId === selectedId) - Number(a.nodeId === selectedId))) {
    const p = label.point.clone().project(camera);
    const x = (p.x + 1) * width / 2, y = (1 - p.y) * height / 2;
    const w = label.element.offsetWidth || 65, h = 25;
    const overlap = occupied.some((r) => Math.abs(r.x - x) < (r.w + w) / 2 + 3 && Math.abs(r.y - y) < h);
    const visible = p.z > -1 && p.z < 1 && x > 8 && x < width - 8 && y > 60 && y < height - 65 && !overlap;
    label.element.hidden = !visible;
    if (visible) {
      label.element.style.left = x + "px"; label.element.style.top = y + "px";
      occupied.push({ x, y, w });
    }
  }
}
function resize() {
  if (!renderer) return;
  const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
  const aspect = width / height;
  const span = Math.max(data.map.height * 1.18, data.map.width * 1.26 / aspect);
  camera.left = -span * aspect / 2; camera.right = span * aspect / 2;
  camera.top = span / 2; camera.bottom = -span / 2;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}
function setView(next, reset = false) {
  if (!renderer) return;
  view = next;
  controls.target.set(0, 0, 0);
  camera.up.set(0, 1, 0);
  if (view === "2d") camera.position.set(0, 1500, .01);
  else camera.position.set(540, 1100, 900);
  controls.enableRotate = view !== "2d";
  controls.mouseButtons.LEFT = view === "2d" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  if (reset) camera.zoom = 1;
  camera.lookAt(controls.target); camera.updateProjectionMatrix(); controls.update();
  document.querySelectorAll("[data-map-view]").forEach((button) => {
    const active = button.dataset.mapView === view;
    button.classList.toggle("is-active", active); button.setAttribute("aria-pressed", String(active));
  });
}
function init3D() {
  try {
    renderer = new THREE.WebGLRenderer({ canvas: $("#indoor-map-3d"), antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0xf1f3f5);
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    scene = new THREE.Scene();
    camera = new THREE.OrthographicCamera(-800, 800, 600, -600, 1, 6000);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = .09;
    controls.minZoom = .5; controls.maxZoom = 4;
    controls.minPolarAngle = 0; controls.maxPolarAngle = Math.PI / 2.45;
    controls.screenSpacePanning = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x929ca8, 2.1));
    const sun = new THREE.DirectionalLight(0xffffff, 2.5);
    sun.position.set(-350, 1000, -500); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -1000; sun.shadow.camera.right = 1000;
    sun.shadow.camera.top = 850; sun.shadow.camera.bottom = -850;
    sun.shadow.camera.far = 2600; sun.shadow.bias = -.0005;
    sun.shadow.normalBias = 1;
    scene.add(sun);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(10000, 10000), material(0xf1f3f5));
    ground.rotation.x = -Math.PI / 2; ground.position.y = -14; ground.receiveShadow = true; scene.add(ground);
    buildGeometry(); resize(); setView("3d", true);
    resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
    let down;
    renderer.domElement.addEventListener("pointerdown", (event) => { down = { x: event.clientX, y: event.clientY }; });
    renderer.domElement.addEventListener("pointerup", (event) => {
      if (!down || event.button !== 0 || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      const ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1), camera);
      const zone = data.zones.find((z) => z.id === ray.intersectObjects(pickables)[0]?.object.userData.zoneId);
      if (zone?.node_id) choose(zone.node_id);
    });
    renderer.domElement.addEventListener("webglcontextlost", (event) => {
      event.preventDefault(); cancelAnimationFrame(animation); renderer = null; drawFallback();
      status("Đồ họa 3D bị gián đoạn. Đang dùng mặt bằng 2D.", true);
    });
    const animate = () => {
      animation = requestAnimationFrame(animate);
      controls.update(); renderer.render(scene, camera); updateLabels();
    };
    animate();
  } catch (error) {
    renderer?.dispose(); renderer = null; drawFallback();
    document.querySelectorAll("[data-map-view], [data-map-action]").forEach((b) => { b.disabled = true; });
  }
}
$("#map-route-form").addEventListener("submit", (event) => { event.preventDefault(); requestRoute(); });
$("#start").addEventListener("change", requestRoute);
$("#end").addEventListener("change", requestRoute);
$("#map-search").addEventListener("input", renderDirectory);
$("#map-show-graph").addEventListener("change", () => { if (graphGroup) graphGroup.visible = $("#map-show-graph").checked; });
document.querySelectorAll("[data-map-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.mapView)));
document.querySelectorAll("[data-map-action]").forEach((button) => button.addEventListener("click", async () => {
  if (!renderer) return;
  const action = button.dataset.mapAction;
  if (action === "reset") setView(view, true);
  if (action === "zoom-in" || action === "zoom-out") {
    camera.zoom = THREE.MathUtils.clamp(camera.zoom * (action === "zoom-in" ? 1.2 : 1 / 1.2), .5, 4);
    camera.updateProjectionMatrix();
  }
  if (action === "rotate") {
    if (view === "2d") setView("3d");
    const offset = camera.position.clone().sub(controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 4);
    camera.position.copy(controls.target).add(offset); controls.update();
  }
  if (action === "fullscreen") {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await $(".indoor-map-stage").requestFullscreen(); }
    catch { status("Trình duyệt không cho phép mở toàn màn hình.", true); }
  }
}));
document.querySelectorAll("[data-hazard-form]").forEach((form) => form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (mutationBusy) return;
  mutationBusy = true; requestNumber++; pendingRoute?.abort();
  document.querySelectorAll("[data-hazard-form] button").forEach((b) => { b.disabled = true; });
  const body = new FormData(form);
  body.set("start", $("#start").value); body.set("end", $("#end").value);
  clearRoute(); status("Đang cập nhật vùng chặn…");
  try {
    data = await readResponse(await fetch(form.action, { method: "POST", body, credentials: "same-origin", headers: { Accept: "application/json" } }));
    paintState();
  } catch { status("Không cập nhật được vùng chặn. Hãy tải lại bản đồ để kiểm tra trạng thái.", true); }
  finally {
    mutationBusy = false;
    document.querySelectorAll("[data-hazard-form] button").forEach((b) => { b.disabled = false; });
    if (data.route.start_id !== $("#start").value || data.route.end_id !== $("#end").value) requestRoute();
  }
}));
window.addEventListener("pagehide", () => {
  cancelAnimationFrame(animation); pendingRoute?.abort(); resizeObserver?.disconnect();
  controls?.dispose(); disposeGroup(scene); renderer?.dispose();
});
init3D();
paintState();
