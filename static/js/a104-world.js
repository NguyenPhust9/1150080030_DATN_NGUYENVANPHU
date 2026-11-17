/* A104: estimated geometry from the supplied two photos and ten-second room tour. */
export function buildA104World(THREE, scene, { offsetX = -10.8 } = {}) {
    const group = new THREE.Group();
    group.name = 'a104-room-world';
    group.position.x = offsetX;
    scene.add(group);
    const obstacles = [], cameraObstacles = [];
    const unitBox = new THREE.BoxGeometry(1, 1, 1);
    const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 20);
    const unitSphere = new THREE.SphereGeometry(1, 16, 12);
    const materials = new Map();
    let seed = 104;
    const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    function mat(name, color, extra = {}) {
        if (!materials.has(name)) materials.set(name, new THREE.MeshStandardMaterial({ color, roughness: .68, ...extra }));
        return materials.get(name);
    }
    const white = mat('white', '#f6f5ef');
    const porcelain = mat('porcelain', '#fafbf4', { roughness: .25 });
    const iron = mat('iron', '#242a2b', { metalness: .4, roughness: .43 });
    const chrome = mat('chrome', '#bec8c7', { metalness: .85, roughness: .2 });
    const facade = mat('facade', '#e7dfcf');
    const glow = mat('glow', '#fffef1', { emissive: '#fffbe8', emissiveIntensity: .85, roughness: .3 });
    const redPipe = mat('redPipe', '#9c302d', { metalness: .25, roughness: .45 });
    const dark = mat('dark', '#202525', { roughness: .5 });
    function texture(width, height, draw) {
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
        draw(canvas.getContext('2d'), width, height);
        const map = new THREE.CanvasTexture(canvas);
        map.colorSpace = THREE.SRGBColorSpace;
        map.wrapS = map.wrapT = THREE.RepeatWrapping;
        map.anisotropy = 4;
        return map;
    }
    const marbleMap = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#f2f2ee'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 31; i++) {
            const x = random() * w, y = random() * h;
            ctx.strokeStyle = `rgba(139,150,149,${.07 + random() * .12})`;
            ctx.lineWidth = .4 + random() * 1.2;
            ctx.beginPath(); ctx.moveTo(x, y);
            ctx.bezierCurveTo(x + 70, y - 43, x + 90, y + 5, x + 205, y - 105); ctx.stroke();
        }
        ctx.strokeStyle = '#d5d9d4'; ctx.lineWidth = 1.5; ctx.strokeRect(0, 0, w, h);
    });
    const floorMap = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#c8ccca'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 5000; i++) {
            ctx.fillStyle = i % 3 ? 'rgba(250,249,239,.09)' : 'rgba(105,118,116,.06)';
            ctx.beginPath(); ctx.ellipse(random() * w, random() * h, 1 + random() * 7, 1 + random() * 3, random() * Math.PI, 0, Math.PI * 2); ctx.fill();
        }
        for (let i = 0; i < 14; i++) {
            const x = random() * w, y = random() * h;
            ctx.strokeStyle = 'rgba(242,244,235,.17)'; ctx.lineWidth = 1.2;
            ctx.beginPath(); ctx.moveTo(x, y); ctx.bezierCurveTo(x + 80, y - 70, x + 90, y + 10, x + 170, y - 65); ctx.stroke();
        }
        ctx.strokeStyle = '#eef0e9'; ctx.lineWidth = 3; ctx.strokeRect(0, 0, w, h);
    });
    const woodMap = texture(512, 1024, (ctx, w, h) => {
        ctx.fillStyle = '#b78957'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 190; i++) {
            const x = random() * w;
            ctx.strokeStyle = i % 3 ? 'rgba(240,200,145,.22)' : 'rgba(88,52,23,.18)';
            ctx.lineWidth = .6 + random() * 2.2;
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.bezierCurveTo(x - 16, 290, x + 13, 760, x - 2, h); ctx.stroke();
        }
        for (let i = 1; i < 5; i++) {
            ctx.fillStyle = 'rgba(85,49,21,.13)'; ctx.fillRect(i * 105, 0, 1.5, h);
        }
    });
    const wood = mat('wood', '#ffffff', { map: woodMap, roughness: .54 });
    const stairWood = mat('stairWood', '#b68c69', { map: woodMap, roughness: .53 });
    const cabinetWhite = mat('cabinetWhite', '#f1f2e8', { roughness: .42 });
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
        const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshStandardMaterial({ map: clone, roughness: .58, ...extra }));
        item.position.set(x, y, z); item.rotation.y = ry; item.receiveShadow = true; group.add(item); return item;
    }
    function rod(from, to, radius, material = chrome, parent = group) {
        const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to), center = a.clone().add(b).multiplyScalar(.5);
        const item = cylinder(center.x, center.y, center.z, radius, a.distanceTo(b), material, parent);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize()); return item;
    }
    function downlight(x, y, z, radius = .082) {
        cylinder(x, y, z, radius + .018, .016, porcelain);
        cylinder(x, y - .012, z, radius, .012, glow);
    }

    // Pale square ceramic floor, glossy marble lower walls and one continuous black trim.
    solid(0, -.08, -3.3, 3.76, .16, 6.92, mat('floorEdge', '#b8bcb6'), false);
    const floor = surface(0, .006, -3.3, 3.4, 6.6, 0, floorMap, 5.67, 11, { roughness: .39 });
    floor.rotation.x = -Math.PI / 2; cameraObstacles.push(floor);
    solid(-1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(0, 2.25, -6.69, 3.76, 4.5, .18, white);
    solid(0, 4.56, -3.3, 3.76, .12, 6.8, white, false);
    for (const x of [-1.694, 1.694]) surface(x, .69, -3.3, 6.6, 1.38, x < 0 ? Math.PI / 2 : -Math.PI / 2, marbleMap, 11, 2.3, { roughness: .36 });
    surface(0, .69, -6.594, 3.4, 1.38, 0, marbleMap, 5.67, 2.3, { roughness: .36 });
    for (const x of [-1.681, 1.681]) box(x, 1.405, -3.3, .024, .045, 6.6, iron);
    box(0, 1.405, -6.58, 3.4, .045, .025, iron);
    for (const x of [-1.63, 1.63]) box(x, 4.39, -3.3, .14, .12, 6.6, white);
    for (const z of [-1.2, -3.35, -5.5]) box(0, 4.41, z, 3.4, .18, .12, white);
    for (const z of [-1.1, -4.0, -5.85]) downlight(0, 4.485, z, .09);
    // The red fire-suppression pipes run above the empty loft, visible in both sources.
    for (const x of [-1.38, 1.39]) {
        rod([x, 4.35, -.75], [x, 4.35, -6.35], .028, redPipe);
        for (const z of [-1.45, -3.6, -5.7]) box(x, 4.385, z, .075, .065, .025, chrome);
    }
    rod([-1.38, 4.35, -6.35], [1.39, 4.35, -6.35], .028, redPipe);
    rod([1.39, 4.35, -6.35], [1.39, 4.06, -6.35], .028, redPipe);

    // The photographed front balcony is adapted to the shared corridor entrance.
    // Its dark glazing, curtains and AC are retained; the rear wood door stays closed.
    solid(-1.58, 2.25, 0, .24, 4.5, .18, facade);
    solid(-.2, 2.25, 0, .4, 4.5, .18, facade);
    solid(-.93, 3.45, 0, 1.22, 2.1, .18, facade, false);
    solid(1.4, 2.25, 0, .6, 4.5, .18, facade);
    solid(.55, 3.375, 0, 1.1, 2.25, .18, facade, false);
    obstacle(-.85, 0, 1.7, .2, 0, 2.4);
    const glass = mat('glass', '#c4d5d4', { transparent: true, opacity: .22, roughness: .14, depthWrite: false });
    box(-.93, 1.2, -.01, 1.17, 2.35, .025, glass).castShadow = false;
    for (const x of [-1.55, -.94, -.32]) box(x, 1.2, -.012, .045, 2.4, .075, iron);
    for (const y of [.035, 2.385]) box(-.93, y, -.012, 1.28, .055, .075, iron);
    box(-.6, 1.16, -.075, .023, .2, .035, iron);
    for (const y of [.16, 1.1]) box(-.93, y, .09, 1.2, .034, .034, iron);
    for (let i = 0; i < 8; i++) box(-1.49 + i * .16, .63, .09, .018, .94, .025, iron);
    const curtain = mat('curtain', '#424b50', { roughness: .95 });
    for (const x of [-1.51, -.28]) {
        for (let i = 0; i < 6; i++) cylinder(x + (i - 2.5) * .038, 1.22, -.135 - (i % 2) * .014, .026, 2.38, curtain);
        box(x, .94, -.168, .25, .075, .045, mat('curtainTie', '#31393c'));
    }
    rod([-1.65, 2.47, -.13], [-.14, 2.47, -.13], .017, chrome);
    solid(-.93, 2.82, -.19, .87, .32, .21, mat('airConditioner', '#505b5d'), false);
    box(-.93, 2.7, -.305, .78, .048, .018, iron);
    for (const y of [2.69, 2.713, 2.736]) box(-.93, y, -.32, .75, .009, .01, chrome);
    const door = new THREE.Group(); door.name = 'a104-front-door'; group.add(door);
    for (const x of [.028, 1.072]) box(x, 1.12, 0, .056, 2.24, .075, iron, door);
    for (const y of [.028, 1.11, 2.212]) box(.55, y, 0, 1.1, .056, .075, iron, door);
    box(.55, 1.12, 0, .99, 2.13, .022, glass, door).castShadow = false;
    for (const z of [-.07, .07]) box(.97, 1.05, z, .13, .028, .035, chrome, door);
    for (const x of [-.035, 1.135]) box(x, 1.15, 0, .06, 2.3, .15, iron);
    box(.55, 2.29, 0, 1.23, .06, .15, iron);
    box(.55, .025, .02, 1.1, .05, .22, mat('threshold', '#c4c7bd'));
    const signMap = texture(768, 384, (ctx, w, h) => {
        ctx.fillStyle = '#b98851'; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#3e4840'; ctx.fillRect(9, 9, w - 18, h - 18);
        ctx.textAlign = 'center'; ctx.fillStyle = '#fff7de'; ctx.font = '600 146px Segoe UI, sans-serif'; ctx.fillText('A104', w / 2, 204);
        ctx.fillStyle = '#dfd3b5'; ctx.font = '34px Segoe UI, sans-serif'; ctx.fillText('TÒA NHÀ AN TÂM', w / 2, 295);
    });
    box(.55, 2.65, .105, .69, .36, .025, wood);
    surface(.55, 2.65, .122, .67, .34, 0, signMap);

    // White loft slab and horizontal metal guardrail, with an open landing over the stairs.
    const topY = 2.4, bottomZ = -.85, topZ = -2.8, stairX = -1.23;
    solid(0, 2.32, -4.7, 3.4, .16, 3.8, white, false);
    const loftFloor = surface(0, 2.402, -4.7, 3.4, 3.8, 0, marbleMap, 5.67, 6.33, { roughness: .5 });
    loftFloor.rotation.x = -Math.PI / 2;
    box(0, 2.345, -2.79, 3.4, .19, .045, porcelain);
    for (const y of [2.46, 2.88, 3.32]) cameraObstacles.push(box(.45, y, -2.8, 2.5, .042, .042, iron));
    for (const x of [-.8, .46, 1.67]) cameraObstacles.push(box(x, 2.88, -2.8, .045, .92, .045, iron));
    obstacle(.45, -2.8, 2.58, .08, topY, 3.37, { tag: 'loft-rail' });
    for (const x of [-.85, .85]) for (const z of [-3.15, -4.7, -6.1]) downlight(x, 2.23, z, .068);
    // Every tread is a wood storage unit, including the white cupboard fronts and cubbies.
    const stepCount = 8, stepDepth = (bottomZ - topZ) / stepCount;
    for (let i = 1; i <= stepCount; i++) {
        const top = topY * i / stepCount, z = bottomZ - stepDepth * i;
        box(stairX, top / 2, z, .74, top, stepDepth + .015, stairWood);
        box(stairX, top + .006, z, .77, .025, stepDepth + .025, wood);
        // Side-facing doors are on the room side of the stair, not on the walkable treads.
        const panelHeight = top - .1, panelDepth = stepDepth - .035;
        box(-.851, top / 2, z, .019, panelHeight, panelDepth, cabinetWhite);
        if (i === 2 || i === 4 || i === 6 || i === 8) {
            const cubbyHeight = .22, cy = top - .17;
            box(-.835, cy, z, .013, cubbyHeight, panelDepth - .025, mat('cubbyShade', '#9b9c87'));
            for (const edge of [-1, 1]) {
                box(-.817, cy + edge * cubbyHeight / 2, z, .045, .021, panelDepth, cabinetWhite);
                box(-.817, cy, z + edge * (panelDepth / 2 - .008), .045, cubbyHeight, .018, cabinetWhite);
            }
            if (top > .7) mesh(unitSphere, chrome, -.822, .45, z - .04, .017, .017, .017);
        } else mesh(unitSphere, chrome, -.822, Math.min(.9, top / 2), z - .04, .017, .017, .017);
    }
    obstacle(stairX, (bottomZ + topZ) / 2, .82, bottomZ - topZ, 0, topY, { tag: 'stairs' });
    rod([-1.647, 1.0, -1.0], [-1.647, 3.18, -2.73], .026, iron);
    for (const [y, z] of [[1, -1.0], [3.18, -2.73]]) rod([-1.69, y, z], [-1.647, y, z], .031, iron);

    // The small black cafe table and two chairs are shifted away from the entry swing.
    cylinder(1.35, .73, -1.94, .285, .035, dark);
    cylinder(1.35, .36, -1.94, .035, .71, iron);
    for (const dx of [-.18, .18]) rod([1.35, .12, -1.94], [1.35 + dx, .035, -1.94 + dx], .018, iron);
    obstacle(1.35, -1.94, .57, .57, 0, .77);
    for (const z of [-1.35, -2.53]) {
        const back = z < -1.94 ? -.18 : .18;
        box(1.35, .44, z, .43, .065, .41, dark);
        box(1.35, .74, z + back, .43, .47, .045, dark);
        for (const dx of [-.16, .16]) for (const dz of [-.15, .15]) rod([1.35 + dx, .42, z + dz], [1.35 + dx * 1.1, .025, z + dz * 1.2], .017, iron);
        obstacle(1.35, z, .47, .48, 0, 1.0);
    }

    // Dark refrigerator beside the storage stairs, with a silver microwave above it.
    const fridge = mat('fridge', '#272e2e', { metalness: .35, roughness: .38 });
    solid(-1.32, .82, -3.34, .6, 1.64, .62, fridge);
    box(-1.32, 1.16, -3.017, .56, .88, .024, mat('fridgeDoor', '#303737', { metalness: .4, roughness: .34 }));
    box(-1.32, .351, -3.017, .56, .67, .024, fridge);
    box(-1.32, .705, -2.997, .57, .016, .023, iron);
    for (const y of [.63, .79]) box(-1.52, y, -2.98, .14, .029, .029, chrome);
    for (const x of [-1.55, -1.09]) cylinder(x, .04, -3.08, .025, .075, iron);
    box(-1.12, 1.46, -2.995, .1, .14, .01, mat('energyLabel', '#7e9e69'));
    box(-1.365, 1.02, -2.992, .34, .13, .012, mat('fridgeLabel', '#b5b8ac'));
    box(-1.365, .99, -2.98, .28, .019, .004, iron);
    solid(-1.32, 1.82, -3.34, .59, .33, .45, mat('microwaveMetal', '#adb4b0', { metalness: .58, roughness: .4 }));
    box(-1.38, 1.82, -3.104, .43, .265, .022, dark);
    box(-1.38, 1.82, -3.089, .35, .19, .008, mat('microwaveGlass', '#56605c', { metalness: .4, roughness: .18 }));
    for (const y of [1.75, 1.89]) {
        const knob = cylinder(-1.068, y, -3.078, .043, .018, chrome); knob.rotation.x = Math.PI / 2;
    }

    // The reference only shows this tiled partition, vanity and closed wooden rear door.
    // No unobserved bathroom interior is invented behind them.
    solid(-.775, 1.12, -5.85, 1.85, 2.24, .14, white);
    surface(-.775, 1.1, -5.772, 1.85, 2.2, 0, marbleMap, 3.08, 3.67, { roughness: .31 });
    box(-.775, 1.405, -5.758, 1.85, .045, .02, iron);
    const vanityGray = mat('vanityGray', '#6b7579', { roughness: .46 });
    solid(-.45, .59, -5.5, .76, .53, .49, vanityGray);
    box(-.45, .59, -5.245, .012, .49, .012, iron);
    box(-.45, .88, -5.5, .82, .065, .55, porcelain);
    box(-.45, .922, -5.49, .58, .012, .32, mat('basinRecess', '#c5d3ce', { roughness: .24 }));
    for (const x of [-.82, -.08]) box(x, .922, -5.5, .065, .046, .53, porcelain);
    for (const z of [-5.72, -5.27]) box(-.45, .922, z, .73, .046, .055, porcelain);
    rod([-.45, .94, -5.7], [-.45, 1.08, -5.7], .018, chrome);
    rod([-.45, 1.08, -5.7], [-.45, 1.08, -5.56], .018, chrome);
    box(-.45, 1.09, -5.7, .075, .014, .025, chrome);
    box(-.45, 1.58, -5.744, .75, .69, .026, chrome);
    box(-.45, 1.58, -5.724, .71, .65, .013, mat('mirror', '#b9ced0', { metalness: .94, roughness: .09 }));
    box(-.45, 1.225, -5.66, .79, .018, .17, chrome);
    for (const x of [-.78, -.12]) box(x, 1.268, -5.59, .012, .075, .012, chrome);
    box(-.45, 1.3, -5.59, .67, .012, .012, chrome);
    box(-.18, .016, -5.25, .13, .016, .13, chrome);
    for (let i = 0; i < 5; i++) box(-.23 + i * .025, .026, -5.25, .007, .005, .1, iron);
    // The door at the far end is visible in the source but is not a second corridor exit.
    solid(.61, 1.08, -6.49, .91, 2.16, .055, wood);
    for (const x of [.135, 1.085]) box(x, 1.105, -6.45, .045, 2.21, .09, wood);
    box(.61, 2.195, -6.45, .99, .055, .09, wood);
    box(.28, .98, -6.446, .06, .2, .028, chrome);
    box(.34, 1.015, -6.415, .17, .025, .035, chrome);

    // Warm wood lower units, white stone worktop and white upper fronts on the right wall.
    solid(1.365, .43, -5.44, .63, .86, 2.02, wood);
    solid(1.34, .892, -5.44, .7, .055, 2.07, porcelain);
    box(1.023, .425, -5.44, .032, .77, 1.94, wood);
    for (const z of [-6.09, -5.44, -4.79]) {
        box(1.001, .43, z, .02, .74, .615, wood);
        box(.982, .72, z, .026, .018, .16, chrome);
    }
    solid(1.49, 1.87, -5.52, .4, .65, 1.85, wood);
    for (const z of [-6.13, -5.52, -4.91]) {
        box(1.275, 1.87, z, .035, .6, .59, cabinetWhite);
        box(1.25, 1.585, z, .023, .018, .18, chrome);
    }
    box(1.66, 1.215, -5.47, .025, .59, 2.12, porcelain);
    box(1.638, 1.405, -5.47, .024, .045, 2.12, iron);
    // The metal basin and high curved tap sit closest to the front, as in the tour video.
    box(1.34, .927, -4.9, .5, .019, .53, chrome);
    box(1.34, .94, -4.9, .39, .013, .42, mat('kitchenBasin', '#71817e', { metalness: .7, roughness: .27 }));
    const tap = new THREE.CubicBezierCurve3(new THREE.Vector3(1.56, .94, -4.9), new THREE.Vector3(1.56, 1.42, -4.9), new THREE.Vector3(1.23, 1.43, -4.9), new THREE.Vector3(1.23, 1.19, -4.9));
    mesh(new THREE.TubeGeometry(tap, 20, .014, 8, false), chrome, 0, 0, 0);
    rod([1.56, 1.02, -4.9], [1.56, 1.08, -4.79], .01, chrome);
    box(1.34, .943, -5.91, .49, .045, .44, iron);
    cylinder(1.34, .973, -5.91, .153, .012, dark);
    cylinder(1.34, 1.006, -5.91, .14, .057, mat('pan', '#4f5652', { metalness: .52, roughness: .42 }));
    rod([1.34, 1.02, -5.78], [1.34, 1.02, -5.56], .025, dark);
    // Small wall switches and outlets complete the photographed fittings.
    for (const [x, z, ry] of [[.08, -5.75, 0], [1.67, -4.25, -Math.PI / 2]]) {
        const socket = new THREE.Group(); socket.position.set(x, 1.35, z); socket.rotation.y = ry; group.add(socket);
        box(0, 0, 0, .09, .13, .018, mat('socketPlate', '#8c9491'), socket);
        for (const dx of [-.018, .018]) box(dx, 0, .012, .008, .026, .008, iron, socket);
    }

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
            { position: { x: offsetX + .55, y: 1.3, z: .25 }, label: 'Cửa phòng A104' },
            { position: { x: offsetX - 1.23, y: 1.2, z: -1.75 }, label: 'Cầu thang gỗ kết hợp tủ đựng đồ' },
            { position: { x: offsetX - 1.3, y: 1.1, z: -3.0 }, label: 'Tủ lạnh và lò vi sóng' },
            { position: { x: offsetX - .45, y: 1.2, z: -5.3 }, label: 'Bồn rửa, tủ xám và gương' },
            { position: { x: offsetX + 1.05, y: 1.1, z: -5.2 }, label: 'Tủ bếp gỗ và mặt đá trắng' },
        ],
    };
}
