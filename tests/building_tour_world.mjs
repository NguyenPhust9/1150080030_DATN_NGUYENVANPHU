import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import { buildRoomTourWorld } from '../static/js/room-tour-world.js';
import { createWalkthroughMotion } from '../static/js/walkthrough-motion.js';

// Geometry/collision checks use the real Three.js meshes. Canvas drawing itself
// is checked by the browser suite; no browser is needed to validate coordinates.
globalThis.document = {
  createElement(tag) {
    assert.equal(tag, 'canvas');
    return { width: 0, height: 0, getContext: () => new Proxy({}, {
      get: (target, key) => target[key] ?? (() => {}),
      set: (target, key, value) => { target[key] = value; return true; },
    }) };
  },
};
const roomDetails = Array.from({ length: 25 }, (_, index) => {
  const floor = Math.floor(index / 5) + 1;
  const number = `A${floor}0${index % 5 + 1}`;
  return { number, floor, status: index ? 'available' : 'occupied', profile: floor === 1 ? number : 'generic' };
});
const config = { rooms: roomDetails.map(room => room.number), roomDetails, entryRoom: 'A101', entryFloor: 1 };
const fixture = (extra = {}) => {
  const scene = new THREE.Scene();
  return { scene, world: buildRoomTourWorld(THREE, scene, { ...config, ...extra }) };
};
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < .00001, `${actual} != ${expected}`);
const overlapsBody = (obstacle, x, z) => {
  const radius = .2;
  return obstacle.minY < 1.4 && obstacle.maxY > .05 && x + radius > obstacle.minX && x - radius < obstacle.maxX
    && z + radius > obstacle.minZ && z - radius < obstacle.maxZ;
};
const cameraDoorHits = (world, room, fromY, toY) => {
  world.group.updateMatrixWorld(true);
  const origin = new THREE.Vector3(room.doorX, fromY, 2.4);
  const offset = new THREE.Vector3(room.doorX, toY, -.3).sub(origin);
  const ray = new THREE.Raycaster(origin, offset.clone().normalize(), 0, offset.length());
  const doorParts = new Set();
  room.door.traverse(item => { if (item.isMesh) doorParts.add(item); });
  return ray.intersectObjects(world.cameraObstacles, false).filter(hit => doorParts.has(hit.object));
};

test('existing A101–A105 keep their coordinates, interiors and loft access', () => {
  const { world } = fixture();
  assert.deepEqual(world.rooms.map(room => room.number), ['A101', 'A102', 'A103', 'A104', 'A105']);
  world.rooms.forEach((room, index) => {
    near(room.offsetX, -3.6 * index);
    near(room.spawn.x, .55 - 3.6 * index);
    assert.deepEqual({ y: room.spawn.y, z: room.spawn.z }, { y: 0, z: 2.4 });
    assert.ok(room.loft && room.stairs && room.door);
    assert.equal(room.profile, room.number);
    assert.ok(world.obstacles.some(item => item.roomNumber === room.number && item.tag === 'stairs'));
    assert.equal(world.roomAt(room.offsetX, -3).number, room.number);
  });
  near(world.ceilingAt(0, -4), 2.06);
  near(world.groundAt(0, -5.3), .15);
  world.dispose();
});

test('only the active floor has interiors; a generic room has a traversable entrance', () => {
  const { world } = fixture({ activeFloor: 3 });
  assert.equal(world.floor, 3);
  assert.deepEqual(world.rooms.map(room => room.number), ['A301', 'A302', 'A303', 'A304', 'A305']);
  assert.ok(!world.group.getObjectByName('a105-room-world'));
  for (const room of world.rooms) {
    assert.equal(room.profile, 'generic');
    assert.equal(room.loft, null);
    assert.equal(room.stairs, null);
    assert.equal(world.ceilingAt(room.doorX, -1), 4.5);
    assert.equal(world.groundAt(room.doorX, -4), 0);
    // The auto-opening door is handled by motion; static walls and furnishings
    // must allow the same clear doorway and initial aisle as the detailed rooms.
    for (let z = 2.4; z > -2; z -= .1) {
      assert.ok(!world.obstacles.some(item => overlapsBody(item, room.doorX, z)), `${room.number} doorway blocked at ${z}`);
    }
    assert.ok(world.obstacles.some(item => overlapsBody(item, room.offsetX - .85, -3.95)), 'bed must block walking');
  }
  world.dispose();
});

