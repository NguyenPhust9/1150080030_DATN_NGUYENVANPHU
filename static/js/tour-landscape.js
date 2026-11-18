// An illustrative courtyard and neighbourhood, not a survey of the real address.
// Static instances share geometry/materials; the central walk connects to the entrance.
export function buildTourLandscape(THREE, parent, { activeFloor = 1, lowestFloor = 1, centerX = -7.2 } = {}) {
  const group = new THREE.Group();
  group.name = 'tour-landscape';
  const groundY = -(activeFloor - lowestFloor) * 4.8;
  group.position.y = groundY;
  parent.add(group);
  const geometry = {
    box: new THREE.BoxGeometry(1, 1, 1),
    trunk: new THREE.CylinderGeometry(.82, 1, 1, 7),
    crown: new THREE.IcosahedronGeometry(1, 1),
    cloud: new THREE.SphereGeometry(1, 8, 5),
    wheel: new THREE.CylinderGeometry(1, 1, 1, 10),
  };
  const palette = {
    soil: ['#aab491', .95], grass: ['#8baf65', .96],
    paving: ['#dcd4c4', .94], seam: ['#c4c0b3', 1], path: ['#efe7d5', .9],
    stone: ['#c9c5b6', .91], terracotta: ['#b98967', .9], wood: ['#9c7654', .86],
    bark: ['#756348', 1], leaf: ['#578557', 1], leafLight: ['#76a05c', 1], leafDeep: ['#426e4e', 1],
    metal: ['#53635c', .63], road: ['#7f8580', .99], roadMark: ['#e3ddc6', .9],
    plaster: ['#e3dfcf', .95], plasterWarm: ['#d3bea0', .95], plasterMint: ['#b9c8bb', .95],
    plasterBlue: ['#bbc9ce', .95], roof: ['#a8a99b', .95], glazing: ['#65878b', .4],
    cloud: ['#f9f6e9', 1], carCream: ['#e1d7bc', .6], carBlue: ['#72969e', .6],
    rubber: ['#424a45', .98], lamp: ['#fff5d8', .65], flower: ['#dba58c', .95],
  };
  const materials = Object.fromEntries(Object.entries(palette).map(([key, [color, roughness]]) => [key,
    new THREE.MeshStandardMaterial({ color, roughness, flatShading: ['leaf', 'leafLight', 'leafDeep', 'cloud'].includes(key),
      ...(key === 'glazing' ? { metalness: .22 } : {}),
      ...(key === 'lamp' ? { emissive: '#ffe5ac', emissiveIntensity: .2 } : {}) })]));
  const batches = new Map();
  const transform = new THREE.Object3D();
  function add(kind, color, x, y, z, sx, sy, sz, rotation = null) {
    const key = `${kind}:${color}`;
    if (!batches.has(key)) batches.set(key, { kind, color, matrices: [] });
    transform.position.set(x, y, z); transform.scale.set(sx, sy, sz);
    transform.rotation.set(rotation?.[0] || 0, rotation?.[1] || 0, rotation?.[2] || 0);
    transform.updateMatrix(); batches.get(key).matrices.push(transform.matrix.clone());
  }
  const box = (color, x, y, z, w, h, d, rotation) => add('box', color, x, y, z, w, h, d, rotation);
  function branch(from, to, radius) {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const direction = b.clone().sub(a);
    const key = 'trunk:bark';
    if (!batches.has(key)) batches.set(key, { kind: 'trunk', color: 'bark', matrices: [] });
    transform.position.copy(a).add(b).multiplyScalar(.5);
    transform.scale.set(radius, direction.length(), radius);
    transform.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    transform.updateMatrix(); batches.get(key).matrices.push(transform.matrix.clone());
  }
  function tree(x, z, size = 1, seed = 0) {
    const base = .18, trunkTop = base + 3.65 * size;
    add('trunk', 'bark', x, base + 1.9 * size, z, .19 * size, 3.8 * size, .19 * size);
    const tips = [
      [-1.4, 4.4, .1], [1.35, 4.8, .25], [.1, 4.25, -1.3], [.1, 5.1, 1.15], [0, 5.6, 0],
    ];
    tips.forEach(([dx, y, dz], index) => {
      branch([x, trunkTop - .7 * size, z], [x + dx * size, base + y * size, z + dz * size], .065 * size);
      const foliage = ['leaf', 'leafLight', 'leafDeep'][(index + seed) % 3];
      add('crown', foliage, x + dx * size, base + y * size, z + dz * size,
        (1.55 + index % 2 * .15) * size, (1.15 + index % 3 * .12) * size, 1.55 * size, [0, index * .9, .13]);
    });
  }
  function shrubs(x, z, width, count = 5) {
    for (let i = 0; i < count; i++) {
      const atX = x - width / 2 + width * (i + .5) / count;
      add('crown', i % 2 ? 'leafLight' : 'leaf', atX, .55, z + Math.sin(i * 2.1) * .13, .58, .44, .53);
      if (i % 2 === 0) add('crown', 'flower', atX + .14, .92, z, .11, .08, .1);
    }
  }
  function lawn(x, z, w, d) {
    box('stone', x, .105, z, w + .32, .21, d + .32);
    box('grass', x, .22, z, w, .05, d);
    for (const dx of [-w / 2 - .07, w / 2 + .07]) box('path', x + dx, .235, z, .13, .06, d + .27);
    for (const dz of [-d / 2 - .07, d / 2 + .07]) box('path', x, .235, z + dz, w + .28, .06, .13);
  }
  function bench(x, z, angle = 0) {
    // Keep every plank in one shared wood batch, including rotated benches.
    const local = (color, dx, y, dz, w, h, d) => {
      const cos = Math.cos(angle), sin = Math.sin(angle);
      box(color, x + dx * cos + dz * sin, y, z - dx * sin + dz * cos, w, h, d, [0, angle, 0]);
    };
    for (let i = 0; i < 4; i++) local('wood', 0, .54, -.22 + i * .145, 2.1, .065, .12);
    for (const y of [.83, 1.02]) local('wood', 0, y, .27, 2.1, .13, .055);
    for (const dx of [-.82, .82]) {
      local('metal', dx, .27, 0, .065, .54, .58);
      local('metal', dx, .8, .28, .045, .64, .045);
      local('metal', dx, .72, -.02, .055, .055, .6);
    }
  }

  // Extend the ground well into fog so the view never ends at a floating slab.
  box('soil', centerX, -.25, 113.9, 280, .4, 220);
  box('paving', centerX, -.015, 17.4, 66, .12, 26);
  for (let x = centerX - 32.5; x <= centerX + 32.5; x += 2.5) box('seam', x, .05, 17.4, .025, .009, 26);
  for (let z = 4.9; z <= 29.9; z += 2.5) box('seam', centerX, .05, z, 66, .009, .025);
  // The broad centre walk remains open from the corridor all the way to the gate.
  box('path', centerX, .065, 17.25, 5.1, .035, 25.7);
  for (const dx of [-2.65, 2.65]) box('terracotta', centerX + dx, .072, 17.25, .13, .045, 25.7);
  box('path', centerX, .075, 23.55, 61, .04, 2.7);
  for (const side of [-1, 1]) {
    const lawnX = centerX + side * 12.1;
    lawn(lawnX, 14.1, 13.2, 13.2);
    tree(centerX + side * 13.5, 11, 1.02, side > 0 ? 1 : 0);
    tree(centerX + side * 16.6, 18.2, .86, 2);
    shrubs(lawnX, 19.7, 10.7, 9);
    lawn(centerX + side * 25.7, 15.7, 7.1, 17.5);
    tree(centerX + side * 25, 11.6, 1.16, 1);
    tree(centerX + side * 26.7, 21.2, 1.02, 0);
    bench(centerX + side * 7.1, 21.5, side > 0 ? -.12 : .12);
    bench(centerX + side * 20.6, 15.5, side * Math.PI / 2);
    shrubs(centerX + side * 11.6, 26.6, 11, 8);
    // Small courtyard lamps add scale without adding any real-time lights.
    for (const z of [8, 24.1]) {
      const x = centerX + side * 4.3;
      add('trunk', 'metal', x, 1.65, z, .045, 3.3, .045);
      box('metal', x, 3.3, z, .5, .07, .5);
      box('lamp', x, 3.13, z, .29, .27, .29);
      box('metal', x, 2.98, z, .4, .06, .4);
    }
  }
  // The walkable central path passes through this open gate. Planting, lamps and
  // boundary walls remain outside that path and need no extra collision meshes.
  for (const side of [-1, 1]) {
    const x = centerX + side * 18.5;
    box('plaster', x, .43, 29.45, 29, .86, .32);
    box('stone', x, .91, 29.45, 29.1, .12, .45);
    box('metal', x, 1.46, 29.45, 29, .045, .045);
    for (let dx = -14.25; dx <= 14.3; dx += 1.05) box('metal', x + dx, 1.21, 29.45, .035, .55, .035);
    box('plaster', centerX + side * 3.7, 1.17, 29.45, .62, 2.34, .62);
    box('terracotta', centerX + side * 3.7, 2.38, 29.45, .76, .12, .76);
  }
  // Street, footways and restrained markings establish a familiar urban setting.
  box('stone', centerX, -.005, 32.2, 220, .12, 4.7);
  box('road', centerX, -.04, 39.2, 250, .08, 9.3);
  box('stone', centerX, -.005, 46.1, 240, .12, 4.5);
  for (const z of [34.55, 43.9]) box('path', centerX, .08, z, 220, .16, .18);
  for (let x = centerX - 120; x < centerX + 120; x += 6.8) box('roadMark', x, .008, 39.2, 3.7, .012, .12);
  for (let z = 35.35; z < 43.3; z += 1.05) box('roadMark', centerX + 4.8, .012, z, 3.7, .012, .48);
  function car(x, z, color, angle) {
    const cos = Math.cos(angle), sin = Math.sin(angle);
    const part = (mat, dx, y, dz, w, h, d) => box(mat, x + dx * cos + dz * sin, y, z - dx * sin + dz * cos, w, h, d, [0, angle, 0]);
    part(color, 0, .62, 0, 3.75, .65, 1.68);
    part('glazing', .05, 1.14, 0, 1.95, .55, 1.48);
    part(color, .05, 1.45, 0, 1.83, .09, 1.5);
    for (const dx of [-1.13, 1.13]) for (const dz of [-.79, .79]) {
      add('wheel', 'rubber', x + dx * cos + dz * sin, .37, z - dx * sin + dz * cos, .34, .18, .34, [Math.PI / 2, 0, 0]);
    }
    for (const dz of [-.58, .58]) part('lamp', 1.89, .68, dz, .035, .19, .28);
  }
  car(centerX - 17, 36.9, 'carCream', 0);
  car(centerX + 21, 41.5, 'carBlue', Math.PI);

  // Varied heights, balconies and roof parapets avoid a flat wall of repeated boxes.
  function house(x, frontZ, width, storeys, color, index) {
    const h = storeys * 3.05, depth = 9 + index % 3 * 1.3;
    box(color, x, h / 2, frontZ + depth / 2, width, h, depth);
    box('roof', x, h + .12, frontZ + depth / 2, width + .26, .24, depth + .26);
    box(color, x, h + .53, frontZ + .1, width, .83, .2);
    for (const dx of [-width / 2 + .1, width / 2 - .1]) box(color, x + dx, h + .53, frontZ + depth / 2, .2, .83, depth);
    box('metal', x - width * .25, h + .59, frontZ + 3.1, 1.25, .42, 1.5);
    // Small roof water tank and foliage on selected terraces.
    if (index % 3 === 0) add('trunk', 'stone', x + width * .22, h + 1.08, frontZ + 5.8, .64, 1.7, .64);
    for (let level = 0; level < storeys; level++) {
      const base = level * 3.05;
      for (const dx of [-width * .235, width * .235]) {
        box('path', x + dx, base + 1.6, frontZ - .055, width * .29, 1.85, .12);
        box('glazing', x + dx, base + 1.6, frontZ - .13, width * .255, 1.65, .035);
        box('path', x + dx, base + 1.6, frontZ - .155, .045, 1.66, .04);
      }
      if (level > 0 && (level + index) % 3 !== 0) {
        const balconyWidth = width * .8;
        box('stone', x, base + .24, frontZ - .56, balconyWidth, .17, 1.16);
        box('metal', x, base + 1.24, frontZ - 1.09, balconyWidth, .05, .05);
        for (let dx = -balconyWidth / 2; dx <= balconyWidth / 2 + .01; dx += balconyWidth / 7) {
          box('metal', x + dx, base + .74, frontZ - 1.09, .04, .98, .04);
        }
        if (level % 2 === 0) {
          box('terracotta', x - balconyWidth * .33, base + .48, frontZ - .65, .65, .38, .45);
          add('crown', 'leaf', x - balconyWidth * .33, base + .88, frontZ - .65, .43, .38, .35);
        }
      }
      box('roof', x, base + 2.96, frontZ - .09, width + .08, .12, .2);
    }
  }
  let facadeX = centerX - 67;
  const facades = ['plaster', 'plasterMint', 'plasterWarm', 'plasterBlue'];
  for (let i = 0; i < 16; i++) {
    const width = 6.6 + (i * 7 % 4) * .9;
    house(facadeX + width / 2, 49.4 + i % 3 * .7, width, 3 + i * 3 % 4, facades[i % facades.length], i);
    facadeX += width + .55;
  }
  // Trees along the far footway soften the elevation; side trees extend the scene.
  for (let i = 0; i < 10; i++) tree(centerX - 52 + i * 11.2, 46, .76 + i % 3 * .06, i);
  for (const side of [-1, 1]) for (let i = 0; i < 4; i++) tree(centerX + side * (39 + i * 8), 12 + i * 5.4, 1.1 + i % 2 * .2, i);
  for (let i = 0; i < 9; i++) {
    const x = centerX - 95 + i * 24, h = 17 + i % 4 * 7;
    box(i % 2 ? 'plasterBlue' : 'plasterMint', x, h / 2, 92 + i % 3 * 7, 15 + i % 3 * 3, h, 13);
    box('roof', x, h + .18, 92 + i % 3 * 7, 15.5 + i % 3 * 3, .36, 13.5);
  }
  // Broad, quiet clouds stay behind the buildings, clear of the player camera.
  for (const [x, y, z, size] of [[-48, 40, 112, 1.2], [18, 47, 132, 1.5], [67, 35, 105, .9]]) {
    for (let i = 0; i < 5; i++) add('cloud', 'cloud', centerX + x + (i - 2) * 4.2 * size,
      y + Math.sin(i * 1.5) * 1.4 * size, z + i % 2 * 1.6, 6 * size, 2.1 * size, 3.5 * size);
  }

  let instances = 0, triangles = 0;
  for (const { kind, color, matrices } of batches.values()) {
    const mesh = new THREE.InstancedMesh(geometry[kind], materials[color], matrices.length);
    mesh.name = `landscape-${kind}-${color}`;
    matrices.forEach((matrix, index) => mesh.setMatrixAt(index, matrix));
    mesh.instanceMatrix.needsUpdate = true;
    mesh.castShadow = color !== 'cloud' && color !== 'glazing';
    mesh.receiveShadow = color !== 'cloud';
    mesh.computeBoundingSphere();
    group.add(mesh);
    instances += matrices.length;
    triangles += (geometry[kind].index?.count || geometry[kind].attributes.position.count) / 3 * matrices.length;
  }
  return { group, groundY, centerX, lowestFloor, bounds: { minX: centerX - 140, maxX: centerX + 140, minZ: 3.9, maxZ: 223.9 },
    drawCalls: batches.size, instances, triangles };
}
