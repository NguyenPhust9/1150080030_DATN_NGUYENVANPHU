// Movement uses explicit floor levels: entering a room beneath its mezzanine
// must never snap the visitor onto the upper floor just because X/Z overlap.
export function createWalkthroughMotion(world, position, { radius = .2, bodyHeight = 1.4, speed = 1.55 } = {}) {
  const state = { level: 'ground', airborne: false, verticalVelocity: 0 };
  let stairRoom = null;
  let queuedJump = false;
  let jumpHeight = 0;
  const gravity = 14;
  const EPS = .006;
  const insideLane = (room, x) => !!room.stairs && x >= room.stairs.minX + .07 && x <= room.stairs.maxX - .07;
  const stairCenter = room => (room.stairs.minX + room.stairs.maxX) / 2;
  function rampHeight(room, z) {
    const stairs = room.stairs;
    const t = Math.max(0, Math.min(1, (stairs.bottomZ - z) / (stairs.bottomZ - stairs.topZ)));
    return stairs.bottomY + (stairs.topY - stairs.bottomY) * t;
  }
  function supportAt(x, z, level = state.level, room = stairRoom) {
    if (level === 'stairs') return rampHeight(room, z);
    if (level === 'loft') return world.roomAt(x, z)?.loft?.y ?? position.y;
    return world.groundAt(x, z);
  }
  function overlaps(x, z, rect) {
    const dx = x - Math.max(rect.minX, Math.min(x, rect.maxX));
    const dz = z - Math.max(rect.minZ, Math.min(z, rect.maxZ));
    return dx * dx + dz * dz < radius * radius;
  }
  function canOccupy(x, z, y, level = state.level, activeStairs = stairRoom) {
    if (x < world.bounds.minX || x > world.bounds.maxX || z < world.bounds.minZ || z > world.bounds.maxZ) return false;
    if (world.isWalkable && !world.isWalkable(x, z, radius)) return false;
    const room = world.roomAt(x, z);
    if (z < 0 && (!room || x < room.minX + radius || x > room.maxX - radius)) return false;
    if (level === 'loft' && (!room?.loft || z > room.loft.maxZ - radius || z < room.loft.minZ + radius)) return false;
    if (y + bodyHeight > world.ceilingAt(x, z, level) + EPS) return false;
    if (world.obstacles.some(rect => {
      if (rect.tag === 'stairs' && level === 'stairs' && activeStairs && rect.roomNumber === activeStairs.number) return false;
      // Furniture is not a walkable platform. Keep its footprint closed upstairs
      // during a jump, otherwise landing on the loft floor would sink into it.
      if (rect.tag === 'loft-furniture' && level === 'loft') return overlaps(x, z, rect);
      if (y >= (rect.maxY ?? Infinity) - EPS || y + bodyHeight <= (rect.minY ?? 0) + EPS) return false;
      return overlaps(x, z, rect);
    })) return false;
    return !world.rooms.some(candidate => {
      if (y > 2.25) return false;
      const angle = candidate.door.rotation.y;
      return overlaps(x, z, {
        minX: candidate.hingeX - .04, maxX: candidate.hingeX + 1.1 * Math.cos(angle) + .04,
        minZ: -1.1 * Math.sin(angle) - .04, maxZ: .04,
      });
    });
  }
  function enterStairs(room, z) {
    const x = stairCenter(room);
    const y = rampHeight(room, z) + jumpHeight;
    if (!canOccupy(x, z, y, 'stairs', room)) return false;
    stairRoom = room;
    state.level = 'stairs';
    position.x = x; position.z = z; position.y = y;
    return true;
  }
  function tryMove(x, z, dz) {
    if (state.level === 'ground' && dz < 0) {
      const room = world.rooms.find(candidate => insideLane(candidate, x)
        && position.z >= candidate.stairs.bottomZ - .05
        && z <= candidate.stairs.bottomZ + .35 && z >= candidate.stairs.bottomZ - .1);
      if (room && enterStairs(room, z)) return true;
    }
    if (state.level === 'loft' && dz > 0) {
      const room = world.roomAt(x, z);
      if (room && insideLane(room, x) && z > room.stairs.topZ - .32 && enterStairs(room, z)) return true;
    }
    const nextGround = supportAt(x, z);
    const y = nextGround + jumpHeight;
    if (!canOccupy(x, z, y)) return false;
    position.x = x; position.z = z; position.y = y;
    return true;
  }
  function moveOnStairs(dt, forward) {
    if (!forward) return;
    const stairs = stairRoom.stairs;
    const slope = (stairs.topY - stairs.bottomY) / (stairs.bottomZ - stairs.topZ);
    const dz = -forward * speed * dt / Math.sqrt(1 + slope * slope);
    const z = position.z + dz;
    const x = stairCenter(stairRoom);
    let nextLevel = 'stairs';
    if (z <= stairs.topZ - .35) nextLevel = 'loft';
    if (z >= stairs.bottomZ + .36) nextLevel = 'ground';
    const y = (nextLevel === 'ground' ? world.groundAt(x, z) : rampHeight(stairRoom, z)) + jumpHeight;
    if (!canOccupy(x, z, y, nextLevel, stairRoom)) return;
    position.x = x; position.z = z; position.y = y;
    state.level = nextLevel;
    if (nextLevel !== 'stairs') stairRoom = null;
  }
  function step(dt, { forward = 0, strafe = 0, yaw = 0 } = {}) {
    const beforeX = position.x, beforeZ = position.z;
    if (state.level === 'stairs') moveOnStairs(dt, forward);
    else if (forward || strafe) {
      const length = Math.hypot(forward, strafe);
      const dx = (strafe * Math.cos(yaw) - forward * Math.sin(yaw)) / length * speed * dt;
      const dz = (-forward * Math.cos(yaw) - strafe * Math.sin(yaw)) / length * speed * dt;
      if (dx) tryMove(position.x + dx, position.z, 0);
      if (dz) tryMove(position.x, position.z + dz, dz);
    }
    if (queuedJump && !state.airborne) {
      state.airborne = true;
      state.verticalVelocity = 4.6;
    }
    queuedJump = false;
    const ground = supportAt(position.x, position.z);
    if (state.airborne) {
      jumpHeight += state.verticalVelocity * dt - .5 * gravity * dt * dt;
      state.verticalVelocity -= gravity * dt;
      const available = Math.max(0, world.ceilingAt(position.x, position.z, state.level) - bodyHeight - ground);
      if (jumpHeight > available) {
        jumpHeight = available;
        state.verticalVelocity = Math.min(0, state.verticalVelocity);
      }
      if (jumpHeight <= 0) {
        jumpHeight = 0;
        state.airborne = false;
        state.verticalVelocity = 0;
      }
    }
    position.y = ground + jumpHeight;
    const dx = position.x - beforeX, dz = position.z - beforeZ;
    return { moved: Math.hypot(dx, dz) > .0001, angle: Math.atan2(dx, dz) };
  }
  function reset() {
    Object.assign(position, { x: world.spawn.x, y: world.spawn.y, z: world.spawn.z });
    Object.assign(state, { level: 'ground', airborne: false, verticalVelocity: 0 });
    stairRoom = null; jumpHeight = 0; queuedJump = false;
  }
  return {
    state, step, reset,
    requestJump: () => { if (!state.airborne) queuedJump = true; },
    clearInput: () => { queuedJump = false; },
  };
}