test('the follow camera stops at a closed generic door after turning toward the courtyard', () => {
  const { world } = fixture({ activeFloor: 2, entryRoom: 'A203' });
  const room = world.rooms.find(room => room.number === 'A203');
  // Reproduce the standing avatar's follow-camera segment after a 180° turn.
  assert.ok(cameraDoorHits(world, room, 1.07, 1.94).length > 0, 'a closed solid door must shorten the camera segment');
  room.door.rotation.y = Math.PI / 2;
  assert.equal(cameraDoorHits(world, room, 1.07, 1.94).length, 0, 'the open door must not leave an invisible camera blocker');
  world.dispose();
});

test('detailed room doors block the camera at solid panels and rails without blocking transparent glass', () => {
  const { world } = fixture();
  for (const room of world.rooms) {
    // A104 is a glazed door with a middle rail; the others have lower panels.
    const height = room.number === 'A104' ? 1.11 : .4;
    assert.ok(cameraDoorHits(world, room, height, height).length > 0, `${room.number}: closed solid door part blocks the camera`);
    room.door.traverse(item => {
      if (!item.isMesh) return;
      const glass = [].concat(item.material || []).every(material => material.transparent && material.opacity < 1);
      const registrations = world.cameraObstacles.filter(obstacle => obstacle === item).length;
      assert.equal(registrations, glass ? 0 : 1, `${room.number}: each opaque door mesh is registered once; glass stays transparent`);
    });
    room.door.rotation.y = Math.PI / 2;
    assert.equal(cameraDoorHits(world, room, height, height).length, 0, `${room.number}: camera obstacles follow the open door`);
  }
  world.dispose();
});

test('lift is reachable along the hallway on all five floors and its cab is walkable', () => {
  for (let floor = 1; floor <= 5; floor++) {
    const { world } = fixture({ activeFloor: floor });
    assert.ok(world.elevator.spawn.x >= world.bounds.minX && world.elevator.spawn.x <= world.bounds.maxX);
    for (let x = world.rooms[0].spawn.x; x > world.elevator.spawn.x; x -= .1) {
      assert.ok(!world.obstacles.some(item => overlapsBody(item, x, 2.4)), `floor ${floor}: lift approach blocked at ${x}`);
    }
    assert.ok(!world.obstacles.some(item => overlapsBody(item, world.elevator.spawn.x, world.elevator.spawn.z)));
    world.dispose();
  }
});

test('route points to the selected room or back to the lift for a different floor', () => {
  const { world } = fixture({ activeFloor: 3 });
  assert.equal(world.setDestination('A303'), true);
  let route = world.group.getObjectByName('route-to-A303');
  near(route.children.at(-1).position.x, -6.65);
  near(route.children.at(-1).position.z, -.72);
  assert.equal(world.setDestination('A105', { x: -6.65, z: -2 }), true);
  assert.ok(!world.group.getObjectByName('route-to-A303'));
  route = world.group.getObjectByName('route-to-A105');
  near(route.children.at(-1).position.x, world.elevator.x);
  near(route.children.at(-1).position.z, world.elevator.z);
  assert.equal(world.setDestination(null), false);
  assert.ok(!world.group.children.some(item => item.name.startsWith('route-to-')));
  assert.equal(world.setDestination('B999'), false);
  world.dispose();
});

