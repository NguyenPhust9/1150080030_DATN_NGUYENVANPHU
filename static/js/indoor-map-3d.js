import { createBuildingScene } from './indoor-building-scene.js?v=building-1';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const element = (tag, text = '', className = '') => {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
};
let data = JSON.parse($('#indoor-scene-data').textContent);
let activeFloor = data.floor, selected = '', overview = new URLSearchParams(location.search).get('overview') === '1';
let view = new URLSearchParams(location.search).get('view') === '2d' ? '2d' : '3d';
let renderer, unavailable3D = false, pending, requestNumber = 0, mutationBusy = false, zoom2D = 1;
const status = (message, error = false) => {
  $('#map-status').textContent = message; $('#map-status').classList.toggle('is-error', error);
};
const currentFloor = () => data.floors.find(floor => floor.number === activeFloor);
const searchKey = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase();
function syncURL() {
  const url = new URL(data.url, location.origin);
  url.searchParams.set('floor', activeFloor);
  for (const key of ['start', 'end']) if ($('#'+key).value) url.searchParams.set(key, $('#'+key).value);
  if ($('#route-mode').value !== 'visit') url.searchParams.set('mode', $('#route-mode').value);
  if (view === '2d') url.searchParams.set('view', view);
  if (overview) url.searchParams.set('overview', '1');
  history.replaceState(null, '', url);
}
function fillPlaces() {
  for (const name of ['start', 'end']) {
    const select = $('#'+name); select.replaceChildren();
    if (name === 'start') select.add(new Option('Chọn phòng hoặc vị trí', ''));
    for (const floor of data.floors) {
      const group = document.createElement('optgroup'); group.label = 'Tầng '+floor.number;
      for (const place of data.places.filter(p => p.floor === floor.number)) group.append(new Option(place.label+' · Tầng '+floor.number, place.id));
      select.append(group);
    }
    select.value = data.route[name+'_id'];
  }
  $('#route-mode').value = data.route.mode;
}
function choose(pick) {
  if (pick.floor !== undefined) { activeFloor = pick.floor; overview = false; zoom2D = 1; }
  selected = pick.id || '';
  if (selected && !$('#start').value) {
    $('#start').value = selected;
    render(); requestRoute(); return;
  }
  render(); syncURL();
}
function renderDirectory() {
  const query = searchKey($('#map-search').value.trim());
  const places = data.places.filter(p => (query || overview || p.floor === activeFloor) && (!query || searchKey(p.label+' tang '+p.floor).includes(query)));
  $('#map-directory-title').textContent = query || overview ? 'Địa điểm trong tòa nhà' : 'Địa điểm trong tầng';
  $('#map-directory-count').textContent = places.length;
  $('#map-directory-empty').hidden = places.length > 0;
  $('#map-directory').replaceChildren(...places.map(place => {
    const button = element('button', '', 'indoor-directory-item'+(place.id === selected ? ' is-selected' : ''));
    button.type = 'button';
    button.append(element('span', place.kind === 'lift' ? '↕' : place.kind === 'entrance' ? '↗' : '⌂', 'indoor-place-icon'));
    const text = element('span');
    const room = data.floors.find(f => f.number === place.floor)?.rooms.find(r => r.id === place.id);
    text.append(element('strong', place.label), element('small', 'Tầng '+place.floor+(place.blocked ? ' · Đang bị chặn' : room ? ' · '+room.status : '')));
    button.append(text); button.addEventListener('click', () => choose({ id: place.id, floor: place.floor }));
    return button;
  }));
}
function renderSelection() {
  const panel = $('#map-selection'), place = data.places.find(p => p.id === selected);
  panel.hidden = !place; panel.replaceChildren();
  if (!place) return;
  panel.append(element('h3', place.label), element('p', 'Tầng '+place.floor+(place.blocked ? ' · Có vùng chặn' : '')));
  const actions = element('div', '', 'indoor-selection-actions');
  for (const [key, text] of [['start', 'Đi từ đây'], ['end', 'Đến đây']]) {
    const button = element('button', text); button.type = 'button';
    button.addEventListener('click', () => {
      $('#'+key).value = place.id;
      if (key === 'end') $('#route-mode').value = 'visit';
      requestRoute();
    }); actions.append(button);
  }
  panel.append(actions);
  if (place.kind === 'lift') {
    panel.append(element('p', 'Thang máy nối các tầng. Chọn tầng để xem mặt bằng:'));
    const floors = element('div', '', 'indoor-lift-floors');
    for (const floor of data.floors) {
      const button = element('button', 'Tầng '+floor.number); button.type = 'button';
      button.addEventListener('click', () => choose({ id: 'lift:'+floor.number, floor: floor.number })); floors.append(button);
    }
    panel.append(floors);
  }
}
function renderSummary() {
  const route = data.route;
  $('#route-summary').hidden = !route.start_id;
  $('#route-destination').textContent = route.found ? route.destination : 'Chưa có tuyến khả dụng';
  $('#route-distance').textContent = route.found ? (route.transfers.length ? 'Di chuyển liên tầng bằng thang máy' : 'Di chuyển trên cùng một tầng') : route.reason;
  const steps = [];
  if (route.found) {
    const first = route.points[0], last = route.points.at(-1);
    steps.push({ text: first.label+' · Tầng '+first.floor, floor: first.floor });
    if (route.transfers.length) {
      const from = route.transfers[0].from, to = route.transfers.at(-1).to;
      steps.push({ text: 'Theo hành lang đến thang máy · Tầng '+from, floor: from });
      steps.push({ text: 'Đi thang máy: tầng '+from+' → tầng '+to, floor: to });
      steps.push({ text: 'Ra thang máy, theo hành lang đến điểm đích', floor: to });
    } else if (first.id !== last.id) steps.push({ text: 'Qua cửa phòng và hành lang', floor: first.floor });
    steps.push({ text: last.label+' · Tầng '+last.floor, floor: last.floor });
  }
  $('#route-steps').replaceChildren(...steps.map(step => {
    const li = element('li'), button = element('button', step.text, 'indoor-route-step');
    button.type = 'button'; button.addEventListener('click', () => choose({ floor: step.floor })); li.append(button); return li;
  }));
  $('#end').disabled = $('#route-mode').value === 'evacuation';
}
function renderHazards() {
  const zones = data.zones.filter(zone => zone.floor === activeFloor), container = $('#map-hazards');
  container.replaceChildren(element('h4', 'Vùng cảnh báo · Tầng '+activeFloor));
  if (!zones.length) container.append(element('p', 'Tầng này chưa gắn vùng cảnh báo.'));
  for (const zone of zones) {
    const row = element('div', '', 'indoor-hazard-row');
    row.dataset.zoneId = zone.id;
    row.append(element('span', zone.name+(zone.mapped ? '' : ' · Chưa định vị lại')));
    if (data.can_simulate) {
      const button = element('button', zone.simulation ? 'Bỏ chặn' : 'Chặn thử'); button.type = 'button'; button.disabled = mutationBusy;
      button.addEventListener('click', () => toggleHazard(zone)); row.append(button);
    } else if (zone.hazard) row.append(element('strong', 'Đang bị chặn'));
    container.append(row);
  }
  const cameras = data.cameras.filter(camera => camera.floor === activeFloor);
  $('#map-cameras').replaceChildren(element('h4', 'Camera'), ...cameras.map(camera => element('p', camera.name+' · '+(camera.active ? 'Đang bật' : 'Tắt')+(camera.location ? '' : ' · Chưa định vị lại'))));
  if (!cameras.length) $('#map-cameras').append(element('p', 'Chưa gắn camera cho tầng này.'));
  const devices = data.devices.filter(device => device.floor === activeFloor);
  if (devices.length) $('#map-cameras').append(element('h4', 'Thiết bị PCCC đã lưu'), ...devices.map(device => element('p', device.name+' · Chưa định vị lại trên mặt bằng mới')));
}
const NS = 'http://www.w3.org/2000/svg';
function svgNode(parent, tag, attrs = {}, text = '') {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.textContent = text; parent.append(node); return node;
}
function floorSVG(floor, compact = false) {
  const svg = document.createElementNS(NS, 'svg');
  const small = $('#map-canvas-host').clientWidth < 500;
  const left = floor.min_x-1, width = floor.max_x-left+1.2, top = -7.7, height = 15.2;
  const scale = compact ? 1 : zoom2D;
  svg.setAttribute('viewBox', [left+(width-width/scale)/2, top+(height-height/scale)/2, width/scale, height/scale].join(' '));
  svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Mặt bằng 2D tầng '+floor.number);
  svg.setAttribute('class', 'indoor-plan-svg');
  const rect = (x, z, w, h, fill, stroke = '#b8b5a8', extra = {}) => svgNode(svg, 'rect', { x, y: z, width: w, height: h, fill, stroke, 'stroke-width': .055, ...extra });
  const text = (x, z, value, size = .31, fill = '#435348') => svgNode(svg, 'text', { x, y: z, fill, 'font-size': size, 'text-anchor': 'middle', 'font-family': 'system-ui, sans-serif' }, value);
  const action = (node, place, label) => {
    node.setAttribute('tabindex', '0'); node.setAttribute('role', 'button'); node.setAttribute('aria-label', label); node.style.cursor = 'pointer';
    const click = () => choose({ id: place, floor: floor.number }); node.addEventListener('click', click);
    node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); click(); } });
  };
  rect(floor.min_x, -6.8, floor.max_x-floor.min_x, 10.5, '#e6e0cf', '#afa68f');
  rect(floor.min_x+.14, .06, floor.max_x-floor.min_x-.28, 3.5, floor.blocked ? '#edb6a5' : '#f4f0e6');
  for (const room of floor.rooms) {
    const group = svgNode(svg, 'g', { 'data-plan-room': room.number });
    const body = svgNode(group, 'rect', { x: room.x-1.7, y: -6.6, width: 3.4, height: 6.6, fill: room.hazard ? '#f0b7a4' : room.id === selected ? '#ece0c7' : '#fffdf6', stroke: '#b5ad99', 'stroke-width': .08 });
    // Diagram symbols are simplified; the 3D floor uses the actual tour interiors.
    svgNode(group, 'rect', { x: room.x-1.36, y: -6.25, width: 1.45, height: 2.1, rx: .08, fill: '#d8e1d2', stroke: '#aab9a5', 'stroke-width': .04 });
    svgNode(group, 'rect', { x: room.x-1.23, y: -6.1, width: 1.19, height: .4, rx: .06, fill: '#fffcf3' });
    svgNode(group, 'rect', { x: room.x+.45, y: -6.24, width: .95, height: 1.4, fill: '#e7e0d0', stroke: '#c5bca6', 'stroke-width': .04 });
    const label = svgNode(group, 'text', { x: room.x, y: -2.8, fill: '#354638', 'font-size': small ? .68 : .4, 'font-weight': 600, 'text-anchor': 'middle', 'font-family': 'system-ui, sans-serif' }, room.number);
    body.style.pointerEvents = 'all'; label.style.pointerEvents = 'none';
    svgNode(group, 'line', { x1: room.x, y1: 0, x2: room.x+1.1, y2: 0, stroke: '#fffdf6', 'stroke-width': .16 });
    svgNode(group, 'path', { d: 'M '+room.x+' 0 v -1.1 M '+room.x+' -1.1 a 1.1 1.1 0 0 1 1.1 1.1', fill: 'none', stroke: '#a78b5e', 'stroke-width': .045 });
    action(group, room.id, room.label+' · Tầng '+floor.number);
  }
  const lift = rect(floor.lift_x-1.35, .17, 2.7, 3.36, '#d4e1db', '#688b7a', { 'data-plan-lift': floor.number });
  action(lift, 'lift:'+floor.number, 'Thang máy tầng '+floor.number);
  text(floor.lift_x, 1.4, '↕', small ? .85 : .75);
  if (small) { text(floor.lift_x, 2.15, 'Thang', .48); text(floor.lift_x, 2.72, 'máy', .48); }
  else text(floor.lift_x, 2.4, 'Thang máy', .3);
  text((floor.lift_x+1.35+floor.max_x)/2, 1.22, 'HÀNH LANG', .27, '#99927f');
  if (floor.entrance_x !== null) {
    rect(floor.entrance_x-1.4, 3.62, 2.8, 2.5, '#e2e8d6', '#a5b392');
    text(floor.entrance_x, 5.55, '↑', .7); const label = text(floor.entrance_x, 6.7, 'Lối vào tòa nhà', .37);
    action(label, 'entrance:'+floor.number, 'Lối vào tòa nhà');
  } else text((floor.min_x+floor.max_x)/2, 4.65, 'Mặt ngoài tòa nhà', .28, '#8a9185');
  const points = data.route.points;
  for (let i = 1; i < points.length; i++) {
    const a = points[i-1], b = points[i];
    if (a.floor === floor.number && b.floor === floor.number) svgNode(svg, 'line', { x1: a.x, y1: a.z, x2: b.x, y2: b.z, stroke: '#c65a26', 'stroke-width': .12, 'stroke-linecap': 'round', 'pointer-events': 'none' });
  }
  for (const point of [points[0], points.at(-1)]) if (point?.floor === floor.number) svgNode(svg, 'circle', { cx: point.x, cy: point.z, r: .18, fill: '#c65a26', stroke: '#fff', 'stroke-width': .06, 'pointer-events': 'none' });
  return svg;
}
function render2D() {
  const host = $('#map-fallback'); host.replaceChildren(); host.classList.toggle('is-overview', overview);
  const shown = overview ? [...data.floors].reverse() : data.floors.filter(f => f.number === activeFloor);
  for (const floor of shown) {
    if (overview) {
      const card = element('section', '', 'indoor-plan-card'), title = element('button', 'Tầng '+floor.number+' · '+floor.rooms.length+' phòng');
      title.type = 'button'; title.addEventListener('click', () => choose({ floor: floor.number }));
      card.append(title, floorSVG(floor, true)); host.append(card);
    } else host.append(floorSVG(floor));
  }
  if (!shown.length) host.append(element('p', 'Chưa có phòng để dựng mặt bằng.'));
}
function render() {
  const floor = currentFloor(), count = data.floors.reduce((sum, f) => sum+f.rooms.length, 0);
  $('#map-building-meta').textContent = data.floors.length+' TẦNG · '+count+' PHÒNG';
  $('#map-floor-description').textContent = overview ? 'Toàn bộ tòa nhà · '+data.floors.length+' tầng' : 'Tầng '+activeFloor+' · '+(floor?.rooms.length || 0)+' phòng';
  $('#map-context').textContent = overview ? 'Các tầng nối bằng thang máy · Bấm tầng để xem chi tiết' : 'Tầng '+activeFloor+' · '+(floor?.rooms.length || 0)+' phòng cùng hành lang · Thang máy ở đầu dãy';
  for (const button of $$('[data-map-floor]')) {
    const active = !overview && Number(button.dataset.mapFloor) === activeFloor;
    button.classList.toggle('is-active', active); button.setAttribute('aria-pressed', active);
  }
  $('[data-map-overview]').classList.toggle('is-active', overview); $('[data-map-overview]').setAttribute('aria-pressed', overview);
  for (const button of $$('[data-map-view]')) {
    const active = button.dataset.mapView === view;
    button.classList.toggle('is-active', active); button.setAttribute('aria-pressed', active);
  }
  $('#map-fallback').hidden = view !== '2d'; $('#indoor-map-3d').hidden = view !== '3d'; $('#map-labels').hidden = view !== '3d';
  $('[data-map-action="rotate"]').disabled = view === '2d';
  $('.indoor-map-gesture-hint').textContent = view === '3d' ? 'Kéo để xoay · Cuộn để thu phóng · Bấm phòng để chọn' : 'Bấm phòng để chọn · Chuyển tầng ở phía trên';
  renderer?.setVisible(view === '3d');
  if (view === '3d') renderer?.update(data, activeFloor, overview, selected); else render2D();
  renderDirectory(); renderSelection(); renderSummary(); renderHazards();
  const warnings = [...data.warnings];
  if (unavailable3D) warnings.push('Trình duyệt chưa hiển thị được 3D. Bản đồ 2D và chỉ đường vẫn sử dụng được.');
  $('#map-warnings').hidden = warnings.length === 0; $('#map-warnings').textContent = warnings.join(' ');
  status(data.floors.length ? data.route.start_id ? data.route.reason : 'Chọn phòng để xem vị trí hoặc tìm đường.' : 'Chưa có phòng trong phạm vi truy cập.');
}
async function requestRoute({ quiet = false } = {}) {
  const number = ++requestNumber; pending?.abort(); const controller = new AbortController(); pending = controller;
  const url = new URL(data.url, location.origin);
  url.searchParams.set('format', 'json'); url.searchParams.set('floor', activeFloor);
  for (const key of ['start', 'end']) url.searchParams.set(key, $('#'+key).value);
  url.searchParams.set('mode', $('#route-mode').value);
  if (!quiet) status('Đang tìm đường…');
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Không tải được bản đồ');
    const next = await response.json();
    if (number !== requestNumber) return;
    if (next.schema_version !== 2) throw new Error('Sai phiên bản bản đồ');
    data = next;
    if (!data.floors.some(f => f.number === activeFloor)) activeFloor = data.floor;
    fillPlaces();
    // Evacuation always targets the ground entrance, never an arbitrary room.
    $('#end').value = data.route.end_id; render(); syncURL();
  } catch (error) {
    if (error.name === 'AbortError' || number !== requestNumber) return;
    data.route = { ...data.route, found: false, points: [], transfers: [], reason: 'Không cập nhật được đường đi. Vui lòng thử lại.', start_id: $('#start').value };
    render(); status('Không kết nối được bản đồ. Kiểm tra mạng rồi bấm Tìm đường để thử lại.', true);
  } finally { if (number === requestNumber) pending = null; }
}
async function toggleHazard(zone) {
  if (mutationBusy) return;
  mutationBusy = true; renderHazards();
  try {
    const body = new URLSearchParams({ csrfmiddlewaretoken: $('#map-csrf input').value });
    const response = await fetch(zone.url, { method: 'POST', body, headers: { Accept: 'application/json' } });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Không cập nhật được vùng mô phỏng');
    await requestRoute();
  } catch { status('Không đổi được vùng mô phỏng. Vui lòng thử lại.', true); }
  finally { mutationBusy = false; renderHazards(); }
}
fillPlaces();
try {
  renderer = createBuildingScene($('#indoor-map-3d'), $('#map-labels'), choose, () => {
    unavailable3D = true; view = '2d'; $('[data-map-view="3d"]').disabled = true; render();
  });
} catch {
  unavailable3D = true; view = '2d'; $('[data-map-view="3d"]').disabled = true;
}
for (const button of $$('[data-map-floor]')) button.addEventListener('click', () => choose({ floor: Number(button.dataset.mapFloor) }));
$('[data-map-overview]').addEventListener('click', () => { overview = true; selected = ''; zoom2D = 1; render(); syncURL(); });
for (const button of $$('[data-map-view]')) button.addEventListener('click', () => { view = button.dataset.mapView; zoom2D = 1; render(); syncURL(); });
$('#map-search').addEventListener('input', renderDirectory);
$('#map-route-form').addEventListener('submit', event => { event.preventDefault(); requestRoute(); });
for (const id of ['start', 'end', 'route-mode']) $('#'+id).addEventListener('change', () => requestRoute());
for (const button of $$('[data-map-action]')) button.addEventListener('click', async () => {
  const action = button.dataset.mapAction;
  if (action === 'fullscreen') {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('.indoor-map-stage').requestFullscreen(); }
    catch { status('Trình duyệt chưa hỗ trợ chế độ toàn màn hình.', true); }
  } else if (view === '3d') renderer?.action(action);
  else { zoom2D = action === 'reset' ? 1 : Math.max(.65, Math.min(3, zoom2D*(action === 'zoom-in' ? 1.2 : .83))); render2D(); }
});
const refresh = setInterval(() => { if (!document.hidden && !pending && !mutationBusy) requestRoute({ quiet: true }); }, 30000);
window.addEventListener('resize', () => { if (view === '2d') render2D(); });
window.addEventListener('pagehide', event => { pending?.abort(); if (!event.persisted) { clearInterval(refresh); renderer?.destroy(); } });
render();
