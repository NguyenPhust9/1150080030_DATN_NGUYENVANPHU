import * as THREE from 'three';
import { OrbitControls } from '../vendor/three/OrbitControls.js';
import { buildA101World } from './a101-world.js?v=a105-tour-1';
import { buildA102World } from './a102-world.js?v=a105-tour-1';
import { buildA103World } from './a103-world.js?v=a105-tour-1';
import { buildA104World } from './a104-world.js?v=a105-tour-1';
import { buildA105World } from './a105-world.js?v=a105-tour-1';
import { buildGenericRoomWorld } from './generic-room-world.js?v=building-tour-1';

// Only this map's new mesh instances are clipped. The original tour builders,
// camera, collisions, interior geometry and assets are never changed.
const builders = { A101: buildA101World, A102: buildA102World, A103: buildA103World, A104: buildA104World, A105: buildA105World };

function dispose(group) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  group.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of [].concat(object.material || [])) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  textures.forEach(texture => texture.dispose());
  materials.forEach(material => material.dispose());
  geometries.forEach(geometry => geometry.dispose());
  group.removeFromParent();
}

export function createBuildingScene(canvas, labelHost, onPick, onContextLost) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.localClippingEnabled = true;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight('#ffffff', '#888779', 3));
  const sun = new THREE.DirectionalLight('#fff5df', 3); sun.position.set(-12, 24, 12); scene.add(sun);
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 400);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.dampingFactor = .08;
  controls.minDistance = 8; controls.maxDistance = 130;
  controls.maxPolarAngle = Math.PI / 2 - .06;
  let world = new THREE.Group(), overlay = new THREE.Group();
  scene.add(world, overlay);
  let labels = [], pickables = [], signature = '', data, overview = false, floorNumber, alive = true, visible = true;
  const cube = () => new THREE.BoxGeometry(1, 1, 1);
  function box(parent, x, y, z, w, h, d, color, opacity = 1) {
    const mesh = new THREE.Mesh(cube(), new THREE.MeshStandardMaterial({ color, roughness: .8, transparent: opacity < 1, opacity, depthWrite: opacity === 1 }));
    mesh.position.set(x, y, z); mesh.scale.set(w, h, d); parent.add(mesh); return mesh;
  }
  function label(text, position, pick, className = '') {
    const button = document.createElement('button');
    button.type = 'button'; button.className = `map-poi-label ${className}`; button.textContent = text;
    button.addEventListener('click', () => onPick(pick)); labelHost.append(button);
    labels.push({ button, position: new THREE.Vector3(...position), pick });
  }
  function floorY(floor) { return overview ? floor.elevation : 0; }
  function reset() {
    if (!data?.floors.length) return;
    const floors = overview ? data.floors : data.floors.filter(f => f.number === floorNumber);
    const left = Math.min(...floors.map(f => f.min_x)), right = Math.max(...floors.map(f => f.max_x));
    const center = (left + right) / 2;
    const height = overview ? Math.max(...floors.map(f => f.elevation)) : 0;
    controls.target.set(center, height / 2, -1.1);
    // Portrait screens require a wider distance to keep the whole slab in view.
    const distance = Math.max(right-left, height + 11, 17) * Math.max(1, 1 / camera.aspect) * 1.35;
    camera.position.copy(controls.target).add(new THREE.Vector3(distance * .36, distance * .78, distance * .93));
    controls.update();
  }
  function resize() {
    const { width, height } = canvas.parentElement.getBoundingClientRect();
    renderer.setSize(Math.max(width, 1), Math.max(height, 1), false);
    camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix();
  }
  const observer = new ResizeObserver(() => { resize(); reset(); }); observer.observe(canvas.parentElement);
  function rebuild() {
    dispose(world); world = new THREE.Group(); scene.add(world);
    labelHost.replaceChildren(); labels = []; pickables = [];
    const shown = overview ? data.floors : data.floors.filter(f => f.number === floorNumber);
    for (const floor of shown) {
      const y = floorY(floor), width = floor.max_x-floor.min_x, center = (floor.max_x+floor.min_x)/2;
      const group = new THREE.Group(); group.position.y = y; world.add(group);
      box(group, center, -.19, -1.5, width+.25, .32, 10.6, '#c8c6b9');
      box(group, center, -.01, 1.85, width, .08, 3.7, '#eeeadf');
      for (let x = Math.ceil(floor.min_x); x < floor.max_x; x += 1.2) box(group, x, .035, 1.85, .018, .005, 3.6, '#d6d1c4');
      box(group, floor.min_x, .64, -1.5, .15, 1.28, 10.6, '#d0c5ad');
      box(group, floor.max_x, .64, -1.5, .15, 1.28, 10.6, '#d0c5ad');
      box(group, center, .64, -6.78, width, 1.28, .15, '#d0c5ad');
      const sections = floor.entrance_x === null ? [[floor.min_x, floor.max_x]] : [[floor.min_x, floor.entrance_x-1.4], [floor.entrance_x+1.4, floor.max_x]];
      for (const [left, right] of sections) {
        box(group, (left+right)/2, .38, 3.7, right-left, .76, .12, '#d5ceb9');
        box(group, (left+right)/2, 1.01, 3.7, right-left, .5, .055, '#adc6c4', .45);
        box(group, (left+right)/2, 1.28, 3.7, right-left, .055, .1, '#5a6d61');
      }
      for (const room of floor.rooms) {
        if (!overview) {
          const interior = new THREE.Group(); group.add(interior);
          if (builders[room.profile]) builders[room.profile](THREE, interior, { offsetX: room.x, includeLanding: false });
          else buildGenericRoomWorld(THREE, interior, { offsetX: room.x, number: room.number });
          const cut = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1.65);
          interior.traverse(object => {
            if (object.isLight) object.visible = false;
            if (object.isMesh) {
              for (const material of [].concat(object.material)) { material.clippingPlanes = [cut]; material.clipShadows = true; }
            }
          });
        } else {
          box(group, room.x, .02, -3.3, 3.4, .09, 6.6, '#f2eee4');
          for (const x of [room.x-1.77, room.x+1.77]) box(group, x, .64, -3.3, .12, 1.28, 6.6, '#ddd5c4');
          // The same doorway is visible in the overview and detailed floor.
          box(group, room.x-.85, .64, 0, 1.7, 1.28, .12, '#d1ccb9');
          box(group, room.x+1.45, .64, 0, .6, 1.28, .12, '#d1ccb9');
          box(group, room.x-.55, .25, -4.65, 1.3, .45, 1.9, '#aabaaa');
        }
        const hit = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 6.6), new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide }));
        hit.rotation.x = -Math.PI/2; hit.position.set(room.x, .12, -3.3); hit.userData.pick = { id: room.id, floor: floor.number }; group.add(hit); pickables.push(hit);
        if (!overview) label(room.number, [room.x, y+1.9, -2.7], hit.userData.pick);
      }
      box(group, floor.lift_x, .04, 1.85, 2.58, .12, 3.36, '#8eaba4');
      box(group, floor.lift_x-1.35, .72, 1.85, .14, 1.44, 3.5, '#768e84');
      box(group, floor.lift_x, .72, .17, 2.7, 1.44, .14, '#9cafa4');
      box(group, floor.lift_x, .65, 3.53, 2.7, 1.3, .07, '#9cbab3', .55);
      if (!overview) label('↕ Thang máy', [floor.lift_x, y+1.6, 1.85], { id: `lift:${floor.number}`, floor: floor.number }, 'is-lift');
      if (floor.entrance_x !== null) {
        box(group, floor.entrance_x, -.04, 5, 2.8, .12, 2.6, '#d1d9c4');
        if (!overview) label('Lối vào tòa nhà', [floor.entrance_x, y+.35, 5.8], { id: `entrance:${floor.number}`, floor: floor.number }, 'is-exit');
      }
      if (overview) label(`Tầng ${floor.number} · ${floor.rooms.length} phòng`, [floor.max_x+.4, y+1.15, 3.8], { floor: floor.number }, 'is-floor');
    }
    if (overview && shown.length > 1) {
      const first = shown[0], last = shown.at(-1), height = last.elevation-first.elevation;
      box(world, first.lift_x, first.elevation+height/2+.5, 1.85, 2.65, height+1, 3.25, '#709588', .13);
      for (const x of [first.lift_x-1.25, first.lift_x+1.25]) box(world, x, first.elevation+height/2, 3.42, .075, height, .075, '#426959');
      label('↕ Thang máy liên tầng', [first.lift_x-1, last.elevation+2, 1.85], { id: `lift:${floorNumber}`, floor: floorNumber }, 'is-lift');
    }
    reset();
  }
  function paint(selected) {
    dispose(overlay); overlay = new THREE.Group(); scene.add(overlay);
    for (const floor of data.floors) {
      if (!overview && floor.number !== floorNumber) continue;
      const y = floorY(floor);
      if (floor.blocked) box(overlay, (floor.min_x+floor.max_x)/2, y+.07, 1.85, floor.max_x-floor.min_x, .04, 3.6, '#dc795d', .45);
      for (const room of floor.rooms) if (room.hazard || room.id === selected) box(overlay, room.x, y+.09, -3.3, 3.3, .03, 6.5, room.hazard ? '#d9684d' : '#d5a86d', .33);
    }
    const points = data.route.points;
    for (let i = 1; i < points.length; i++) {
      const a = points[i-1], b = points[i];
      if (!overview && (a.floor !== floorNumber || b.floor !== floorNumber)) continue;
      const start = new THREE.Vector3(a.x, (overview ? a.y : 0)+.18, a.z);
      const end = new THREE.Vector3(b.x, (overview ? b.y : 0)+.18, b.z);
      if (start.distanceTo(end) < .001) continue;
      const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.LineCurve3(start, end), 1, .065, 6, false), new THREE.MeshBasicMaterial({ color: '#c65a26', depthTest: false }));
      tube.renderOrder = 5; overlay.add(tube);
    }
    for (const endpoint of [points[0], points.at(-1)]) if (endpoint && (overview || endpoint.floor === floorNumber)) {
      const sphere = new THREE.Mesh(new THREE.SphereGeometry(.15, 12, 8), new THREE.MeshBasicMaterial({ color: '#c65a26', depthTest: false }));
      sphere.position.set(endpoint.x, (overview ? endpoint.y : 0)+.2, endpoint.z); sphere.renderOrder = 6; overlay.add(sphere);
    }
    for (const entry of labels) {
      entry.button.classList.toggle('is-selected', entry.pick.id === selected);
      entry.button.classList.toggle('is-hazard', data.places.some(p => p.id === entry.pick.id && p.blocked));
    }
  }
  function update(next, activeFloor, allFloors, selected) {
    data = next; floorNumber = activeFloor; overview = allFloors;
    const nextSignature = JSON.stringify([activeFloor, allFloors, data.floors.map(f => [f.number, f.rooms.map(r => [r.id, r.x])])]);
    if (signature !== nextSignature) { signature = nextSignature; rebuild(); }
    paint(selected);
  }
  let pointerDown;
  canvas.addEventListener('pointerdown', event => { pointerDown = [event.clientX, event.clientY]; });
  canvas.addEventListener('pointerup', event => {
    if (!pointerDown || Math.hypot(event.clientX-pointerDown[0], event.clientY-pointerDown[1]) > 5) return;
    const rect = canvas.getBoundingClientRect(), ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1, -(event.clientY-rect.top)/rect.height*2+1), camera);
    const hit = ray.intersectObjects(pickables)[0]; if (hit) onPick(hit.object.userData.pick);
  });
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); visible = false; onContextLost(); });
  function frame() {
    if (!alive) return;
    requestAnimationFrame(frame);
    if (!visible || document.hidden) return;
    controls.update(); renderer.render(scene, camera);
    const width = canvas.clientWidth, height = canvas.clientHeight;
    for (const entry of labels) {
      const position = entry.position.clone().project(camera);
      entry.button.hidden = position.z > 1 || position.z < -1 || Math.abs(position.x) > 1 || Math.abs(position.y) > 1;
      entry.button.style.left = `${(position.x*.5+.5)*width}px`;
      entry.button.style.top = `${(-position.y*.5+.5)*height}px`;
    }
  }
  resize(); frame();
  return {
    update, reset,
    setVisible(value) { visible = value; canvas.hidden = !value; labelHost.hidden = !value; },
    action(action) {
      if (action === 'reset') reset();
      if (action === 'zoom-in' || action === 'zoom-out') camera.position.sub(controls.target).multiplyScalar(action === 'zoom-in' ? .85 : 1.18).add(controls.target);
      if (action === 'rotate') camera.position.sub(controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI/8).add(controls.target);
      controls.update();
    },
    destroy() { alive = false; observer.disconnect(); controls.dispose(); dispose(world); dispose(overlay); renderer.dispose(); labelHost.replaceChildren(); },
  };
}