test('floor changes release every geometry, material and texture once', () => {
  const { scene, world } = fixture({ activeFloor: 3 });
  world.setDestination('A303');
  const resources = new Set();
  let instanceBatches = 0;
  world.group.traverse(item => {
    // InstancedMesh owns separate GPU attributes; disposing its shared geometry
    // alone does not release instanceMatrix/instanceColor when leaving a floor.
    if (item.isInstancedMesh) { resources.add(item); instanceBatches++; }
    if (item.geometry) resources.add(item.geometry);
    for (const material of [].concat(item.material || [])) {
      resources.add(material);
      Object.values(material).forEach(value => { if (value?.isTexture) resources.add(value); });
    }
  });
  const counts = new Map();
  resources.forEach(item => { counts.set(item, 0); item.addEventListener('dispose', () => counts.set(item, counts.get(item) + 1)); });
  world.dispose(); world.dispose();
  assert.equal(scene.children.length, 0);
  assert.ok(resources.size > 20);
  assert.ok(instanceBatches > 0, 'landscape instancing participates in resource cleanup');
  counts.forEach(count => assert.equal(count, 1));
});

test('the outdoor ground stays below floors 1, 2 and 5 while room coordinates stay local', () => {
  let centerX;
  for (const floor of [1, 2, 5]) {
    const { world } = fixture({ activeFloor: floor });
    const landscape = world.landscape;
    assert.ok(landscape?.group, `floor ${floor} has an outdoor environment`);
    assert.equal(landscape.group.name, 'tour-landscape');
    assert.equal(landscape.group.parent, world.group, 'the floor owns all outdoor resources');
    near(landscape.groundY, -(floor - 1) * 4.8);
    near(landscape.group.position.y, landscape.groundY);
    if (centerX === undefined) centerX = landscape.centerX;
    near(landscape.centerX, centerX);
    for (const [index, room] of world.rooms.entries()) {
      near(room.offsetX, -3.6 * index);
      near(room.spawn.x, .55 - 3.6 * index);
      near(room.spawn.y, 0);
      near(world.groundAt(room.doorX, -1), 0);
    }
    near(world.elevator.spawn.y, 0);
    world.dispose();
  }
});

test('landscape never enters the walkable corridor or takes over the follow camera', () => {
  for (const floor of [1, 2, 5]) {
    const { world } = fixture({ activeFloor: floor });
    const landscapeObjects = new Set();
    world.landscape.group.traverse(item => {
      landscapeObjects.add(item);
      assert.ok(!item.isLight, 'outdoor decoration must reuse scene lighting');
    });
    const outdoorBounds = new THREE.Box3().setFromObject(world.landscape.group);
    assert.ok(!outdoorBounds.isEmpty());
    assert.ok(outdoorBounds.min.z > world.corridorBounds.maxZ, 'trees and buildings stay outside the enclosed corridor');
    assert.ok(!world.cameraObstacles.some(item => landscapeObjects.has(item)), 'distant scenery cannot force the camera into the avatar');
    const position = { ...world.rooms[0].spawn };
    const motion = createWalkthroughMotion(world, position);
    for (let tick = 0; tick < 1600 && position.x > world.elevator.spawn.x + .1; tick++) {
      motion.step(1 / 60, { strafe: -1 });
    }
    assert.ok(Math.abs(position.x - world.elevator.spawn.x) < .12, `floor ${floor}: walking to the lift is unchanged`);
    near(position.z, 2.4);
    near(position.y, 0);
    world.dispose();
  }
});

test('single-room tenant tours keep the true outdoor elevation without exposing other rooms', () => {
  const details = [roomDetails.find(room => room.number === 'A501')];
  const { world } = fixture({
    rooms: ['A501'], roomDetails: details,
    entryRoom: 'A501', entryFloor: 5, activeFloor: 5,
  });
  near(world.landscape.groundY, -19.2);
  assert.deepEqual(world.rooms.map(room => room.number), ['A501']);
  assert.equal(world.setDestination('A101'), false);
  assert.equal(world.setDestination('A502'), false);
  near(world.rooms[0].spawn.y, 0);
  world.dispose();
});

