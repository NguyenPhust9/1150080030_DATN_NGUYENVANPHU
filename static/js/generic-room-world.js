// A deliberately simple room until photographs and video are available.
// Dimensions and furnishings illustrate a layout, not a measured reconstruction.
export function buildGenericRoomWorld(THREE, scene, { offsetX = 0, number } = {}) {
  const group = new THREE.Group();
  group.name = `generic-room-${number}`;
  group.position.x = offsetX;
  scene.add(group);
  const obstacles = [], cameraObstacles = [];
  const cube = new THREE.BoxGeometry(1, 1, 1);
  const material = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: .78, ...extra });
  const plaster = material('#f3f0e8'), facade = material('#e7dfcf');
  const sage = material('#d6dfd0'), oak = material('#bc9870'), iron = material('#46534b');
  const linen = material('#f7f6ee'), fabric = material('#aebda6'), stone = material('#777e73');
  const chrome = material('#afbcb8', { metalness: .65, roughness: .3 });
  function box(x, y, z, width, height, depth, mat, solid = false, parent = group) {
    const item = new THREE.Mesh(cube, mat);
    item.position.set(x, y, z); item.scale.set(width, height, depth);
    item.castShadow = item.receiveShadow = true; parent.add(item);
    if (solid) {
      obstacles.push({ minX: offsetX + x - width / 2, maxX: offsetX + x + width / 2,
        minZ: z - depth / 2, maxZ: z + depth / 2, minY: y - height / 2, maxY: y + height / 2 });
      cameraObstacles.push(item);
    }
    return item;
  }
  function sign(text, subtitle, x, y, z, width, height) {
    const canvas = document.createElement('canvas'); canvas.width = 768; canvas.height = 384;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#3e4c42'; ctx.fillRect(0, 0, 768, 384);
    ctx.strokeStyle = '#b99867'; ctx.lineWidth = 16; ctx.strokeRect(8, 8, 752, 368);
    ctx.textAlign = 'center'; ctx.fillStyle = '#fff9e9'; ctx.font = '600 144px Segoe UI, sans-serif';
    ctx.fillText(text, 384, 208);
    ctx.fillStyle = '#e1d8c2'; ctx.font = '30px Segoe UI, sans-serif'; ctx.fillText(subtitle, 384, 298);
    const map = new THREE.CanvasTexture(canvas); map.colorSpace = THREE.SRGBColorSpace;
    const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material('#ffffff', { map }));
    item.position.set(x, y, z); group.add(item);
  }
  box(0, -.08, -3.3, 3.6, .16, 6.8, material('#d5d1c3'));
  // A few seams give the floor a scale without adding texture downloads.
  const grout = material('#e7e2d5');
  for (let z = -.6; z > -6.6; z -= .6) box(0, .003, z, 3.4, .006, .012, grout);
  for (let x = -1.2; x < 1.7; x += .6) box(x, .003, -3.3, .012, .006, 6.6, linen);
  box(-1.78, 2.25, -3.3, .16, 4.5, 6.8, plaster, true);
  box(1.78, 2.25, -3.3, .16, 4.5, 6.8, plaster, true);
  // Rear window has real depth; the wall around it stays solid for movement.
  box(0, .8, -6.68, 3.72, 1.6, .16, sage, true);
  box(0, 3.85, -6.68, 3.72, 1.3, .16, sage, true);
  for (const x of [-1.35, 1.35]) box(x, 2.4, -6.68, 1, 1.6, .16, sage, true);
  const glass = material('#c4dfdf', { metalness: .15, roughness: .27, emissive: '#bfd8d8', emissiveIntensity: .18 });
  box(0, 2.4, -6.68, 1.7, 1.6, .07, glass, true);
  for (const x of [-.85, 0, .85]) box(x, 2.4, -6.57, .045, 1.66, .05, iron);
  for (const y of [1.57, 2.4, 3.23]) box(0, y, -6.57, 1.74, .045, .05, iron);
  box(0, 4.55, -3.3, 3.72, .1, 6.8, plaster);
  for (const x of [-1.68, 1.68]) box(x, .09, -3.3, .025, .18, 6.6, stone);
  box(0, .09, -6.58, 3.4, .18, .025, stone);
  box(-.85, 2.25, 0, 1.7, 4.5, .18, facade, true);
  box(1.4, 2.25, 0, .6, 4.5, .18, facade, true);
  box(.55, 3.375, 0, 1.1, 2.25, .18, facade, true);
  const door = new THREE.Group(); door.name = `door-${number}`; group.add(door);
  box(.55, 1.1, 0, 1.08, 2.2, .055, oak, false, door);
  box(.55, 1.15, .034, .85, 1.8, .015, material('#c8aa82'), false, door);
  for (const z of [-.065, .065]) box(.96, 1.05, z, .16, .035, .04, chrome, false, door);
  for (const x of [-.035, 1.135]) box(x, 1.13, 0, .06, 2.26, .14, iron);
  box(.55, 2.26, 0, 1.23, .06, .14, iron);
  sign(number, 'PHÒNG MÔ PHỎNG', .55, 2.67, .12, .76, .38);

  // Leave the centre/right aisle open from the entrance to the rear window.
  box(-.85, .24, -3.95, 1.4, .4, 2.05, oak, true);
  box(-.85, .49, -3.95, 1.36, .18, 2, linen);
  box(-.85, .6, -4.91, 1.45, 1.08, .08, oak);
  box(-.85, .6, -4.57, .76, .13, .39, linen);
  box(-.85, .59, -3.51, 1.38, .04, 1.08, fabric);
  box(1.21, 1.02, -3.02, .84, 2.04, 1.26, oak, true);
  box(1.21, 1.04, -2.374, .76, 1.9, .025, linen);
  box(1.21, 1.04, -2.352, .012, 1.9, .02, stone);
  for (const x of [1.15, 1.28]) box(x, 1.08, -2.325, .018, .2, .025, iron);
  box(-1.13, .78, -1.35, 1.03, .07, .6, oak, true);
  for (const x of [-1.53, -.73]) for (const z of [-1.58, -1.12]) box(x, .38, z, .045, .76, .045, iron);
  obstacles.push({ minX: offsetX - 1.65, maxX: offsetX - .61, minZ: -1.66, maxZ: -1.04, minY: 0, maxY: .82 });
  box(-1.1, .44, -.72, .42, .07, .42, fabric, true);
  for (const x of [-1.26, -.94]) for (const z of [-.88, -.56]) box(x, .21, z, .04, .42, .04, iron);
  box(-1.1, .7, -.54, .42, .47, .05, oak);
  // Simple kitchenette and an enclosed wet area. These are illustrative fittings.
  box(-.7, .43, -6.2, 1.8, .86, .64, oak, true);
  box(-.7, .89, -6.2, 1.86, .06, .7, stone);
  box(-.43, .93, -6.2, .54, .025, .42, chrome);
  box(-.43, .948, -6.2, .45, .01, .33, stone);
  box(-.43, 1.1, -6.43, .025, .34, .025, chrome);
  box(-.43, 1.25, -6.32, .025, .025, .23, chrome);
  box(1.06, 1.12, -5.72, 1.26, 2.24, 1.72, plaster, true);
  box(1.04, 1.04, -4.846, .68, 2.08, .025, material('#b0b7ac'));
  box(.78, 1.03, -4.82, .04, .15, .04, iron);
  // Ceiling fitting is visible in first-person view without a costly shadow light.
  box(0, 4.47, -2.65, .6, .035, .6, material('#fffdf1', { emissive: '#fff4d8', emissiveIntensity: .5 }));

  return {
    group, obstacles, cameraObstacles, door,
    doorHinge: { x: offsetX, z: 0 },
    spawn: { x: offsetX + .55, y: 0, z: 2.4 },
    roomBounds: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: 0 },
    ceiling: { roomHeight: 4.5 }, headClearance: 4.5,
    stairs: null, loft: null,
    landmarks: [
      { position: { x: offsetX + .55, y: 1.3, z: .25 }, label: `Cửa phòng ${number}` },
      { position: { x: offsetX - .85, y: .9, z: -3.95 }, label: 'Khu nghỉ ngơi mô phỏng' },
    ],
  };
}
