// Navigation is driven solely by rooms the server has authorized for this visitor.
export function createBuildingNavigation({ config, openDialog, onDestination, onFloor }) {
  const details = config.roomDetails;
  const floors = [...new Set(details.map(room => room.floor))].sort((a, b) => a - b);
  const byNumber = new Map(details.map(room => [room.number, room]));
  const byFloor = floor => details.filter(room => room.floor === floor)
    .sort((a, b) => a.number.localeCompare(b.number, 'vi', { numeric: true })).reverse();
  let selected = byNumber.get(config.entryRoom) || details[0];
  let destination = null;
  let state = { floor: config.entryFloor, room: config.entryRoom, inside: false, nearElevator: false };
  let signature = '';
  const el = id => document.getElementById(id);
  const roomButtons = new Map();
  const floorRows = new Map();
  const floorButtons = new Map();
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const svgElement = (tag, attrs, text) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function floorPlan() {
    const rooms = byFloor(selected.floor), slot = 49;
    const width = Math.max(300, 50 + rooms.length * slot);
    const svg = svgElement('svg', { viewBox: `0 0 ${width} 134`, role: 'img', 'aria-label': `Hành lang tầng ${selected.floor}, thang máy và cửa phòng ${selected.number}` });
    svg.append(svgElement('rect', { x: 8, y: 12, width: 30, height: 68, rx: 3, fill: '#cbdce1', stroke: '#7a949d' }));
    svg.append(svgElement('text', { x: 23, y: 38, class: 'floor-plan-text' }, '⇅'));
    svg.append(svgElement('text', { x: 23, y: 58, class: 'floor-plan-text', 'font-size': 8 }, 'TM'));
    let targetX = 60;
    rooms.forEach((room, index) => {
      const x = 47 + index * slot, isTarget = room.number === selected.number;
      if (isTarget) targetX = x + 21;
      svg.append(svgElement('rect', { x, y: 12, width: 43, height: 68, rx: 2, class: `floor-plan-room${isTarget ? ' is-selected' : ''}` }));
      svg.append(svgElement('text', { x: x + 21, y: 29, class: 'floor-plan-text' }, room.number));
      svg.append(svgElement('rect', { x: x + 8, y: 39, width: 25, height: 30, rx: 2, class: 'floor-plan-bed' }));
      svg.append(svgElement('path', { d: `M ${x + 8} 47 h25`, stroke: '#b2bdac' }));
    });
    svg.append(svgElement('path', { d: `M23 83 V102 H${targetX} V80 m-4 5 l4 -5 l4 5`, class: 'floor-plan-path' }));
    svg.append(svgElement('text', { x: width / 2, y: 122, class: 'floor-plan-text' }, `Hành lang tầng ${selected.floor}`));
    el('selected-floor-plan').replaceChildren(svg);
  }

  function renderSelection() {
    roomButtons.forEach((button, number) => {
      const active = number === selected.number;
      button.classList.toggle('is-selected', active);
      button.setAttribute('aria-pressed', String(active));
    });
    el('selected-room-title').textContent = `Phòng ${selected.number} · Tầng ${selected.floor}`;
    el('selected-room-status').textContent = selected.statusLabel || 'Đang cập nhật';
    el('selected-room-status').dataset.status = selected.status;
    el('selected-room-model').textContent = selected.profile !== 'generic'
      ? 'Nội thất đã phỏng dựng theo tư liệu của phòng. Ảnh và video được giữ trong mục tư liệu.'
      : 'Nội thất mô phỏng cơ bản. Bố cục sẽ được dựng chi tiết hơn khi có tư liệu của phòng.';
    const steps = selected.floor === state.floor
      ? [`Bạn đang ở tầng ${state.floor}`, 'Đi theo đường xanh dọc hành lang', `Đi qua cửa để vào phòng ${selected.number}`]
      : ['Đi tới thang máy ở cuối hành lang', `Nhấn F và chọn tầng ${selected.floor}`, `Đi dọc hành lang vào phòng ${selected.number}`];
    el('selected-room-steps').replaceChildren(...steps.map(step => element('li', step)));
    el('building-route-start').textContent = `Chỉ đường tới ${selected.number}`;
    floorPlan();
  }

  for (const floor of [...floors].reverse()) {
    const rooms = byFloor(floor);
    const row = element('div', undefined, 'building-storey');
    row.dataset.floor = floor;
    const lift = element('div', undefined, 'storey-lift');
    lift.append(element('strong', `Tầng ${floor}`), element('span', '⇅', 'lift-symbol'));
    const roomList = element('div', undefined, 'storey-rooms');
    roomList.style.setProperty('--room-count', rooms.length);
    for (const room of rooms) {
      const button = element('button', undefined, 'building-room');
      button.type = 'button';
      button.dataset.buildingRoom = room.number;
      button.dataset.status = room.status;
      button.setAttribute('aria-label', `Phòng ${room.number}, tầng ${floor}, ${room.statusLabel || 'đang cập nhật'}`);
      button.append(element('strong', room.number), element('span', undefined, 'room-model-icon'));
      button.lastChild.setAttribute('aria-hidden', 'true');
      button.addEventListener('click', () => { selected = room; renderSelection(); });
      roomButtons.set(room.number, button);
      roomList.append(button);
    }
    row.append(lift, roomList);
    el('building-elevation').append(row);
    floorRows.set(floor, row);
    const floorButton = element('button');
    floorButton.type = 'button';
    floorButton.dataset.elevatorFloor = floor;
    floorButton.append(element('strong', `Tầng ${floor}`), element('small', `${rooms.length} phòng`));
    floorButton.addEventListener('click', () => {
      if (!state.nearElevator || floor === state.floor) return;
      el('tour-elevator-dialog').close();
      onFloor(floor);
    });
    floorButtons.set(floor, floorButton);
    el('elevator-floors').append(floorButton);
  }

  function openMap() { renderSelection(); openDialog('tour-building-dialog'); }
  function openElevator() {
    if (!state.nearElevator) return false;
    openDialog('tour-elevator-dialog');
    return true;
  }
  function setDestination(room) {
    destination = room;
    el('room-tour').dataset.destination = room?.number || '';
    el('tour-route').hidden = !room;
    if (room) el('route-destination').textContent = `${room.number} · Tầng ${room.floor}`;
    onDestination(room);
    signature = '';
    update(state);
  }
  el('tour-map').addEventListener('click', openMap);
  el('mini-map-open').addEventListener('click', openMap);
  el('tour-elevator').addEventListener('click', openElevator);
  el('building-route-start').addEventListener('click', () => {
    setDestination(selected);
    el('tour-building-dialog').close();
  });
  el('route-clear').addEventListener('click', () => setDestination(null));

  function update(next) {
    const nextSignature = `${next.floor}|${next.room}|${next.inside}|${next.nearElevator}`;
    state = next;
    if (signature === nextSignature) return;
    signature = nextSignature;
    el('tour-floor-label').textContent = `Tầng ${state.floor}`;
    el('mini-floor-label').textContent = `Vị trí của bạn · Tầng ${state.floor}`;
    el('building-location').textContent = `Bạn đang ở tầng ${state.floor}`;
    el('elevator-current').textContent = `Hiện tại: tầng ${state.floor}`;
    el('tour-elevator').hidden = !state.nearElevator;
    floorRows.forEach((row, floor) => row.classList.toggle('is-current', floor === state.floor));
    roomButtons.forEach((button, number) => button.classList.toggle('is-here', number === state.room && state.inside));
    floorButtons.forEach((button, floor) => {
      button.disabled = floor === state.floor;
      button.setAttribute('aria-current', String(floor === state.floor));
      button.classList.toggle('is-destination', floor === destination?.floor);
      const count = byFloor(floor).length;
      button.querySelector('small').textContent = floor === state.floor ? 'Bạn đang ở đây' : `${count} phòng${destination?.floor === floor ? ` · ${destination.number}` : ''}`;
    });
    if (destination) {
      el('route-instruction').textContent = state.floor !== destination.floor
        ? (state.nearElevator ? `Nhấn F hoặc nút thang máy, chọn tầng ${destination.floor}.` : `Đi theo đường xanh tới thang máy, lên tầng ${destination.floor}.`)
        : state.inside && state.room === destination.number ? `Bạn đã tới phòng ${destination.number}. Có thể tiếp tục tham quan.`
          : `Đi dọc hành lang theo đường xanh rồi vào cửa ${destination.number}.`;
    }
  }
  renderSelection();
  update(state);
  return { update, openMap, openElevator, get destination() { return destination; } };
}
