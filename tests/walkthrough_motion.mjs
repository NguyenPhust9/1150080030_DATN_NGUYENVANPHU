import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createWalkthroughMotion } from '../static/js/walkthrough-motion.js';

// Pure movement fixtures use the real rooms' deck heights and stair direction.
// Rendering and world metadata are covered separately by browser checks.
const variants = [
  { number: 'A101', deckY: 2.305, roofY: 4.2, groundCeiling: 2.06, stairBottomZ: -1.27 },
  { number: 'A102', deckY: 2.376, roofY: 4.5, groundCeiling: 2.16, stairBottomZ: -1.17 },
  { number: 'A103', deckY: 2.36, roofY: 4.4, groundCeiling: 2.16, stairBottomZ: -.85 },
];
const DT = 1 / 60;
const close = (actual, expected, tolerance = .00001) => {
  assert.ok(Math.abs(actual - expected) <= tolerance, `Expected ${actual} near ${expected}`);
};

function fixture(variant, initial = {}) {
  const stairs = { minX: -1.6, maxX: -.9, bottomZ: variant.stairBottomZ, topZ: -2.8, bottomY: 0, topY: variant.deckY };
  const room = {
    number: variant.number, minX: -1.6, maxX: 1.6,
    stairs, loft: { y: variant.deckY, minZ: -6.6, maxZ: -2.8 },
    hingeX: 0, door: { rotation: { y: Math.PI / 2 } },
  };
  const stairX = (stairs.minX + stairs.maxX) / 2;
  const spawn = { x: stairX, y: 0, z: stairs.bottomZ + .45 };
  const position = { ...spawn, ...initial };
  const world = {
    rooms: [room], spawn,
    bounds: { minX: -1.6, maxX: 1.6, minZ: -6.4, maxZ: 3.35 },
    roomAt: (x, z) => x >= room.minX && x <= room.maxX && z <= 0 && z >= -6.6 ? room : undefined,
    groundAt: () => 0,
    ceilingAt: (x, z, level = 'ground') => level === 'ground' && z < -2.7 ? variant.groundCeiling : variant.roofY,
    obstacles: [
      // The rendered stair obstacle includes a 10 cm buffer before its first
      // tread; stair attachment must happen before the body hits that buffer.
      { ...stairs, minZ: stairs.topZ, maxZ: stairs.bottomZ + .1, minY: 0, maxY: variant.deckY, tag: 'stairs', roomNumber: variant.number },
      // A downstairs cabinet, an upstairs mattress, and the mezzanine rail.
      { minX: .6, maxX: 1.1, minZ: -4.4, maxZ: -3.8, minY: 0, maxY: 1.95, tag: 'cabinet' },
      { minX: -.4, maxX: .4, minZ: -5, maxZ: -4.5, minY: variant.deckY + .03, maxY: variant.deckY + .25, tag: 'loft-furniture', name: 'mattress' },
      { minX: -.9, maxX: 1.6, minZ: -2.84, maxZ: -2.76, minY: variant.deckY, maxY: variant.deckY + .9, tag: 'rail' },
    ],
  };
  return { world, room, position, motion: createWalkthroughMotion(world, position), stairX };
}

function until(item, predicate, input, { dt = DT, frames = 1800 } = {}) {
  for (let i = 0; i < frames; i++) {
    if (predicate()) return;
    item.motion.step(dt, input);
  }
  assert.ok(predicate(), `Movement did not reach its target: ${JSON.stringify({ ...item.position, ...item.motion.state })}`);
}

function run(item, input, seconds = 1) {
  for (let i = 0; i < Math.ceil(seconds / DT); i++) item.motion.step(DT, input);
}

function ascend(item, dt = DT) {
  until(item, () => item.motion.state.level === 'loft', { forward: 1 }, { dt });
  close(item.position.y, item.room.loft.y);
  assert.ok(item.position.z <= item.room.stairs.topZ - .35);
}