test('the courtyard remains beneath a tenant room with a preserved sparse slot', () => {
  const details = [roomDetails.find(room => room.number === 'A105')];
  const { world } = fixture({ rooms: ['A105'], roomDetails: details, entryRoom: 'A105' });
  near(world.rooms[0].offsetX, -14.4);
  near(world.landscape.centerX, world.rooms[0].offsetX);
  assert.deepEqual(world.rooms.map(room => room.number), ['A105']);
  world.dispose();
});

test('an explicitly configured ground floor zero remains at ground level', () => {
  const details = [{ number: 'Ground', floor: 0, profile: 'generic' }];
  const { world } = fixture({
    rooms: ['Ground'], roomDetails: details,
    entryRoom: 'Ground', entryFloor: 0, activeFloor: 0,
  });
  near(world.landscape.groundY, 0);
  near(world.landscape.group.position.y, 0);
  near(world.rooms[0].spawn.y, 0);
  world.dispose();
});

test('room allow-list is respected even when metadata contains more rooms', () => {
  const { world } = fixture({ rooms: ['A303'], activeFloor: 3 });
  assert.deepEqual(world.rooms.map(room => room.number), ['A303']);
  assert.equal(world.setDestination('A302'), false);
  assert.equal(world.setDestination('A303'), true);
  world.dispose();
});

test('generic rooms support real walking, jumping and furniture collision without stairs', () => {
  const { world } = fixture({ activeFloor: 3, entryRoom: 'A303' });
  const room = world.rooms.find(room => room.number === 'A303');
  room.door.rotation.y = Math.PI / 2;
  const position = { ...room.spawn };
  const motion = createWalkthroughMotion(world, position);
  for (let i = 0; i < 140; i++) motion.step(1 / 60, { forward: 1 });
  assert.ok(position.z < 0 && position.z > -2, 'walk through the open generic room entrance');
  assert.equal(motion.state.level, 'ground');
  motion.requestJump();
  let peak = 0;
  for (let i = 0; i < 100; i++) { motion.step(1 / 60); peak = Math.max(peak, position.y); }
  assert.ok(peak > .15);
  near(position.y, 0);
  assert.equal(motion.state.airborne, false);
  // The rear wet area blocks the aisle; it must never be treated as a loft/ramp.
  for (let i = 0; i < 300; i++) motion.step(1 / 60, { forward: 1 });
  assert.ok(position.z > -4.86 && position.z < -3.5, 'stop before the solid bathroom enclosure');
  near(position.y, 0);
  assert.equal(motion.state.level, 'ground');
  world.dispose();
});

test('additional room codes cannot overlap preserved A101–A105 slots', () => {
  const mixed = [{ number: 'A103', floor: 1, profile: 'A103' }, { number: 'A105', floor: 1, profile: 'A105' }, { number: 'A106', floor: 1, profile: 'generic' }];
  const { world } = fixture({ rooms: mixed.map(room => room.number), roomDetails: mixed, entryRoom: 'A103' });
  assert.deepEqual(world.rooms.map(room => room.offsetX), [-7.2, -14.4, -18]);
  for (let i = 1; i < world.rooms.length; i++) assert.ok(world.rooms[i].maxX < world.rooms[i - 1].minX);
  world.dispose();
});

test('the front wall, windows, corridor ends and ceiling enclose every active floor', () => {
  for (const floor of [1, 2, 5]) {
    const { world } = fixture({ activeFloor: floor });
    world.group.updateMatrixWorld(true);
    const x = world.rooms[0].spawn.x;
    // The same collision applies at standing and jumping height, including glazing.
    for (const y of [0, .7]) {
      const position = { x, y, z: 2.4 };
      const motion = createWalkthroughMotion(world, position);
      if (y) motion.requestJump();
      for (let i = 0; i < 150; i++) motion.step(1 / 60, { forward: -1 });
      assert.ok(position.z < 3.5, `floor ${floor}: the front enclosure cannot be crossed`);
    }
    for (const direction of [new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0), new THREE.Vector3(-1, 0, 0), new THREE.Vector3(0, 1, 0)]) {
      const ray = new THREE.Raycaster(new THREE.Vector3(x, 1.4, 2.4), direction, 0, 40);
      assert.ok(ray.intersectObjects(world.enclosure.cameraObstacles).length, `floor ${floor}: the camera must stay inside the envelope`);
    }
    near(world.ceilingAt(x, 2.4), 4.36);
    if (floor > 1) assert.equal(world.entrance, null);
    world.dispose();
  }
});

