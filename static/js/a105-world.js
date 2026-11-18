/* A105: estimated dimensions, with finishes and fittings from its supplied photo/video. */
export function buildA105World(THREE, scene, { offsetX = -14.4 } = {}) {
    const group = new THREE.Group();
    group.name = 'a105-room-world';
    group.position.x = offsetX;
    scene.add(group);
    const obstacles = [], cameraObstacles = [];
    const unitBox = new THREE.BoxGeometry(1, 1, 1);
    const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 16);
    const materials = new Map();
    let seed = 105;
    const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    function mat(name, color, extra = {}) {
        if (!materials.has(name)) materials.set(name, new THREE.MeshStandardMaterial({ color, roughness: .68, ...extra }));
        return materials.get(name);
    }
    const white = mat('white', '#f6f5f0');
    const iron = mat('iron', '#252928', { metalness: .48, roughness: .42 });
    const chrome = mat('chrome', '#c0c8c6', { metalness: .9, roughness: .21 });
    const facade = mat('facade', '#e7dfcf');
    const glow = mat('glow', '#fffef7', { emissive: '#f7fbff', emissiveIntensity: .95, roughness: .25 });
    function texture(width, height, draw) {
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
        draw(canvas.getContext('2d'), width, height);
        const map = new THREE.CanvasTexture(canvas);
        map.colorSpace = THREE.SRGBColorSpace;
        map.wrapS = map.wrapT = THREE.RepeatWrapping;
        map.anisotropy = 4;
        return map;
    }
    const tileMap = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#b9b9b6'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 4600; i++) {
            ctx.fillStyle = i % 3 ? 'rgba(245,245,239,.1)' : 'rgba(100,102,99,.06)';
            ctx.beginPath(); ctx.ellipse(random() * w, random() * h, 2 + random() * 9, 1 + random() * 4, random() * Math.PI, 0, Math.PI * 2); ctx.fill();
        }
        for (let i = 0; i < 27; i++) {
            const x = random() * w, y = random() * h;
            ctx.strokeStyle = 'rgba(241,242,236,.17)'; ctx.lineWidth = .8 + random();
            ctx.beginPath(); ctx.moveTo(x, y);
            ctx.bezierCurveTo(x + 90, y - 58, x + 120, y + 14, x + 225, y - 75); ctx.stroke();
        }
        ctx.strokeStyle = '#e8e8e1'; ctx.lineWidth = 2.6; ctx.strokeRect(0, 0, w, h);
    });
    const woodMap = texture(512, 1024, (ctx, w, h) => {
        ctx.fillStyle = '#c69d59'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 210; i++) {
            const x = random() * w;
            ctx.strokeStyle = i % 3 ? 'rgba(249,220,154,.23)' : 'rgba(122,85,36,.16)';
            ctx.lineWidth = .5 + random() * 2;
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.bezierCurveTo(x - 8, 290, x + 12, 750, x + 1, h); ctx.stroke();
        }
        for (let i = 1; i < 5; i++) {
            ctx.fillStyle = 'rgba(130,86,33,.15)'; ctx.fillRect(i * 104, 0, 1.2, h);
        }
    });
    const stoneMap = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#616565'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 4000; i++) {
            ctx.fillStyle = i % 2 ? 'rgba(232,234,226,.34)' : 'rgba(21,29,27,.32)';
            ctx.fillRect(random() * w, random() * h, 1 + random() * 3, 1 + random() * 2);
        }
    });
    const ceilingMap = texture(256, 256, (ctx, w, h) => {
        ctx.fillStyle = '#eeeae1'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#b2afa7'; ctx.lineWidth = 3; ctx.strokeRect(0, 0, w, h);
        ctx.strokeStyle = '#faf8ef'; ctx.lineWidth = 1; ctx.strokeRect(3, 3, w - 6, h - 6);
    });
    const meshMap = texture(512, 256, (ctx, w, h) => {
        ctx.clearRect(0, 0, w, h); ctx.strokeStyle = '#242927'; ctx.lineWidth = 1.5;
        for (let x = -h; x < w + h; x += 12) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + h / 2, h); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x - h / 2, h); ctx.stroke();
        }
    });
    const wood = mat('wood', '#ffffff', { map: woodMap, roughness: .55 });
    const stone = mat('stone', '#ffffff', { map: stoneMap, roughness: .34 });
    const skirting = mat('skirting', '#8f9390', { map: tileMap, roughness: .43 });
    function mesh(geometry, material, x, y, z, sx = 1, sy = 1, sz = 1, parent = group) {
        const item = new THREE.Mesh(geometry, material);
        item.position.set(x, y, z); item.scale.set(sx, sy, sz);
        item.castShadow = true; item.receiveShadow = true; parent.add(item); return item;
    }
    const box = (x, y, z, width, height, depth, material, parent = group) => mesh(unitBox, material, x, y, z, width, height, depth, parent);
    const cylinder = (x, y, z, radius, height, material, parent = group) => mesh(unitCylinder, material, x, y, z, radius, height, radius, parent);
    function obstacle(x, z, width, depth, minY, maxY, extra = {}) {
        obstacles.push({ minX: offsetX + x - width / 2, maxX: offsetX + x + width / 2, minZ: z - depth / 2, maxZ: z + depth / 2, minY, maxY, ...extra });
    }
    function solid(x, y, z, width, height, depth, material, collidable = true) {
        const item = box(x, y, z, width, height, depth, material); cameraObstacles.push(item);
        if (collidable) obstacle(x, z, width, depth, y - height / 2, y + height / 2);
        return item;
    }
    function surface(x, y, z, width, height, ry, map, repeatX = 1, repeatY = 1, extra = {}) {
        const clone = map.clone(); clone.needsUpdate = true; clone.repeat.set(repeatX, repeatY);
        const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshStandardMaterial({ map: clone, roughness: .6, ...extra }));
        item.position.set(x, y, z); item.rotation.y = ry; item.receiveShadow = true; group.add(item); return item;
    }
    function rod(from, to, radius, material = chrome) {
        const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to), center = a.clone().add(b).multiplyScalar(.5);
        const item = cylinder(center.x, center.y, center.z, radius, a.distanceTo(b), material);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize()); return item;
    }
    function beam(from, to, width, depth, material = iron) {
        const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to), center = a.clone().add(b).multiplyScalar(.5);
        const item = box(center.x, center.y, center.z, width, a.distanceTo(b), depth, material);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize()); return item;
    }

    // The open front half has gray glossy tiles, low gray skirting and plain white walls.
    solid(0, -.08, -3.3, 3.76, .16, 6.92, mat('floorEdge', '#a9aca5'), false);
    const floor = surface(0, .006, -3.3, 3.4, 6.6, 0, tileMap, 5.67, 11, { roughness: .29 });
    floor.rotation.x = -Math.PI / 2; cameraObstacles.push(floor);
    solid(-1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(0, 2.25, -6.69, 3.76, 4.5, .18, white);
    solid(0, 4.56, -3.3, 3.76, .12, 6.8, white, false);
    for (const x of [-1.683, 1.683]) box(x, .105, -3.3, .03, .21, 6.6, skirting);
    box(0, .105, -6.582, 3.4, .21, .03, skirting);
    const suspendedCeiling = surface(0, 4.493, -3.3, 3.4, 6.6, 0, ceilingMap, 5.67, 11);
    suspendedCeiling.rotation.x = Math.PI / 2;
    for (const x of [-1.67, 1.67]) box(x, 4.465, -3.3, .05, .04, 6.6, mat('ceilingTrim', '#c9c7bd'));
    // Slim white fluorescent fittings and their surface cable match the supplied photograph.
    box(-1.657, 4.25, -1.6, .055, .105, 1.22, white);
    rod([-1.62, 4.25, -1.04], [-1.62, 4.25, -2.16], .022, glow);
    box(-1.683, 3.23, -3.3, .024, .024, 6.6, mat('conduit', '#d1cfc4'));
    box(-1.683, 2.86, -5.68, .024, .76, .024, white);

    // The source does not show the facade; this entrance follows the shared tour corridor.
    solid(-.85, 2.25, 0, 1.7, 4.5, .18, facade);
    solid(1.4, 2.25, 0, .6, 4.5, .18, facade);
    solid(.55, 3.375, 0, 1.1, 2.25, .18, facade, false);
    const door = new THREE.Group(); door.name = 'a105-front-door'; group.add(door);
    const doorPanel = mat('doorPanel', '#626b5f', { metalness: .2, roughness: .58 });
    for (const x of [.028, 1.072]) box(x, 1.12, 0, .056, 2.24, .075, iron, door);
    for (const y of [.028, .8, 2.212]) box(.55, y, 0, 1.1, .056, .075, iron, door);
    box(.55, .4, 0, .99, .72, .045, doorPanel, door);
    for (let i = 0; i < 7; i++) box(.55, .94 + i * .18, 0, 1.04, .026, .04, iron, door);
    for (const x of [.29, .81]) box(x, 1.52, 0, .025, 1.35, .04, iron, door);
    for (const z of [-.07, .07]) box(.96, 1.05, z, .14, .028, .035, chrome, door);
    for (const x of [-.035, 1.135]) box(x, 1.15, 0, .06, 2.3, .15, iron);
    box(.55, 2.29, 0, 1.23, .06, .15, iron);
    box(.55, .025, .02, 1.1, .05, .22, mat('threshold', '#bdc0b6'));
    const signMap = texture(768, 384, (ctx, w, h) => {
        ctx.fillStyle = '#b98851'; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#3e4840'; ctx.fillRect(9, 9, w - 18, h - 18);
        ctx.textAlign = 'center'; ctx.fillStyle = '#fff7de'; ctx.font = '600 146px Segoe UI, sans-serif'; ctx.fillText('A105', w / 2, 204);
        ctx.fillStyle = '#dfd3b5'; ctx.font = '34px Segoe UI, sans-serif'; ctx.fillText('TÒA NHÀ AN TÂM', w / 2, 295);
    });
    box(.55, 2.65, .105, .69, .36, .025, wood);
    surface(.55, 2.65, .122, .67, .34, 0, signMap);

    // Gold wood decking rests on exposed dark steel beams; the loft is empty in the sources.
    const topY = 2.4, bottomZ = -.85, topZ = -2.8, stairX = -1.23;
    solid(0, 2.367, -4.7, 3.4, .066, 3.8, wood, false);
    const loftFloor = surface(0, 2.402, -4.7, 3.4, 3.8, 0, woodMap, 3.4, 2.7, { roughness: .55 });
    loftFloor.rotation.x = -Math.PI / 2;
    box(0, 2.388, topZ + .02, 3.4, .07, .045, wood);
    for (const z of [-2.85, -3.6, -4.35, -5.1, -5.85, -6.53]) {
        cameraObstacles.push(box(0, 2.285, z, 3.4, .09, .065, iron));
        box(0, 2.244, z, 3.4, .018, .09, iron);
    }
    for (const x of [-1.66, 1.66]) box(x, 2.285, -4.7, .065, .09, 3.8, iron);
    // Offset the guardrail to leave a clear left-hand stair landing.
    for (const y of [2.44, 3.36]) cameraObstacles.push(box(.45, y, topZ, 2.5, .045, .045, iron));
    for (const x of [-.8, 1.68]) cameraObstacles.push(box(x, 2.9, topZ, .045, .965, .045, iron));
    const railMesh = surface(.45, 2.9, topZ + .002, 2.22, .52, 0, meshMap, 1, 1, { side: THREE.DoubleSide, alphaTest: .45, metalness: .35, roughness: .47 });
    railMesh.castShadow = true;
    for (const y of [2.62, 3.18]) box(.45, y, topZ, 2.28, .045, .05, iron);
    for (const x of [-.69, 1.59]) box(x, 2.9, topZ, .045, .6, .05, iron);
    for (const x of [-.59, 1.44]) {
        box(x, 3.27, topZ, .032, .18, .045, iron);
        box(x, 2.53, topZ, .032, .18, .045, iron);
    }
    obstacle(.45, topZ, 2.58, .08, topY, 3.4, { tag: 'loft-rail' });

    // Open steel treads and two black stringers distinguish this room from A104's wood stairs.
    const stepCount = 8, stepDepth = (bottomZ - topZ) / stepCount;
    for (let i = 1; i <= stepCount; i++) {
        const y = topY * i / stepCount, z = bottomZ - i * stepDepth;
        for (const dz of [-.105, .105]) box(stairX, y, z + dz, .74, .038, .035, iron);
        for (const dx of [-.35, .35]) box(stairX + dx, y, z, .035, .038, .21, iron);
        box(stairX, y - .007, z, .66, .018, .17, mat('tread', '#343b37', { metalness: .42, roughness: .58 }));
    }
    for (const x of [-1.6, -.86]) beam([x, .03, bottomZ + .1], [x, topY + .025, topZ - .025], .065, .085);
    obstacle(stairX, (bottomZ + topZ) / 2, .82, bottomZ - topZ, 0, topY, { tag: 'stairs' });

    // Only the white bathroom enclosure is visible: its unseen interior remains closed off.
    // The recessed dark doorway sits beside the sink, at the left edge of the partition.
    solid(.91, 1.12, -5.825, 1.58, 2.24, 1.55, white);
    box(.13, .105, -5.035, .03, .21, .035, skirting);
    box(.92, .105, -5.035, 1.56, .21, .03, skirting);
    box(.126, 1.09, -5.43, .018, 2.18, .67, mat('bathDoorRecess', '#303737', { roughness: .86 }));
    for (const z of [-5.07, -5.79]) box(.105, 1.1, z, .04, 2.2, .035, iron);
    box(.105, 2.185, -5.43, .04, .04, .755, iron);

    // Rear-left oak sink cabinet: two open shelves on the left, a plain panel on the right.
    const cabinetX = -.94, cabinetZ = -6.2, cabinetWidth = 1.28;
    obstacle(cabinetX, cabinetZ, cabinetWidth, .6, 0, .94);
    box(cabinetX, .075, cabinetZ, cabinetWidth, .11, .6, wood);
    box(cabinetX, .46, -6.475, cabinetWidth, .75, .04, wood);
    for (const x of [-1.56, -.32]) cameraObstacles.push(box(x, .46, cabinetZ, .04, .75, .6, wood));
    box(-1.12, .46, cabinetZ, .035, .75, .6, wood);
    for (const y of [.15, .46, .8]) box(-1.345, y, cabinetZ, .43, .035, .57, wood);
    box(-.72, .46, -5.89, .78, .73, .035, wood);
    box(-.73, .46, -5.867, .009, .71, .006, mat('cabinetSeam', '#aa813f'));
    solid(cabinetX, .875, cabinetZ, 1.34, .055, .65, stone);
    box(cabinetX, .944, -6.49, 1.34, .105, .035, stone);
    box(-1.59, .944, cabinetZ, .035, .105, .65, stone);
    box(-.63, .91, -6.19, .52, .018, .4, chrome);
    box(-.63, .923, -6.19, .43, .013, .31, mat('basin', '#697a77', { metalness: .75, roughness: .24 }));
    const tap = new THREE.CubicBezierCurve3(new THREE.Vector3(-.62, .93, -6.415), new THREE.Vector3(-.62, 1.39, -6.415), new THREE.Vector3(-.62, 1.4, -6.12), new THREE.Vector3(-.62, 1.18, -6.12));
    mesh(new THREE.TubeGeometry(tap, 24, .013, 8, false), chrome, 0, 0, 0);
    rod([-.62, 1.0, -6.415], [-.52, 1.04, -6.415], .01);
    box(-.98, 2.04, -6.565, .69, .075, .06, white);
    rod([-1.28, 2.035, -6.523], [-.68, 2.035, -6.523], .018, glow);
    // The socket and white surface conduit are visible just above the worktop.
    box(-1.56, 1.44, -6.57, .085, .12, .025, white);
    for (const dx of [-.015, .015]) box(-1.56 + dx, 1.44, -6.55, .007, .02, .006, iron);
    box(-1.56, 1.83, -6.576, .018, .66, .018, white);

    return {
        group,
        obstacles,
        cameraObstacles,
        door,
        doorHinge: { x: offsetX, z: 0 },
        spawn: { x: offsetX + .55, y: 0, z: 2.4 },
        roomBounds: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: 0 },
        bounds: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: 3.4 },
        ceiling: { loftFrontZ: topZ, undersideY: 2.24, roomHeight: 4.5 },
        headClearance: 2.2,
        stairs: { minX: offsetX - 1.6, maxX: offsetX - .86, bottomZ, topZ, bottomY: 0, topY },
        loft: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: topZ, y: topY, ceilingY: 4.5 },
        landmarks: [
            { position: { x: offsetX + .55, y: 1.3, z: .25 }, label: 'Cửa phòng A105' },
            { position: { x: offsetX - 1.23, y: 1.2, z: -1.75 }, label: 'Cầu thang sắt lên gác' },
            { position: { x: offsetX + .35, y: 2.9, z: -2.75 }, label: 'Gác gỗ và lan can lưới thép' },
            { position: { x: offsetX - .94, y: 1.2, z: -5.82 }, label: 'Tủ gỗ và bồn rửa' },
            { position: { x: offsetX + .65, y: 1.3, z: -5.0 }, label: 'Vách khu vệ sinh' },
        ],
    };
}
