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
  world.group.traverse(item => {
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
  counts.forEach(count => assert.equal(count, 1));
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