for (const variant of variants) {
  test(`${variant.number}: continuous stair ascent and descent at 60 and 20 fps`, () => {
    for (const dt of [DT, .05]) {
      const item = fixture(variant);
      let previousHeight = item.position.y;
      until(item, () => item.motion.state.level === 'stairs', { forward: 1 }, { dt });
      for (let i = 0; item.motion.state.level !== 'loft' && i < 1000; i++) {
        item.motion.step(dt, { forward: 1 });
        assert.ok(item.position.y >= previousHeight - .00001);
        assert.ok(item.position.y - previousHeight < .12, 'Climbing must not warp onto the deck');
        previousHeight = item.position.y;
      }
      assert.equal(item.motion.state.level, 'loft');
      close(item.position.y, variant.deckY);
      until(item, () => item.motion.state.level === 'ground', { forward: -1 }, { dt });
      close(item.position.y, 0);
      assert.ok(item.position.z >= item.room.stairs.bottomZ + .25);
    }
  });

  test(`${variant.number}: walking or jumping under the loft stays downstairs`, () => {
    const item = fixture(variant, { x: .2, z: -1.5 });
    until(item, () => item.position.z < -3.5, { forward: 1 });
    assert.equal(item.motion.state.level, 'ground');
    close(item.position.y, 0);
    item.motion.requestJump();
    item.motion.step(DT);
    let peak = item.position.y;
    let jumpFrames = 0;
    while (item.motion.state.airborne && jumpFrames++ < 120) {
      item.motion.step(DT);
      peak = Math.max(peak, item.position.y);
      assert.ok(item.position.y + 1.4 <= variant.groundCeiling + .00001);
    }
    assert.ok(jumpFrames < 120);
    assert.equal(item.motion.state.level, 'ground');
    close(item.position.y, 0);
    // Ground walkers can pass beneath the mattress's X/Z footprint.
    until(item, () => item.position.z < -5.2, { forward: 1 });
    close(item.position.y, 0);
    assert.ok(peak > 0 && peak < variant.deckY);
  });

  test(`${variant.number}: a sideways approach halfway up cannot enter or teleport onto stairs`, () => {
    const item = fixture(variant, { x: -.5, z: -2 });
    run(item, { strafe: -1 }, 2);
    assert.equal(item.motion.state.level, 'ground');
    close(item.position.y, 0);
    assert.ok(item.position.x >= item.room.stairs.maxX + .19);
    run(item, { forward: 1 }, .2);
    assert.equal(item.motion.state.level, 'ground');
    close(item.position.y, 0);
  });

  test(`${variant.number}: loft jump lands on its original floor and respects roof clearance`, () => {
    const item = fixture(variant);
    ascend(item);
    item.motion.requestJump();
    item.motion.step(DT);
    assert.equal(item.motion.state.airborne, true);
    let peak = item.position.y;
    let frames = 0;
    while (item.motion.state.airborne && frames++ < 120) {
      item.motion.requestJump(); // Requests while airborne must not queue another jump.
      item.motion.step(DT);
      peak = Math.max(peak, item.position.y);
      assert.ok(item.position.y + 1.4 <= variant.roofY + .00001);
    }
    assert.ok(frames < 120, 'Repeated requests cannot keep the visitor airborne');
    assert.ok(peak > variant.deckY + .25);
    assert.equal(item.motion.state.level, 'loft');
    close(item.position.y, variant.deckY);
    run(item, {}, .2);
    assert.equal(item.motion.state.airborne, false);
    close(item.position.y, variant.deckY);
  });

  test(`${variant.number}: furniture and front rail apply only at their own height`, () => {
    const ground = fixture(variant, { x: .85, z: -3.3 });
    run(ground, { forward: 1 }, 1);
    assert.ok(ground.position.z >= -3.6 - .001, 'Downstairs cabinet must block a ground walker');

    const loft = fixture(variant);
    ascend(loft);
    until(loft, () => loft.position.z < -3.45, { forward: 1 });
    until(loft, () => loft.position.x > .85, { strafe: 1 });
    until(loft, () => loft.position.z < -4.7, { forward: 1 });
    close(loft.position.y, variant.deckY); // The cabinet beneath must not block this path.
    until(loft, () => loft.position.z > -3.45, { forward: -1 });
    until(loft, () => loft.position.x < .15, { strafe: -1 });
    run(loft, { forward: 1 }, 1.5);
    assert.ok(loft.position.z >= -4.3 - .001, 'Upstairs mattress must block a loft walker');
    until(loft, () => loft.position.z > -3.4, { forward: -1 });
    run(loft, { forward: -1 }, 1);
    assert.ok(loft.position.z <= -3.04 + .001, 'The loft rail must stop forward exit');
    assert.equal(loft.motion.state.level, 'loft');
    loft.motion.requestJump();
    run(loft, { forward: -1 }, 1);
    assert.ok(loft.position.z <= -3.04 + .001, 'Jumping must not bypass the loft rail');
    assert.equal(loft.motion.state.level, 'loft');

    const underRail = fixture(variant, { x: .2, z: -3.35 });
    until(underRail, () => underRail.position.z > -2.4, { forward: -1 });
    close(underRail.position.y, 0);
  });

  test(`${variant.number}: reset clears floor level, vertical velocity and queued jumps`, () => {
    const item = fixture(variant);
    ascend(item);
    item.motion.requestJump();
    item.motion.step(DT);
    assert.equal(item.motion.state.airborne, true);
    item.motion.reset();
    assert.deepEqual(item.position, item.world.spawn);
    assert.deepEqual(item.motion.state, { level: 'ground', airborne: false, verticalVelocity: 0 });
    item.motion.requestJump();
    item.motion.clearInput();
    item.motion.step(DT);
    assert.equal(item.motion.state.airborne, false);
    close(item.position.y, 0);
    item.motion.requestJump();
    item.motion.reset();
    item.motion.step(DT);
    assert.equal(item.motion.state.airborne, false, 'Reset must discard a pending jump');
  });

  test(`${variant.number}: jumping at low loft furniture cannot land inside its solid volume`, () => {
    const item = fixture(variant);
    ascend(item);
    until(item, () => item.position.z < -3.45, { forward: 1 });
    until(item, () => item.position.x > 0, { strafe: 1 });
    run(item, { forward: 1 }, 1);
    item.motion.requestJump();
    run(item, { forward: 1 }, 1.5);
    assert.equal(item.motion.state.airborne, false);
    const bed = item.world.obstacles.find(obstacle => obstacle.name === 'mattress');
    const dx = item.position.x - Math.max(bed.minX, Math.min(item.position.x, bed.maxX));
    const dz = item.position.z - Math.max(bed.minZ, Math.min(item.position.z, bed.maxZ));
    const insideSolid = dx * dx + dz * dz < .2 ** 2
      && item.position.y < bed.maxY - .006 && item.position.y + 1.4 > bed.minY + .006;
    assert.equal(insideSolid, false, `Landed inside mattress at ${JSON.stringify(item.position)}`);
  });
}
