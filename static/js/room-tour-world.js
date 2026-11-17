import { buildA101World } from './a101-world.js?v=room-view-2';
import { buildA102World } from './a102-world.js?v=room-view-2';
import { buildA103World } from './a103-world.js?v=room-view-2';

// All doors face the shared landing; each interior keeps its own layout.
export function buildRoomTourWorld(THREE, scene, config) {
  const allowed = new Set(config.rooms);
  const rooms = [];
  const obstacles = [];
  const cameraObstacles = [];
  const descriptions = [
    { number: 'A101', offsetX: 0, minX: -1.6, maxX: 1.6, headClearance: 2.06, build: () => buildA101World(THREE, scene, { includeLanding: false }) },
    { number: 'A102', offsetX: -3.6, minX: -5.3, maxX: -1.9, headClearance: 2.16, build: () => buildA102World(THREE, scene, { offsetX: -3.6 }) },
    { number: 'A103', offsetX: -7.2, minX: -8.9, maxX: -5.5, headClearance: 2.16, build: () => buildA103World(THREE, scene, { offsetX: -7.2 }) },
  ];
  const cream = new THREE.MeshStandardMaterial({ color: '#e7dfcf', roughness: .85 });
  const trim = new THREE.MeshStandardMaterial({ color: '#c9b28d', roughness: .8 });
  const dark = new THREE.MeshStandardMaterial({ color: '#596457', roughness: .8 });
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  function box(x, y, z, w, h, d, material, block = false) {
    const mesh = new THREE.Mesh(boxGeometry, material);
    mesh.position.set(x, y, z); mesh.scale.set(w, h, d);
    mesh.castShadow = mesh.receiveShadow = true; scene.add(mesh);
    if (block) {
      obstacles.push({ minX: x - w / 2, maxX: x + w / 2, minZ: z - d / 2, maxZ: z + d / 2, minY: y - h / 2, maxY: y + h / 2 });
      cameraObstacles.push(mesh);
    }
    return mesh;
  }
  for (const description of descriptions) {
    if (!allowed.has(description.number)) {
      // Do not construct an inaccessible room's interior or expose its media.
      box((description.minX + description.maxX) / 2, 2.25, 0, description.maxX - description.minX, 4.5, .2, cream, true);
      box(description.offsetX + .55, 1.1, .12, 1.1, 2.2, .03, dark);
      continue;
    }
    const built = description.build();
    rooms.push({ ...description, ...built, hingeX: description.offsetX, doorX: description.offsetX + .55 });
    obstacles.push(...built.obstacles.map(rect => ({ ...rect, roomNumber: description.number })));
    cameraObstacles.push(...built.cameraObstacles);
    for (const [z, y, intensity] of [[-1, 3.35, 13], [-4.5, 1.94, 10], [-4.4, built.loft.ceilingY - .3, 12]]) {
      const light = new THREE.PointLight(0xfff5e4, intensity, 7, 2);
      light.position.set(description.offsetX, y, z); scene.add(light);
    }
  }
  const landingCanvas = document.createElement('canvas');
  landingCanvas.width = landingCanvas.height = 128;
  const ctx = landingCanvas.getContext('2d');
  ctx.fillStyle = '#e1d3ba'; ctx.fillRect(0, 0, 128, 128);
  ctx.strokeStyle = '#c9bfae'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, 128, 128);
  const floorMap = new THREE.CanvasTexture(landingCanvas);
  floorMap.colorSpace = THREE.SRGBColorSpace;
  floorMap.wrapS = floorMap.wrapT = THREE.RepeatWrapping; floorMap.repeat.set(19, 6);
  // From left to right the landing connects A103, A102, then A101.
  box(-3.6, -.09, 1.85, 11.6, .18, 3.7, new THREE.MeshStandardMaterial({ map: floorMap, roughness: .9 }));
  box(-9.15, 2.25, 0, .5, 4.5, .22, cream, true);
  box(-5.4, 2.25, 0, .2, 4.5, .22, cream, true);
  box(-1.75, 2.25, 0, .3, 4.5, .22, cream, true);
  box(1.9, 2.25, 0, .6, 4.5, .22, cream, true);
  box(-3.6, 4.5, .13, 11.6, .17, .65, trim);
  box(-3.6, .12, 3.61, 11.6, .24, .14, cream, true);
  for (const x of [-9.25, 2.05]) box(x, 1.95, .17, .15, 3.9, .5, trim, true);
  // A small planter beside A101 preserves the sunny landing's visual cue.
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(.23, .17, .43, 14), trim);
  pot.position.set(1.45, .215, .6); pot.castShadow = true; scene.add(pot);
  const leafMaterial = new THREE.MeshStandardMaterial({ color: '#63834d', roughness: .9 });
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(.013, .018, .72, 8), dark);
  stem.position.set(1.45, .77, .6); scene.add(stem);
  for (let i = 0; i < 9; i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 6), leafMaterial);
    const angle = i * 2.4;
    leaf.position.set(1.45 + Math.cos(angle) * .19, .5 + i * .065, .6 + Math.sin(angle) * .19);
    leaf.scale.set(.22, .035, .09); leaf.rotation.y = -angle; scene.add(leaf);
    const start = new THREE.Vector3(1.45, leaf.position.y - .035, .6);
    const end = leaf.position.clone();
    const branch = new THREE.Mesh(new THREE.CylinderGeometry(.007, .007, start.distanceTo(end), 6), leafMaterial);
    branch.position.copy(start).add(end).multiplyScalar(.5);
    branch.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.sub(start).normalize());
    scene.add(branch);
  }
  obstacles.push({ minX: 1.18, maxX: 1.72, minZ: .33, maxZ: .87, minY: 0, maxY: 1.15 });
  const entry = rooms.find(room => room.number === config.entryRoom) || rooms[0];
  if (!entry) throw new Error('No accessible walkthrough room');
  const roomAt = (x, z) => rooms.find(room => x >= room.minX && x <= room.maxX && z <= 0 && z >= -6.6);
  return {
    rooms, obstacles, cameraObstacles, spawn: entry.spawn,
    bounds: { minX: -9.1, maxX: 1.9, minZ: -6.4, maxZ: 3.35 },
    roomAt,
    nearestRoom: (x, z) => roomAt(x, z) || rooms.reduce((best, room) => Math.abs(room.doorX - x) < Math.abs(best.doorX - x) ? room : best, entry),
    groundAt: (x, z) => roomAt(x, z)?.number === 'A101' && z < -5.1 ? .15 : 0,
    ceilingAt: (x, z, level = 'ground') => {
      const room = roomAt(x, z);
      if (room && level !== 'ground') return room.loft.ceilingY;
      // A102's bathroom lintel is lower than its mezzanine beams. Include the
      // character's radius so its head cannot clip the edge during a jump.
      if (room?.number === 'A102' && x - room.offsetX < -.65 && z < -4.85 && z > -5.5) return 2;
      return room && z < room.loft.maxZ + .1 ? room.headClearance : (room?.loft.ceilingY ?? 4.1);
    },
  };
}
