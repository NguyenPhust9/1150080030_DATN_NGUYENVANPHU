/* A101: a measured-looking interpretation of the room's photos, not a survey. */
export function buildA101World(THREE, scene, { includeLanding = true } = {}) {
    const obstacles = [];
    const cameraObstacles = [];
    const world = new THREE.Group();
    world.name = 'a101-room-world';
    scene.add(world);
    const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
    const sphereGeometry = new THREE.SphereGeometry(1, 12, 8);
    const cylinderGeometry = new THREE.CylinderGeometry(1, 1, 1, 16);
    const materials = {};
    const material = (name, color, extra = {}) => {
        if (!materials[name]) materials[name] = new THREE.MeshStandardMaterial({ color, roughness: 0.82, ...extra });
        return materials[name];
    };
    const plaster = material('plaster', '#f3f0e8');
    const facade = material('facade', '#e7dfcf');
    const iron = material('iron', '#252a29', { metalness: 0.48, roughness: 0.48 });
    const shelfMetal = material('shelfMetal', '#343b35', { metalness: 0.3, roughness: 0.5 });
    const doorMetal = material('doorMetal', '#858b81', { metalness: 0.4, roughness: 0.55 });
    const porcelain = material('porcelain', '#f7f7ed', { roughness: 0.35 });
    const chrome = material('chrome', '#b4b9b4', { metalness: 0.8, roughness: 0.27 });
    const leaf = material('leaf', '#3f633b');
    const leafLight = material('leafLight', '#63814c');
    const soil = material('soil', '#443e2c');
    const wood = material('wood', '#b79568');
    const cream = material('cream', '#ebe5d5');
    let seed = 101;
    const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    function canvasTexture(width, height, draw) {
        const canvas = document.createElement('canvas');
        canvas.width = width; canvas.height = height;
        draw(canvas.getContext('2d'), width, height);
        const texture = new THREE.CanvasTexture(canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
        texture.anisotropy = 4;
        return texture;
    }
    const tileTexture = canvasTexture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#eeeee7'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 32; i++) {
            const startX = random() * w, startY = random() * h;
            ctx.strokeStyle = `rgba(159,163,154,${0.025 + random() * 0.07})`;
            ctx.lineWidth = 0.5 + random() * 1.7;
            ctx.beginPath(); ctx.moveTo(startX, startY);
            ctx.bezierCurveTo(startX + 70, startY - 45, startX - 10, startY - 115, startX + 140, startY - 180);
            ctx.stroke();
        }
        ctx.strokeStyle = '#cbcec5'; ctx.lineWidth = 3; ctx.strokeRect(0, 0, w, h);
        ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.lineWidth = 2; ctx.strokeRect(3, 3, w - 6, h - 6);
    });
    const borderTexture = canvasTexture(512, 80, (ctx, w, h) => {
        ctx.fillStyle = '#eeeade'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#7b7d66'; ctx.lineWidth = 4;
        ctx.beginPath(); ctx.moveTo(0, 5); ctx.lineTo(w, 5); ctx.moveTo(0, h - 5); ctx.lineTo(w, h - 5); ctx.stroke();
        for (let x = 24; x < w; x += 85) {
            ctx.strokeStyle = '#7b8263'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x - 38, 49); ctx.quadraticCurveTo(x, 20, x + 42, 44); ctx.stroke();
            ctx.fillStyle = '#8a9575';
            for (const direction of [-1, 1]) {
                ctx.beginPath(); ctx.ellipse(x + direction * 25, 37, 12, 4, direction * .5, 0, Math.PI * 2); ctx.fill();
            }
            for (let petal = 0; petal < 6; petal++) {
                const angle = petal * Math.PI / 3;
                ctx.fillStyle = petal % 2 ? '#b76a64' : '#a6504c';
                ctx.beginPath(); ctx.arc(x + Math.cos(angle) * 8, 39 + Math.sin(angle) * 8, 7, 0, Math.PI * 2); ctx.fill();
            }
            ctx.fillStyle = '#d8bd83'; ctx.beginPath(); ctx.arc(x, 39, 4, 0, Math.PI * 2); ctx.fill();
        }
    });
    const rugTexture = canvasTexture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#b89b65'; ctx.fillRect(0, 0, w, h);
        for (let radius = 3; radius < w / 2; radius += 3) {
            ctx.strokeStyle = radius % 2 ? '#aa8d5e' : '#c7ad78'; ctx.lineWidth = 1.8;
            ctx.beginPath(); ctx.arc(w / 2, h / 2, radius, 0, Math.PI * 2); ctx.stroke();
        }
        for (let i = 0; i < 1500; i++) {
            ctx.fillStyle = random() > .5 ? 'rgba(240,222,167,.16)' : 'rgba(91,67,37,.13)';
            ctx.fillRect(random() * w, random() * h, 2, 7);
        }
    });
    function mesh(geometry, mat, x, y, z, sx, sy, sz, parent = world) {
        const item = new THREE.Mesh(geometry, mat);
        item.position.set(x, y, z); item.scale.set(sx, sy, sz);
        item.castShadow = true; item.receiveShadow = true; parent.add(item);
        return item;
    }
    const box = (x, y, z, w, h, d, mat, parent = world) => mesh(boxGeometry, mat, x, y, z, w, h, d, parent);
    const cylinder = (x, y, z, r, h, mat, parent = world) => mesh(cylinderGeometry, mat, x, y, z, r, h, r, parent);
    function solid(x, y, z, w, h, d, mat, collidable = true) {
        const item = box(x, y, z, w, h, d, mat);
        cameraObstacles.push(item);
        if (collidable) obstacles.push({ minX: x - w / 2, maxX: x + w / 2, minZ: z - d / 2, maxZ: z + d / 2 });
        return item;
    }
    function surface(x, y, z, width, height, rotation, texture, repeatX, repeatY = 1, extra = {}) {
        const map = texture.clone(); map.needsUpdate = true; map.repeat.set(repeatX, repeatY);
        const mat = new THREE.MeshStandardMaterial({ map, roughness: .58, ...extra });
        const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), mat);
        item.position.set(x, y, z); item.rotation.y = rotation; item.receiveShadow = true; world.add(item);
        return item;
    }
    function rod(from, to, radius, mat, parent = world) {
        const start = new THREE.Vector3(...from), end = new THREE.Vector3(...to);
        const middle = start.clone().add(end).multiplyScalar(.5);
        const item = cylinder(middle.x, middle.y, middle.z, radius, start.distanceTo(end), mat, parent);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), end.sub(start).normalize());
        return item;
    }
    function sign(text, subtitle, x, y, z, width = .7, height = .35) {
        const texture = canvasTexture(768, 384, (ctx, w, h) => {
            ctx.fillStyle = '#b98851'; ctx.fillRect(0, 0, w, h);
            ctx.fillStyle = '#3e4840'; ctx.fillRect(9, 9, w - 18, h - 18);
            ctx.textAlign = 'center'; ctx.fillStyle = '#fff7de';
            ctx.font = '600 146px Segoe UI, sans-serif'; ctx.fillText(text, w / 2, 204);
            ctx.fillStyle = '#dfd3b5'; ctx.font = '34px Segoe UI, sans-serif'; ctx.fillText(subtitle, w / 2, 295);
        });
        box(x, y, z - .012, width + .02, height + .02, .025, wood);
        const item = surface(x, y, z + .004, width, height, 0, texture, 1);
        item.material.roughness = .8;
    }
    function plant(x, y, z, scale = 1, potMaterial = porcelain) {
        const group = new THREE.Group(); group.position.set(x, y, z); group.scale.setScalar(scale); world.add(group);
        const pot = new THREE.Mesh(new THREE.CylinderGeometry(.145, .105, .28, 18), potMaterial);
        pot.position.y = .14; pot.castShadow = true; pot.receiveShadow = true; group.add(pot);
        cylinder(0, .282, 0, .125, .012, soil, group);
        rod([0, .28, 0], [.025, .98, -.025], .014, material('stem', '#65734b'), group);
        for (let i = 0; i < 11; i++) {
            const angle = i * 2.4, height = .38 + i * .055;
            const distance = .18 + .055 * Math.sin(i);
            const leafX = Math.cos(angle) * distance, leafZ = Math.sin(angle) * distance;
            rod([0, height - .03, 0], [leafX, height + .035, leafZ], .006, leaf, group);
            const item = mesh(sphereGeometry, i % 3 ? leaf : leafLight, leafX, height + .045, leafZ, .16, .025, .065, group);
            item.rotation.set(.12 * Math.sin(angle), -angle, .22 * Math.cos(angle));
        }
        return group;
    }

    // The front door is at z=0; the room extends backwards along -Z.
    const floorMap = tileTexture.clone(); floorMap.needsUpdate = true; floorMap.repeat.set(3.2 / .62, 6.6 / .62);
    const floorMaterial = new THREE.MeshStandardMaterial({ map: floorMap, roughness: .38, metalness: .025 });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 6.6), floorMaterial);
    floor.rotation.x = -Math.PI / 2; floor.position.set(0, .006, -3.3); floor.receiveShadow = true;
    world.add(floor); cameraObstacles.push(floor);
    solid(0, -.09, -3.3, 3.52, .18, 6.92, cream, false);
    solid(-1.69, 2.1, -3.3, .18, 4.2, 6.8, plaster);
    solid(1.69, 2.1, -3.3, .18, 4.2, 6.8, plaster);
    solid(0, 2.1, -6.69, 3.52, 4.2, .18, plaster);
    solid(0, 4.26, -3.3, 3.52, .12, 6.8, plaster, false);
    // Side-wall ceramic tiles and the distinctive red floral edging from the photos.
    surface(-1.594, .66, -3.3, 6.6, 1.32, Math.PI / 2, tileTexture, 11, 2.2);
    surface(1.594, .66, -3.3, 6.6, 1.32, -Math.PI / 2, tileTexture, 11, 2.2);
    surface(0, .66, -6.594, 3.2, 1.32, 0, tileTexture, 5.33, 2.2);
    surface(-1.589, 1.36, -3.3, 6.6, .09, Math.PI / 2, borderTexture, 7.8);
    surface(1.589, 1.36, -3.3, 6.6, .09, -Math.PI / 2, borderTexture, 7.8);
    surface(0, 1.36, -6.589, 3.2, .09, 0, borderTexture, 3.8);
    for (const side of [-1, 1]) box(side * 1.583, .045, -3.3, .025, .09, 6.6, cream);

    // Front wall: real opening for the door and a barred window to its left.
    solid(-1.4, 2.1, 0, .4, 4.2, .18, facade);
    solid(-.2, 2.1, 0, .4, 4.2, .18, facade);
    solid(-.8, .51, 0, .8, 1.02, .18, facade);
    solid(-.8, 3.25, 0, .8, 1.9, .18, facade, false);
    solid(1.35, 2.1, 0, .5, 4.2, .18, facade);
    solid(.55, 3.225, 0, 1.1, 1.95, .18, facade, false);
    // The window is impassable even though the thin glass can be seen through.
    obstacles.push({ minX: -1.6, maxX: 0, minZ: -.1, maxZ: .1 });
    const glass = material('glass', '#b2c5bd', { transparent: true, opacity: .24, roughness: .18, metalness: .12, depthWrite: false });
    box(-.8, 1.66, 0, .8, 1.28, .025, glass).castShadow = false;
    for (const x of [-1.21, -.39]) box(x, 1.66, 0, .045, 1.35, .12, doorMetal);
    for (const y of [1.01, 2.31]) box(-.8, y, 0, .86, .045, .12, doorMetal);
    for (let i = 0; i < 8; i++) box(-.8, 1.09 + i * .16, .025, .8, .025, .035, chrome);
    box(-.8, 1.66, .025, .025, 1.25, .035, chrome);
    // Front inside tile patches below the window, beside the door and across the lintel.
    surface(-.8, .49, -.096, 1.6, .98, Math.PI, tileTexture, 2.67, 1.63);
    surface(1.35, .66, -.096, .5, 1.32, Math.PI, tileTexture, .83, 2.2);
    surface(1.35, 1.36, -.099, .5, .09, Math.PI, borderTexture, .6);
    surface(-1.4, 1.36, -.099, .4, .09, Math.PI, borderTexture, .48);
    surface(-.2, 1.36, -.099, .4, .09, Math.PI, borderTexture, .48);

    const door = new THREE.Group(); door.name = 'a101-front-door'; world.add(door);
    const doorFrame = material('doorFrame', '#6e786f', { metalness: .45, roughness: .5 });
    box(.55, .43, 0, 1.05, .82, .055, doorMetal, door);
    box(.55, .43, -.035, .86, .63, .018, doorFrame, door);
    box(.55, .43, .035, .86, .63, .018, doorFrame, door);
    for (const x of [.026, 1.074]) box(x, 1.12, 0, .052, 2.24, .07, doorFrame, door);
    for (const y of [.025, .86, 2.215]) box(.55, y, 0, 1.1, .055, .07, doorFrame, door);
    const doorGlass = box(.55, 1.53, 0, .99, 1.3, .02, glass, door); doorGlass.castShadow = false;
    for (let i = 0; i < 8; i++) box(.55, .93 + i * .17, .022, 1.02, .035, .035, doorMetal, door);
    box(.96, 1.03, .065, .035, .16, .035, chrome, door);
    box(.96, 1.03, -.065, .035, .16, .035, chrome, door);
    for (const x of [-.035, 1.135]) box(x, 1.15, 0, .06, 2.3, .15, doorFrame);
    box(.55, 2.29, 0, 1.23, .06, .15, doorFrame);
    box(.55, .025, .02, 1.1, .05, .22, cream);
    sign('A101', 'TÒA NHÀ AN TÂM', .55, 2.65, .105, .67, .34);
    box(.55, 2.69, -.11, .48, .13, .03, material('ventDark', '#6b6f60'));
    for (let i = 0; i < 5; i++) box(.55, 2.637 + i * .026, -.13, .48, .01, .025, doorMetal);
    const glow = material('fixtureGlow', '#fffde3', { emissive: '#fff7cd', emissiveIntensity: .65, roughness: .4 });
    box(-.25, 3.3, -.12, 1.65, .1, .09, chrome);
    box(-.25, 3.3, -.182, 1.51, .055, .055, glow);
    box(-.15, 1.08, -.126, .18, .13, .045, porcelain);
    for (const x of [-.2, -.12]) box(x, 1.08, -.152, .04, .045, .006, cream);

    // The black steel mezzanine is the room's strongest visual landmark.
    solid(0, 2.24, -4.7, 3.2, .13, 3.8, cream, false);
    for (const z of [-2.8, -3.7, -4.6, -5.5, -6.4]) box(0, 2.13, z, 3.2, .12, .075, iron);
    for (const x of [-1.55, 1.55]) box(x, 2.12, -4.7, .1, .15, 3.85, iron);
    // Leave the left ladder access clear at the balustrade.
    box(.3, 3.12, -2.8, 2.6, .065, .065, iron);
    box(.3, 2.33, -2.8, 2.6, .065, .065, iron);
    for (let i = 0; i <= 12; i++) box(-1 + i * (2.6 / 12), 2.725, -2.8, .033, .79, .033, iron);
    for (const x of [-1, 1.57]) box(x, 2.7, -2.8, .065, .9, .065, iron);
    // Shallow upper-room detail gives the loft depth without inventing furniture.
    box(0, 3.85, -5.45, 3.2, .1, .1, plaster);
    box(.85, 3.48, -6.57, 1.08, .29, .07, cream);
    for (let i = 0; i < 4; i++) box(.85, 3.385 + i * .04, -6.526, .93, .012, .01, doorMetal);
    box(-1.59, 3.04, -3.55, .015, .43, .43, material('loftVent', '#aeb0a2'));
    for (const x of [-1.53, -.99]) rod([x, .05, -1.27], [x, 2.3, -2.95], .032, iron);
    for (let i = 0; i < 8; i++) {
        const amount = (i + .35) / 8;
        box(-1.26, .05 + amount * 2.25, -1.27 - amount * 1.68, .62, .055, .17, iron);
    }
    obstacles.push({ minX: -1.6, maxX: -.88, minZ: -3.05, maxZ: -1.17 });
    // Ladder braces and a small magazine on one tread, as visible in the photo.
    rod([-1.57, 2.06, -2.8], [-1.57, 1.84, -2.5], .018, iron);
    const magazine = box(-1.3, 1.63, -2.43, .27, .035, .22, porcelain);
    magazine.rotation.x = -.55;

    // Back service area: tiled step, sink on the left, translucent shower door right.
    solid(0, .075, -5.85, 3.15, .15, 1.5, cream, false);
    solid(-.25, 1.07, -5.6, .13, 2.04, 1.85, plaster);
    solid(.26, 1.06, -5.35, .9, 2.02, .1, plaster);
    surface(.26, .7, -5.292, .9, 1.27, 0, tileTexture, 1.5, 2.1);
    surface(.26, 1.37, -5.289, .9, .08, 0, borderTexture, 1.1);
    box(.95, 1.13, -5.35, .035, 1.97, .055, cream);
    box(1.52, 1.13, -5.35, .035, 1.97, .055, cream);
    box(1.235, 2.1, -5.35, .61, .055, .055, cream);
    box(1.235, 1.13, -5.35, .54, 1.87, .025, material('showerGlass', '#d0d9c4', { transparent: true, opacity: .42, roughness: .35, depthWrite: false })).castShadow = false;
    box(1.43, 1.14, -5.29, .02, .19, .025, chrome);
    obstacles.push({ minX: .68, maxX: 1.6, minZ: -5.48, maxZ: -5.24 });
    rod([.77, 1.08, -6.54], [.77, 1.94, -6.54], .012, chrome);
    rod([.77, 1.94, -6.54], [.77, 1.94, -6.38], .012, chrome);
    const showerHead = cylinder(.77, 1.91, -6.38, .07, .022, iron); showerHead.rotation.x = .3;
    // A simple sink basin and pipework stay within the compact rear alcove.
    solid(-1.06, .86, -5.89, .91, .11, .63, material('counter', '#b7b9a9'));
    for (const x of [-1.44, -.68]) box(x, .46, -5.9, .08, .76, .49, cream);
    box(-1.07, .926, -5.9, .6, .025, .4, chrome);
    box(-1.07, .944, -5.9, .48, .026, .3, material('sinkBasin', '#7d8b85', { metalness: .5, roughness: .36 }));
    rod([-1.05, .92, -6.13], [-1.05, 1.17, -6.13], .018, chrome);
    rod([-1.05, 1.17, -6.13], [-1.05, 1.17, -5.99], .018, chrome);
    box(-.6, 2.09, -5.9, .9, .035, .08, glow);

    // Three-tier black shelf and white planter in front of the rear partition.
    const shelfX = -.05, shelfZ = -4.78;
    for (const x of [shelfX - .56, shelfX + .56]) {
        for (const z of [shelfZ - .27, shelfZ + .27]) box(x, .56, z, .035, 1.12, .035, shelfMetal);
    }
    for (const y of [.12, .56, 1.03]) {
        box(shelfX, y, shelfZ, 1.16, .035, .57, shelfMetal);
        for (const z of [shelfZ - .28, shelfZ + .28]) box(shelfX, y + .025, z, 1.16, .035, .027, iron);
    }
    obstacles.push({ minX: shelfX - .6, maxX: shelfX + .6, minZ: shelfZ - .31, maxZ: shelfZ + .31 });
    plant(-.37, 1.048, -4.79, .82);
    const book = box(.25, 1.058, -4.67, .3, .025, .22, porcelain); book.rotation.y = -.24;
    const page = box(.29, 1.075, -4.66, .13, .005, .19, material('bookPage', '#d2d5be')); page.rotation.y = -.24;
    const rug = new THREE.Mesh(new THREE.CircleGeometry(.55, 64), new THREE.MeshStandardMaterial({ map: rugTexture, roughness: 1 }));
    rug.rotation.x = -Math.PI / 2; rug.position.set(.92, .013, -1.66); rug.receiveShadow = true; world.add(rug);

    function floralPicture(x, y, z, background, blossom, rotation = 0) {
        const texture = canvasTexture(256, 384, (ctx, w, h) => {
            ctx.fillStyle = background; ctx.fillRect(0, 0, w, h);
            ctx.strokeStyle = '#64755d'; ctx.lineWidth = 5;
            ctx.beginPath(); ctx.moveTo(w * .51, h * .87); ctx.quadraticCurveTo(w * .4, h * .54, w * .55, h * .33); ctx.stroke();
            for (let i = 0; i < 18; i++) {
                const angle = i * 2.4, radius = 7 + (i % 5) * 10;
                ctx.fillStyle = blossom;
                ctx.beginPath(); ctx.ellipse(w * .55 + Math.cos(angle) * radius, h * .33 + Math.sin(angle) * radius, 18, 25, angle, 0, Math.PI * 2); ctx.fill();
            }
            ctx.fillStyle = '#e6c782'; ctx.beginPath(); ctx.arc(w * .55, h * .33, 9, 0, Math.PI * 2); ctx.fill();
        });
        const frame = box(x, y, z, .43, .64, .028, iron); frame.rotation.y = rotation;
        surface(x + Math.sin(rotation) * .018, y, z + Math.cos(rotation) * .018, .397, .607, rotation, texture, 1);
    }
    floralPicture(-.45, 1.77, -5.276, '#f4e6de', '#c97e8a');
    floralPicture(.07, 1.77, -5.276, '#a7c3bc', '#e4ded2');
    floralPicture(-1.568, 1.88, -4.75, '#e4e9df', '#d9a587', Math.PI / 2);
    floralPicture(-1.568, 1.88, -5.25, '#f0e6d8', '#b66b4d', Math.PI / 2);

    // Quiet, sunlit landing outside. All exterior detail is an illustrative setting.
    if (includeLanding) {
    const landingTexture = tileTexture.clone(); landingTexture.needsUpdate = true; landingTexture.repeat.set(9, 4.5);
    const landingMaterial = new THREE.MeshStandardMaterial({ color: '#e4d4b8', map: landingTexture, roughness: .86 });
    solid(0, -.085, 1.85, 7.2, .16, 3.7, landingMaterial, false);
    solid(-2.6, 2.1, -.03, 1.8, 4.2, .24, facade);
    solid(2.6, 2.1, -.03, 1.8, 4.2, .24, facade);
    for (const x of [-3.4, 3.4]) solid(x, 1.95, .15, .18, 3.9, .5, material('column', '#d7c8ae'));
    box(0, 3.74, .19, 7, .19, .48, cream);
    box(0, 3.9, .2, 7.2, .12, .74, wood);
    box(-2.6, 1.1, .115, .94, 2.2, .035, material('neighborDoor', '#a0a58f'));
    for (const x of [-3.1, -2.1]) box(x, 1.12, .15, .045, 2.25, .06, cream);
    box(-2.6, 2.24, .15, 1.04, .045, .06, cream);
    box(-2.24, 1.03, .17, .028, .14, .025, chrome);
    sign('A102', 'TÒA NHÀ AN TÂM', -2.6, 2.57, .14, .52, .27);
    plant(2.35, 0, .55, 1.35, material('terracotta', '#b18a66'));
    plant(-3.06, 0, .78, 1.1, material('stonePot', '#c2bba4'));
    obstacles.push({ minX: 2.08, maxX: 2.62, minZ: .28, maxZ: .82 });
    obstacles.push({ minX: -3.29, maxX: -2.83, minZ: .55, maxZ: 1.01 });
    // Low parapet leaves the follow camera's view into the room unobstructed.
    solid(0, .12, 3.61, 7.1, .24, .14, facade);
    }

    return {
        obstacles,
        cameraObstacles,
        door,
        spawn: { x: .55, y: 0, z: 2.4 },
        bounds: { minX: -3.3, maxX: 3.3, minZ: -6.45, maxZ: 3.4 },
        roomBounds: { minX: -1.6, maxX: 1.6, minZ: -6.6, maxZ: 0 },
        landmarks: [
            { position: { x: .55, y: 1.3, z: .25 }, label: 'Cửa phòng A101' },
            { position: { x: -1.2, y: 1.2, z: -2.1 }, label: 'Thang lên gác lửng' },
            { position: { x: 0, y: 2.5, z: -3.4 }, label: 'Gác lửng' },
            { position: { x: -1.05, y: 1.1, z: -5.65 }, label: 'Khu rửa' },
            { position: { x: 1.2, y: 1.2, z: -5.2 }, label: 'Khu vệ sinh' },
        ],
    };
}
