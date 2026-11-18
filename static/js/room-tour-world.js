import { buildA101World } from './a101-world.js?v=a105-tour-1';
import { buildA102World } from './a102-world.js?v=a105-tour-1';
import { buildA103World } from './a103-world.js?v=a105-tour-1';
import { buildA104World } from './a104-world.js?v=a105-tour-1';
import { buildA105World } from './a105-world.js?v=a105-tour-1';
import { buildGenericRoomWorld } from './generic-room-world.js?v=building-tour-1';
import { buildTourLandscape } from './tour-landscape.js?v=landscape-1';
import { buildTourBuildingEnvelope } from './tour-building-envelope.js?v=enclosed-entry-1';

// All doors face the shared landing; each interior keeps its own layout.
export function buildRoomTourWorld(THREE, scene, config) {
  const owned = new THREE.Group(); owned.name = 'room-tour-floor'; scene.add(owned);
  const target = scene; scene = owned;
  const allowed = new Set(config.rooms);
  const floorOf = number => Number(String(number).match(/(\d+)\d{2}$/)?.[1]) || 1;
  const details = config.roomDetails?.length ? config.roomDetails : config.rooms.map(number => ({
    number, floor: floorOf(number), profile: /^A10[1-5]$/.test(number) ? number : 'generic',
  }));
  const floor = Number(config.activeFloor ?? config.entryFloor ?? floorOf(config.entryRoom));
  const rooms = [];
  const obstacles = [];
  const cameraObstacles = [];
  const builders = { A101: buildA101World, A102: buildA102World, A103: buildA103World, A104: buildA104World, A105: buildA105World };
  const floorRooms = details.filter(room => allowed.has(room.number) && Number(room.floor) === floor)
    .sort((a, b) => a.number.localeCompare(b.number, undefined, { numeric: true }));
  const preservedSlots = floorRooms.filter(room => /^A10[1-5]$/.test(room.number)).map(room => Number(room.number.at(-1)) - 1);
  let nextGenericSlot = preservedSlots.length ? Math.max(...preservedSlots) + 1 : 0;
  const descriptions = floorRooms.map(room => {
      // Preserve the established coordinates and collision geometry of A101–A105.
      const slot = /^A10[1-5]$/.test(room.number) ? Number(room.number.at(-1)) - 1 : nextGenericSlot++;
      const offsetX = -3.6 * slot;
      const profile = room.profile || (/^A10[1-5]$/.test(room.number) ? room.number : 'generic');
      const builder = profile === room.number ? builders[profile] : null;
      return { ...room, floor, profile: builder ? profile : 'generic', offsetX,
        minX: offsetX - (room.number === 'A101' ? 1.6 : 1.7),
        maxX: offsetX + (room.number === 'A101' ? 1.6 : 1.7),
        headClearance: room.number === 'A101' ? 2.06 : room.number === 'A104' || room.number === 'A105' ? 2.2 : 2.16,
        build: () => builder ? builder(THREE, scene, { offsetX, includeLanding: false })
          : buildGenericRoomWorld(THREE, scene, { offsetX, number: room.number }) };
    });
  if (!descriptions.length) { target.remove(owned); throw new Error('No accessible walkthrough room on this floor'); }
  const layout = [...descriptions].sort((a, b) => a.minX - b.minX);
  const roomMinX = layout[0].minX - .5;
  const cabWidth = 2.7, elevatorX = roomMinX - cabWidth / 2 - .08;
  const landingMinX = elevatorX - cabWidth / 2 - .12;
  const landingMaxX = layout.at(-1).maxX + .6;
  const landingWidth = landingMaxX - landingMinX;
  const landingCenterX = (landingMinX + landingMaxX) / 2;
  const cream = new THREE.MeshStandardMaterial({ color: '#e7dfcf', roughness: .85 });
  const trim = new THREE.MeshStandardMaterial({ color: '#c9b28d', roughness: .8 });
  const dark = new THREE.MeshStandardMaterial({ color: '#596457', roughness: .8 });
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  function box(x, y, z, w, h, d, material, block = false, cameraBlock = block) {
    const mesh = new THREE.Mesh(boxGeometry, material);
    mesh.position.set(x, y, z); mesh.scale.set(w, h, d);
    mesh.castShadow = mesh.receiveShadow = true; scene.add(mesh);
    if (block) {
      obstacles.push({ minX: x - w / 2, maxX: x + w / 2, minZ: z - d / 2, maxZ: z + d / 2, minY: y - h / 2, maxY: y + h / 2 });
    }
    if (cameraBlock) cameraObstacles.push(mesh);
    return mesh;
  }
  for (const description of descriptions) {
    const built = description.build();
    rooms.push({ ...description, ...built, hingeX: description.offsetX, doorX: description.offsetX + .55 });
    obstacles.push(...built.obstacles.map(rect => ({ ...rect, roomNumber: description.number })));
    cameraObstacles.push(...built.cameraObstacles);
    // Doors rotate independently of the static room walls. Include their opaque
    // panels in the follow-camera raycast so orbiting cannot enter a closed door.
    built.door?.traverse(item => {
      if (!item.isMesh || cameraObstacles.includes(item)) return;
      const materials = [].concat(item.material || []);
      if (materials.some(material => !material.transparent || material.opacity >= 1)) cameraObstacles.push(item);
    });
    const lightSpecs = built.loft ? [[-1, 3.35, 13], [-4.5, 1.94, 10], [-4.4, built.loft.ceilingY - .3, 12]] : [[-2.6, 3.6, 20], [-5.2, 2.5, 9]];
    for (const [z, y, intensity] of lightSpecs) {
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
  floorMap.wrapS = floorMap.wrapT = THREE.RepeatWrapping; floorMap.repeat.set(landingWidth / .6, 6);
  // Extend the landing and its facade with the physical room order.
  box(landingCenterX, -.09, 1.85, landingWidth, .18, 3.7, new THREE.MeshStandardMaterial({ map: floorMap, roughness: .9 }));
  box(roomMinX + .25, 2.25, 0, .5, 4.5, .22, cream, true);
  for (let i = 1; i < layout.length; i++) {
    const left = layout[i - 1].maxX, right = layout[i].minX;
    box((left + right) / 2, 2.25, 0, right - left, 4.5, .22, cream, true);
  }
  box(landingMaxX - .3, 2.25, 0, .6, 4.5, .22, cream, true);
  box(landingCenterX, 4.5, .13, landingWidth, .17, .65, trim);
  for (const x of [roomMinX + .15, landingMaxX - .15]) box(x, 1.95, .17, .15, 3.9, .5, trim, true);
  const metal = new THREE.MeshStandardMaterial({ color: '#6d7b76', metalness: .5, roughness: .4 });
  const chrome = new THREE.MeshStandardMaterial({ color: '#b6c1bd', metalness: .75, roughness: .25 });
  function label(text, subtitle, x, y, z, w, h) {
    const canvas = document.createElement('canvas'); canvas.width = 768; canvas.height = 384;
    const context = canvas.getContext('2d');
    context.fillStyle = '#394d48'; context.fillRect(0, 0, 768, 384);
    context.textAlign = 'center'; context.fillStyle = '#fffbed'; context.font = '600 98px Segoe UI, sans-serif'; context.fillText(text, 384, 176);
    context.fillStyle = '#d9e1d9'; context.font = '48px Segoe UI, sans-serif'; context.fillText(subtitle, 384, 284);
    const map = new THREE.CanvasTexture(canvas); map.colorSpace = THREE.SRGBColorSpace;
    const item = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map, roughness: .8 }));
    item.position.set(x, y, z); scene.add(item); return item;
  }
  // The lift opens sideways into the shared landing. Its walkable cab uses the
  // same ground coordinates as the rooms, including after changing floors.
  box(elevatorX, .015, 1.85, cabWidth - .12, .03, 3.36, new THREE.MeshStandardMaterial({ color: '#aeb9b3', roughness: .7 }));
  box(elevatorX - cabWidth / 2, 1.65, 1.85, .14, 3.3, 3.5, metal, true);
  box(elevatorX, 1.65, .17, cabWidth, 3.3, .14, metal, true);
  // A glazed outer wall lets the follow camera see the visitor inside the cab,
  // while its physical collision still prevents walking through the shaft.
  const liftGlass = new THREE.MeshStandardMaterial({ color: '#c0dad6', transparent: true, opacity: .18,
    depthWrite: false, roughness: .25, metalness: .1, side: THREE.DoubleSide });
  box(elevatorX, 1.65, 3.53, cabWidth, 3.3, .07, liftGlass, true, false);
  cameraObstacles.push(box(elevatorX, 3.34, 1.85, cabWidth + .14, .12, 3.5, metal));
  box(elevatorX, 3.25, 1.85, 1.2, .03, .3, new THREE.MeshStandardMaterial({ color: '#fff7dc', emissive: '#fff1cc', emissiveIntensity: .7 }));
  box(elevatorX - cabWidth / 2 + .085, 1.72, 1.85, .025, 1.7, 2.25, new THREE.MeshStandardMaterial({ color: '#b7ccc9', metalness: .65, roughness: .19 }));
  for (const z of [.29, 3.41]) box(elevatorX, 1.05, z, cabWidth - .25, .045, .045, chrome);
  const openX = elevatorX + cabWidth / 2;
  for (const z of [.28, 3.42]) box(openX, 1.6, z, .14, 3.2, .13, trim, true);
  box(openX, 3.17, 1.85, .17, .26, 3.25, trim);
  label('THANG MÁY', `Tầng ${floor}`, elevatorX, 3.8, .26, 2.35, .8);
  label(String(floor).padStart(2, '0'), 'CHỌN TẦNG', elevatorX, 1.78, .26, .55, .55);
  const cabLight = new THREE.PointLight(0xfff6df, 8, 5, 2); cabLight.position.set(elevatorX, 2.9, 1.85); scene.add(cabLight);
  const elevator = { x: elevatorX, z: 2.4, minX: elevatorX - 1.05, maxX: openX - .06,
    minZ: .55, maxZ: 3.12, spawn: { x: elevatorX, y: 0, z: 2.4 } };
  // Only cheap exterior slabs and doors represent the other levels; interiors
  // are constructed when the lift arrives there, then disposed on departure.
  const allFloors = [...new Set(details.filter(room => allowed.has(room.number)).map(room => Number(room.floor)))].sort((a, b) => a - b);
  const windowMaterial = new THREE.MeshStandardMaterial({ color: '#bbcdc5', roughness: .5 });
  for (const otherFloor of allFloors) {
    if (otherFloor === floor) continue;
    const y = (otherFloor - floor) * 4.8;
    box(landingCenterX, y - .09, 1.85, landingWidth, .18, 3.7, cream);
    box(landingCenterX, y + 2.2, -.12, landingWidth, 4.4, .12, cream);
    const floorRooms = details.filter(room => allowed.has(room.number) && Number(room.floor) === otherFloor)
      .sort((a, b) => a.number.localeCompare(b.number, undefined, { numeric: true }));
    floorRooms.forEach((room, index) => {
      const x = -3.6 * index;
      box(x + .55, y + 1.1, -.035, 1.05, 2.2, .04, dark);
      box(x - .8, y + 1.5, -.03, .88, 1.35, .05, windowMaterial);
    });
    box(landingCenterX, y + 1.05, 3.57, landingWidth, .055, .055, metal);
    for (const x of [landingMinX + .15, landingMaxX - .15]) box(x, y + 2.3, .13, .16, 4.6, .45, trim);
  }
  // Use a stable envelope across authorized floors, preserving sparse A101–A105
  // slots too. A tenant who sees only A105 still has the courtyard below A105.
  const landscapeOffsets = [];
  for (const otherFloor of allFloors) {
    const candidates = details.filter(room => allowed.has(room.number) && Number(room.floor) === otherFloor)
      .sort((a, b) => a.number.localeCompare(b.number, undefined, { numeric: true }));
    const known = candidates.filter(room => /^A10[1-5]$/.test(room.number)).map(room => Number(room.number.at(-1)) - 1);
    let next = known.length ? Math.max(...known) + 1 : 0;
    for (const room of candidates) landscapeOffsets.push(-3.6 * (/^A10[1-5]$/.test(room.number) ? Number(room.number.at(-1)) - 1 : next++));
  }
  const landscape = buildTourLandscape(THREE, owned, {
    activeFloor: floor, lowestFloor: Math.min(1, ...allFloors),
    centerX: (Math.min(...landscapeOffsets) + Math.max(...landscapeOffsets)) / 2,
  });
  const enclosure = buildTourBuildingEnvelope(THREE, owned, {
    minX: landingMinX, maxX: landingMaxX, liftEdgeX: openX, floor, floors: allFloors,
    groundFloor: landscape.lowestFloor, pathX: landscape.centerX,
  });
  obstacles.push(...enclosure.obstacles);
  cameraObstacles.push(...enclosure.cameraObstacles);
  const entrance = enclosure.entrance;
  if (entrance) {
    label('LỐI VÀO', 'SẢNH TÒA NHÀ', entrance.x, 3.72, 3.86, 2.3, .72);
    const exitSign = label('LỐI RA', 'SÂN · CỔNG CHÍNH', entrance.x, 3.72, 3.54, 2.3, .72);
    exitSign.rotation.y = Math.PI;
  }
  const corridorBounds = { minX: landingMinX + .3, maxX: landingMaxX - .3, minZ: -6.4, maxZ: 3.35 };
  // A small planter beside A101 preserves the sunny landing's visual cue.
  if (rooms.some(room => room.number === 'A101')) {
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
  }
  let route = null, disposed = false;
  function disposeObjects(group) {
    const geometries = new Set(), materials = new Set(), textures = new Set(), instancedMeshes = new Set();
    group.traverse(object => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.isInstancedMesh) instancedMeshes.add(object);
      for (const mat of [].concat(object.material || [])) {
        materials.add(mat);
        for (const value of Object.values(mat)) if (value?.isTexture) textures.add(value);
      }
    });
    instancedMeshes.forEach(mesh => mesh.dispose());
    textures.forEach(texture => texture.dispose()); materials.forEach(mat => mat.dispose());
    geometries.forEach(geometry => geometry.dispose());
  }
  function setDestination(number, origin = null) {
    if (route) { owned.remove(route); disposeObjects(route); route = null; }
    const destination = rooms.find(room => room.number === number);
    if (!number || disposed || !details.some(room => allowed.has(room.number) && room.number === number)) return false;
    route = new THREE.Group(); route.name = `route-to-${number}`; owned.add(route);
    const blue = new THREE.MeshBasicMaterial({ color: '#1478e7', depthWrite: false });
    const white = new THREE.MeshBasicMaterial({ color: '#effbff', depthWrite: false });
    // Separate geometry avoids disposing the room boxes when replacing a route.
    const routeBox = new THREE.BoxGeometry(1, 1, 1);
    function strip(x, z, width, depth, material, y) {
      const item = new THREE.Mesh(routeBox, material); item.position.set(x, y, z);
      item.scale.set(width, .008, depth); route.add(item);
    }
    function arrow(x, atZ, heading) {
      const shape = new THREE.Shape(); shape.moveTo(-.17, -.19); shape.lineTo(.17, 0); shape.lineTo(-.17, .19); shape.closePath();
      const item = new THREE.Mesh(new THREE.ShapeGeometry(shape), blue);
      item.rotation.x = -Math.PI / 2; item.rotation.z = heading; item.position.set(x, atZ > 3.7 ? .155 : .055, atZ); route.add(item);
    }
    let points;
    if (destination) {
      points = [{ x: elevator.x, z: 2.4 }, { x: destination.doorX, z: 2.4 }, { x: destination.doorX, z: -.72 }];
    } else {
      // A room on another floor first directs the visitor back to the lift.
      const nearest = rooms.reduce((best, room) => Math.abs(room.doorX - (origin?.x ?? 0)) < Math.abs(best.doorX - (origin?.x ?? 0)) ? room : best, rooms[0]);
      const startX = origin?.z < 0 ? nearest.doorX : Math.max(openX, Math.min(landingMaxX - .4, origin?.x ?? nearest.doorX));
      points = origin?.z < 0 ? [{ x: startX, z: -.72 }, { x: startX, z: 2.4 }] : [{ x: startX, z: 2.4 }];
      points.push({ x: elevator.x, z: 2.4 });
    }
    if (entrance && origin?.z > 3.8) {
      // Outside routes pass through the actual opening, then follow the hallway.
      const hallwayX = destination?.doorX ?? elevator.x;
      points = [{ x: origin.x, z: origin.z }];
      // Turn on the broad apron, clear of both doorway jambs even when starting
      // immediately outside a window or beside the entrance.
      points.push({ x: origin.x, z: 6.1 }, { x: entrance.x, z: 6.1 },
        { x: entrance.x, z: 2.4 }, { x: hallwayX, z: 2.4 });
      if (destination) points.push({ x: destination.doorX, z: -.72 });
    }
    for (let i = 1; i < points.length; i++) {
      const from = points[i - 1], to = points[i], dx = to.x - from.x, dz = to.z - from.z;
      const distance = Math.hypot(dx, dz);
      if (distance < .01) continue;
      const centerX = (from.x + to.x) / 2, centerZ = (from.z + to.z) / 2;
      // Keep route markings above the raised courtyard paving.
      const height = centerZ > 3.7 ? .1 : 0;
      strip(centerX, centerZ, Math.abs(dx) || .21, Math.abs(dz) || .21, white, height + .034);
      strip(centerX, centerZ, Math.abs(dx) || .13, Math.abs(dz) || .13, blue, height + .041);
      for (let step = Math.min(.8, distance / 2); step < distance - .2; step += 2.1) {
        arrow(from.x + dx * step / distance, from.z + dz * step / distance, Math.atan2(-dz, dx));
      }
    }
    const end = points.at(-1);
    const marker = new THREE.Mesh(new THREE.RingGeometry(.15, .24, 24), white);
    marker.rotation.x = -Math.PI / 2; marker.position.set(end.x, .056, end.z); route.add(marker);
    return true;
  }
  const entry = rooms.find(room => room.number === config.entryRoom) || rooms[0];
  if (!entry) throw new Error('No accessible walkthrough room');
  const roomAt = (x, z) => rooms.find(room => x >= room.minX && x <= room.maxX && z <= 0 && z >= -6.6);
  return {
    group: owned, floor, rooms, obstacles, cameraObstacles, elevator, landscape, enclosure, entrance, corridorBounds, spawn: entry.spawn, setDestination,
    bounds: entrance ? { ...corridorBounds, minX: Math.min(corridorBounds.minX, enclosure.porch.minX + .2),
      maxX: Math.max(corridorBounds.maxX, enclosure.porch.maxX - .2), maxZ: enclosure.path.maxZ - .2 } : corridorBounds,
    isWalkable: (x, z, radius) => enclosure.contains(x, z, radius),
    roomAt,
    nearestRoom: (x, z) => roomAt(x, z) || rooms.reduce((best, room) => Math.abs(room.doorX - x) < Math.abs(best.doorX - x) ? room : best, entry),
    groundAt: (x, z) => roomAt(x, z)?.number === 'A101' && z < -5.1 ? .15 : enclosure.groundAt(z),
    ceilingAt: (x, z, level = 'ground') => {
      const room = roomAt(x, z);
      if (x >= elevator.minX && x <= elevator.maxX && z >= elevator.minZ && z <= elevator.maxZ) return 3.25;
      if (!room) return enclosure.ceilingAt(x, z);
      if (room && !room.loft) return room.ceiling.roomHeight;
      if (room && level !== 'ground') return room.loft.ceilingY;
      // A102's bathroom lintel is lower than its mezzanine beams. Include the
      // character's radius so its head cannot clip the edge during a jump.
      if (room?.number === 'A102' && x - room.offsetX < -.65 && z < -4.85 && z > -5.5) return 2;
      return room && z < room.loft.maxZ + .1 ? room.headClearance : (room?.loft.ceilingY ?? 4.1);
    },
    dispose() {
      if (disposed) return;
      disposed = true; target.remove(owned); disposeObjects(owned); owned.clear(); route = null;
    },
  };
}
