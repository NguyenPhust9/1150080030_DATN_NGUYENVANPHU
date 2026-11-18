// The envelope surrounds the established rooms; it never rebuilds their interiors.
export function buildTourBuildingEnvelope(THREE, parent, { minX, maxX, liftEdgeX, floor, floors, groundFloor, pathX }) {
  const group = new THREE.Group(); group.name = 'tour-building-envelope'; parent.add(group);
  const obstacles = [], cameraObstacles = [];
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const plaster = new THREE.MeshStandardMaterial({ color: '#e7dfcf', roughness: .85 });
  const stone = new THREE.MeshStandardMaterial({ color: '#c9b28d', roughness: .8 });
  const frame = new THREE.MeshStandardMaterial({ color: '#465b52', roughness: .55, metalness: .35 });
  const glass = new THREE.MeshStandardMaterial({ color: '#c3dcd7', transparent: true, opacity: .24,
    depthWrite: false, roughness: .3, metalness: .05 });
  const glow = new THREE.MeshStandardMaterial({ color: '#fff5dc', emissive: '#fff0cc', emissiveIntensity: .55 });
  const width = maxX - minX, centerX = (minX + maxX) / 2;
  const groundY = (groundFloor - floor) * 4.8;
  const isGroundFloor = floor === groundFloor;
  const entranceX = Math.max(liftEdgeX + 1.65, Math.min(maxX - 1.65, pathX));
  const entrance = { x: entranceX, minX: entranceX - 1.4, maxX: entranceX + 1.4, z: 3.7 };
  const porch = { minX: Math.min(entrance.minX - .3, pathX - 2.55), maxX: Math.max(entrance.maxX + .3, pathX + 2.55), minZ: 3.4, maxZ: 6.6 };
  const path = { minX: pathX - 2.55, maxX: pathX + 2.55, minZ: 6.1, maxZ: 33.7 };
  function box(name, x, y, z, w, h, d, material, collide = true) {
    const mesh = new THREE.Mesh(geometry, material); mesh.name = name;
    mesh.position.set(x, y, z); mesh.scale.set(w, h, d);
    mesh.castShadow = mesh.receiveShadow = true; group.add(mesh);
    if (collide) {
      obstacles.push({ minX: x - w / 2, maxX: x + w / 2, minZ: z - d / 2, maxZ: z + d / 2, minY: y - h / 2, maxY: y + h / 2 });
      cameraObstacles.push(mesh);
    }
    return mesh;
  }
  function facade(left, right, y, active) {
    if (right <= left) return;
    const span = right - left, cx = (left + right) / 2;
    box('facade-sill', cx, y + .48, 3.7, span, .96, .24, plaster, active);
    box('facade-header', cx, y + 3.92, 3.7, span, 1.16, .24, plaster, active);
    const bays = Math.max(1, Math.ceil(span / 3.6)), bayWidth = span / bays;
    for (let i = 0; i < bays; i++) {
      const x = left + (i + .5) * bayWidth;
      box('corridor-window', x, y + 2.15, 3.7, bayWidth - .15, 2.38, .06, glass, active);
      box('window-mullion', x, y + 2.15, 3.66, .045, 2.38, .09, frame, active);
      for (const h of [1, 3.3]) box('window-frame', x, y + h, 3.66, bayWidth, .065, .1, frame, active);
    }
    for (let i = 0; i <= bays; i++) box('facade-pier', left + i * bayWidth, y + 2.15, 3.7, .16, 2.4, .24, plaster, active);
  }
  // Close both corridor ends, the rear and the top from outside the room shells.
  const bottom = groundY, top = (Math.max(...floors) - floor) * 4.8 + 4.65;
  for (const x of [minX - .06, maxX + .06]) box('building-end-wall', x, (bottom + top) / 2, -1.55, .2, top - bottom, 10.7, plaster);
  box('building-rear-wall', centerX, (bottom + top) / 2, -6.86, width, top - bottom, .16, plaster);
  box('building-roof', centerX, top + .08, -1.55, width + .4, .16, 10.9, stone);
  for (const level of new Set([groundFloor, ...floors])) {
    const y = (level - floor) * 4.8, active = level === floor;
    if (level === groundFloor) {
      facade(minX, entrance.minX, y, active);
      facade(entrance.maxX, maxX, y, active);
      box('entrance-lintel', entranceX, y + 3.85, 3.7, 2.8, 1.3, .28, plaster, active);
      for (const x of [entrance.minX, entrance.maxX]) box('entrance-jamb', x, y + 1.6, 3.7, .12, 3.2, .36, frame, active);
      box('entrance-frame', entranceX, y + 3.14, 3.7, 2.8, .12, .36, frame, active);
    } else facade(minX, maxX, y, active);
    // This ceiling covers only the shared corridor, leaving every room ceiling intact.
    box('corridor-ceiling', centerX, y + 4.45, 1.85, width, .18, 3.8, plaster, active);
    box('facade-storey-band', centerX, y + 4.63, 3.78, width + .2, .18, .44, stone, false);
  }
  for (let x = liftEdgeX + 1.4; x < maxX - .5; x += 3.6) {
    box('corridor-light', x, 4.34, 1.8, .85, .035, .25, glow, false);
    const light = new THREE.PointLight(0xfff3de, 5, 5.5, 2); light.position.set(x, 3.7, 1.8); group.add(light);
  }
  // A level apron bridges the old floating edge to the existing central garden walk.
  box('entrance-apron', (porch.minX + porch.maxX) / 2, groundY - .08, 4.8, porch.maxX - porch.minX, .16, 3.6, stone, false);
  box('entrance-canopy', entranceX, groundY + 3.3, 4.65, 3.5, .18, 2.2, stone);
  box('entrance-light', entranceX, groundY + 3.2, 4.6, 1.2, .025, .24, glow, false);
  // A shallow ramp matches the existing courtyard paving without a step or gap.
  const ramp = box('entrance-ramp', pathX, groundY + .00125, 6.15, 5.1, .08, .9, stone, false);
  ramp.rotation.x = -Math.atan(.0825 / .9);
  const inRect = (rect, x, z, radius) => x >= rect.minX + radius && x <= rect.maxX - radius
    && z >= rect.minZ + radius && z <= rect.maxZ - radius;
  return {
    group, obstacles, cameraObstacles, entrance: isGroundFloor ? entrance : null, porch, path, isGroundFloor,
    contains(x, z, radius = .2) {
      return inRect({ minX: minX + .1, maxX: maxX - .1, minZ: -6.6, maxZ: 3.8 }, x, z, radius)
        || (isGroundFloor && (inRect(porch, x, z, radius) || inRect(path, x, z, radius)));
    },
    groundAt: z => isGroundFloor && z > 5.7 ? Math.min(.0825, (z - 5.7) / .9 * .0825) : 0,
    ceilingAt: (x, z) => z <= 3.8 ? 4.36
      : isGroundFloor && z <= 5.75 && Math.abs(x - entranceX) <= 1.75 ? 3.21 : Infinity,
  };
}