test('walk from the street through the main entrance to every original room and back', () => {
  const { world } = fixture();
  const position = { x: world.landscape.centerX, y: world.groundAt(world.landscape.centerX, 33), z: 33 };
  const motion = createWalkthroughMotion(world, position);
  const step = input => motion.step(1 / 60, input);
  const reach = (axis, target) => {
    for (let i = 0; i < 2400 && Math.abs(position[axis] - target) > .03; i++) {
      const sign = Math.sign(target - position[axis]);
      step(axis === 'x' ? { strafe: sign } : { forward: -sign });
    }
    assert.ok(Math.abs(position[axis] - target) <= .03, `${axis}: could not reach ${target}, stopped at ${position[axis]}`);
  };
  reach('z', 6.1); reach('x', world.entrance.x); reach('z', 2.4);
  near(position.y, 0);
  for (const room of world.rooms) {
    room.door.rotation.y = Math.PI / 2;
    reach('x', room.doorX); reach('z', -1.5);
    assert.equal(world.roomAt(position.x, position.z), room);
    reach('z', 2.4);
  }
  reach('x', world.entrance.x); reach('z', 6.1); reach('x', world.landscape.centerX); reach('z', 33);
  assert.ok(position.y > 0 && position.y < .1);
  for (let i = 0; i < 200; i++) step({ strafe: 1 });
  assert.ok(position.x <= world.enclosure.path.maxX - .2, 'cannot walk off the paved route into scenery');
  world.dispose();
});

test('outside destination routes pass through the entrance and remain above the pavement', () => {
  const { world } = fixture();
  for (const number of ['A105', 'A303']) {
    assert.equal(world.setDestination(number, { x: world.landscape.centerX, z: 32 }), true);
    const route = world.group.getObjectByName(`route-to-${number}`);
    assert.ok(route.children.some(mesh => mesh.position.z > 25 && mesh.position.y > .1));
    assert.ok(route.children.some(mesh => Math.abs(mesh.position.x - world.entrance.x) < .01 && mesh.position.z > 3.7 && mesh.position.z < 6.1));
    const marker = route.children.at(-1);
    near(marker.position.x, number === 'A105' ? world.rooms[4].doorX : world.elevator.x);
  }
  world.dispose();
});

test('a sparse tenant tour has a connected entrance without exposing other rooms', () => {
  const details = [roomDetails.find(room => room.number === 'A105')];
  const { world } = fixture({ rooms: ['A105'], roomDetails: details, entryRoom: 'A105' });
  const position = { x: world.entrance.x, y: 0, z: 2.4 };
  const motion = createWalkthroughMotion(world, position);
  for (let i = 0; i < 250; i++) motion.step(1 / 60, { forward: -1 });
  assert.ok(position.z > 8, 'the single-room entrance is traversable');
  assert.equal(world.setDestination('A104', position), false);
  assert.deepEqual(world.rooms.map(room => room.number), ['A105']);
  world.dispose();
});

test('the porch cannot be used to walk or jump through glass beside the entrance', () => {
  const { world } = fixture();
  for (const side of [-1, 1]) {
    for (const outside of [false, true]) {
      const position = { x: world.entrance.x + side * 1.8, y: 0, z: outside ? 5 : 2.4 };
      const motion = createWalkthroughMotion(world, position);
      for (let tick = 0; tick < 160; tick++) {
        if (tick % 45 === 0) motion.requestJump();
        motion.step(1 / 60, { forward: outside ? 1 : -1 });
      }
      assert.ok(outside ? position.z > 3.9 : position.z < 3.5, 'glazing is solid from both sides, including during a jump');
    }
  }
  world.dispose();
});
