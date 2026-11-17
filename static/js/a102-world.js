/* A102: an illustrative reconstruction of the supplied room and mezzanine photos. */
export function buildA102World(THREE, scene, { offsetX = -3.6 } = {}) {
    const world = new THREE.Group();
    world.name = 'a102-room-world';
    world.position.x = offsetX;
    scene.add(world);
    const obstacles = [], cameraObstacles = [];
    const unitBox = new THREE.BoxGeometry(1, 1, 1);
    const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 16);
    const unitSphere = new THREE.SphereGeometry(1, 14, 10);
    const materials = new Map();
    let seed = 102;
    const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    const material = (name, color, extra = {}) => {
        if (!materials.has(name)) materials.set(name, new THREE.MeshStandardMaterial({ color, roughness: .76, ...extra }));
        return materials.get(name);
    };
    const white = material('white', '#f2f1e9');
    const porcelain = material('porcelain', '#f8f8f0', { roughness: .25 });
    const steel = material('steel', '#292e2b', { metalness: .5, roughness: .46 });
    const chrome = material('chrome', '#b8bdb8', { metalness: .8, roughness: .28 });
    const mint = material('mint', '#c9dfd8');
    const facade = material('facade', '#e7dfcf');
    const cream = material('cream', '#e8e4d5');
    const doorMetal = material('doorMetal', '#818b82', { metalness: .4, roughness: .55 });
    const glow = material('glow', '#fff5d2', { emissive: '#fff0bd', emissiveIntensity: .7, roughness: .4 });

    function texture(width, height, draw) {
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
        draw(canvas.getContext('2d'), width, height);
        const map = new THREE.CanvasTexture(canvas);
        map.colorSpace = THREE.SRGBColorSpace;
        map.wrapS = map.wrapT = THREE.RepeatWrapping;
        map.anisotropy = 4;
        return map;
    }
    const tileTexture = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#efeee8'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 45; i++) {
            const x = random() * w, y = random() * h;
            ctx.strokeStyle = `rgba(172,171,157,${.02 + random() * .055})`; ctx.lineWidth = 1 + random() * 2;
            ctx.beginPath(); ctx.moveTo(x, y); ctx.bezierCurveTo(x + 25, y - 65, x + 95, y + 45, x + 160, y - 80); ctx.stroke();
        }
        ctx.strokeStyle = '#bfc0b7'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, w, h);
        ctx.strokeStyle = '#f7f7ef'; ctx.lineWidth = 2; ctx.strokeRect(3, 3, w - 6, h - 6);
    });
    const wallTexture = texture(512, 256, (ctx, w, h) => {
        ctx.fillStyle = '#f3f3ec'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#dcddd5'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, w, h);
        ctx.strokeStyle = '#fafaf5'; ctx.lineWidth = 2; ctx.strokeRect(3, 3, w - 6, h - 6);
    });
    function woodTexture(pale = false) {
        return texture(512, 1024, (ctx, w, h) => {
            for (let plank = 0; plank < 4; plank++) {
                const x = plank * w / 4, tone = Math.round(random() * 12);
                ctx.fillStyle = pale ? `rgb(${214 + tone},${200 + tone},${175 + tone})` : `rgb(${186 + tone},${143 + tone},${84 + tone})`;
                ctx.fillRect(x, 0, w / 4, h);
                for (let grain = 0; grain < 44; grain++) {
                    const start = x + random() * w / 4;
                    ctx.strokeStyle = pale ? 'rgba(126,105,77,.11)' : 'rgba(110,72,31,.17)';
                    ctx.lineWidth = .5 + random() * 1.5;
                    ctx.beginPath(); ctx.moveTo(start, 0);
                    ctx.bezierCurveTo(start - 6, h * .25, start + 9, h * .6, start + 2, h); ctx.stroke();
                }
                if (!pale) {
                    ctx.strokeStyle = 'rgba(104,69,31,.25)'; ctx.lineWidth = 1;
                    for (let ring = 1; ring < 5; ring++) {
                        ctx.beginPath(); ctx.ellipse(x + w / 9, h * .38, ring * 2, ring * 12, -.08, 0, Math.PI * 2); ctx.stroke();
                    }
                }
                ctx.fillStyle = pale ? 'rgba(141,127,100,.1)' : 'rgba(111,77,37,.22)'; ctx.fillRect(x, 0, 1, h);
            }
        });
    }
    const warmWoodMap = woodTexture(), paleWoodMap = woodTexture(true);
    const warmWood = material('warmWood', '#ffffff', { map: warmWoodMap, roughness: .58 });
    const paleWood = material('paleWood', '#ffffff', { map: paleWoodMap, roughness: .67 });
    const curtainTexture = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#e9e7d8'; ctx.fillRect(0, 0, w, h);
        for (let y = 24; y < h; y += 59) {
            for (let x = 22; x < w; x += 57) {
                const px = x + (Math.round(y / 59) % 2) * 13;
                ctx.strokeStyle = '#7d8570'; ctx.lineWidth = 2;
                ctx.beginPath(); ctx.moveTo(px, y + 16); ctx.lineTo(px + 8, y - 8); ctx.stroke();
                for (let leaf = 0; leaf < 4; leaf++) {
                    ctx.fillStyle = leaf % 2 ? '#a6a898' : '#858c78';
                    ctx.beginPath(); ctx.ellipse(px + (leaf % 2 ? 8 : -1), y - leaf * 3, 7, 3, leaf % 2 ? -.7 : .6, 0, Math.PI * 2); ctx.fill();
                }
                ctx.fillStyle = '#f8f6ed'; ctx.beginPath(); ctx.arc(px + 8, y - 10, 7, 0, Math.PI * 2); ctx.fill();
                ctx.fillStyle = '#b4b392'; ctx.beginPath(); ctx.arc(px + 8, y - 10, 2, 0, Math.PI * 2); ctx.fill();
            }
        }
    });
    const quiltTexture = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#8b8b87'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#a8a8a0'; ctx.lineWidth = 2;
        for (let i = -w; i < w * 2; i += 64) {
            ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + w, h); ctx.moveTo(i, 0); ctx.lineTo(i - w, h); ctx.stroke();
        }
        for (let i = 0; i < 1700; i++) {
            ctx.fillStyle = random() > .5 ? 'rgba(255,255,255,.055)' : 'rgba(30,30,25,.045)';
            ctx.fillRect(random() * w, random() * h, 1, 5);
        }
    });
    function mesh(geometry, mat, x, y, z, sx = 1, sy = 1, sz = 1, parent = world) {
        const item = new THREE.Mesh(geometry, mat);
        item.position.set(x, y, z); item.scale.set(sx, sy, sz);
        item.castShadow = true; item.receiveShadow = true; parent.add(item); return item;
    }
    const box = (x, y, z, width, height, depth, mat, parent = world) => mesh(unitBox, mat, x, y, z, width, height, depth, parent);
    const cylinder = (x, y, z, radius, height, mat, parent = world) => mesh(unitCylinder, mat, x, y, z, radius, height, radius, parent);
    function obstacle(x, z, width, depth) {
        obstacles.push({ minX: offsetX + x - width / 2, maxX: offsetX + x + width / 2, minZ: z - depth / 2, maxZ: z + depth / 2 });
    }
    function solid(x, y, z, width, height, depth, mat, collidable = true) {
        const item = box(x, y, z, width, height, depth, mat);
        cameraObstacles.push(item); if (collidable) obstacle(x, z, width, depth); return item;
    }
    function surface(x, y, z, width, height, rotation, map, repeatX = 1, repeatY = 1, extra = {}) {
        const clone = map.clone(); clone.needsUpdate = true; clone.repeat.set(repeatX, repeatY);
        const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshStandardMaterial({ map: clone, roughness: .7, ...extra }));
        item.position.set(x, y, z); item.rotation.y = rotation; item.receiveShadow = true; world.add(item); return item;
    }
    function rod(from, to, radius, mat = steel, parent = world) {
        const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to), center = a.clone().add(b).multiplyScalar(.5);
        const item = cylinder(center.x, center.y, center.z, radius, a.distanceTo(b), mat, parent);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize()); return item;
    }
    function pleatedCurtain(x, y, z, width, height, map, rotation = 0, repeat = 1) {
        const geometry = new THREE.PlaneGeometry(width, height, 48, 1);
        const positions = geometry.attributes.position;
        for (let i = 0; i < positions.count; i++) positions.setZ(i, Math.sin((positions.getX(i) / width + .5) * Math.PI * 20) * .023);
        geometry.computeVertexNormals();
        const clone = map.clone(); clone.needsUpdate = true; clone.repeat.set(repeat, repeat);
        const item = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: clone, roughness: 1, side: THREE.DoubleSide }));
        item.position.set(x, y, z); item.rotation.y = rotation; item.castShadow = true; item.receiveShadow = true; world.add(item); return item;
    }
    function plant(x, y, z, size = 1) {
        const group = new THREE.Group(); group.position.set(x, y, z); group.scale.setScalar(size); world.add(group);
        mesh(new THREE.CylinderGeometry(.12, .09, .23, 16), porcelain, 0, .115, 0, 1, 1, 1, group);
        cylinder(0, .232, 0, .104, .008, material('soil', '#574c37'), group);
        const leaves = material('leaf', '#66804d');
        rod([0, .22, 0], [.04, .82, 0], .009, leaves, group);
        for (let i = 0; i < 10; i++) {
            const angle = i * 2.4, radius = .15, h = .3 + i * .046;
            const x = Math.cos(angle) * radius, z = Math.sin(angle) * radius;
            rod([0, h, 0], [x, h + .05, z], .005, leaves, group);
            const item = mesh(unitSphere, leaves, x, h + .06, z, .095, .018, .045, group); item.rotation.y = -angle;
        }
        return group;
    }

    // White tiled room, 3.4 m across. A102 uses plain ceramic tiles, without A101's floral stripe.
    solid(0, -.08, -3.3, 3.76, .16, 6.92, cream, false);
    const floor = surface(0, .006, -3.3, 3.4, 6.6, 0, tileTexture, 3.4 / .6, 11, { roughness: .32 });
    floor.rotation.x = -Math.PI / 2; cameraObstacles.push(floor);
    solid(-1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(1.79, 2.25, -3.3, .18, 4.5, 6.8, white);
    solid(0, 2.25, -6.69, 3.76, 4.5, .18, white);
    solid(0, 4.56, -3.3, 3.76, .12, 6.8, white, false);
    surface(-1.694, 1.03, -3.3, 6.6, 2.06, Math.PI / 2, wallTexture, 11, 6.86);
    surface(1.694, 1.03, -3.3, 6.6, 2.06, -Math.PI / 2, wallTexture, 11, 6.86);
    surface(0, 1.03, -6.594, 3.4, 2.06, 0, wallTexture, 5.66, 6.86);
    for (const x of [-1.682, 1.682]) box(x, .04, -3.3, .026, .08, 6.6, cream);
    // White structural band, visible along the left wall in the reference image.
    box(-1.65, 1.94, -3.8, .11, .15, 5.4, white);
    box(-1.675, 1.68, -1.94, .025, .095, .7, chrome);
    for (let i = 0; i < 5; i++) rod([-1.65, 1.7, -2.2 + i * .13], [-1.615, 1.66, -2.2 + i * .13], .009, steel);

    // Entry uses the same apartment-building style; the supplied photos show the back, not this facade.
    solid(-1.475, 2.25, 0, .45, 4.5, .18, facade);
    solid(-.225, 2.25, 0, .45, 4.5, .18, facade);
    solid(-.85, .51, 0, .8, 1.02, .18, facade);
    solid(-.85, 3.39, 0, .8, 2.22, .18, facade, false);
    solid(1.4, 2.25, 0, .6, 4.5, .18, facade);
    solid(.55, 3.375, 0, 1.1, 2.25, .18, facade, false);
    obstacle(-.85, 0, 1.7, .2);
    const glass = material('glass', '#becfc5', { transparent: true, opacity: .25, roughness: .2, depthWrite: false });
    box(-.85, 1.65, 0, .8, 1.26, .022, glass).castShadow = false;
    for (const x of [-1.27, -.43]) box(x, 1.65, 0, .045, 1.34, .12, doorMetal);
    for (const y of [1.01, 2.3]) box(-.85, y, 0, .88, .045, .12, doorMetal);
    for (let i = 0; i < 8; i++) box(-.85, 1.1 + i * .16, .025, .8, .025, .035, chrome);
    box(-.85, 1.65, .025, .025, 1.26, .035, chrome);
    surface(-.85, .49, -.096, 1.7, .98, Math.PI, wallTexture, 2.83, 3.26);
    surface(1.4, 1.03, -.096, .6, 2.06, Math.PI, wallTexture, 1, 6.86);
    const door = new THREE.Group(); door.name = 'a102-front-door'; world.add(door);
    box(.55, .43, 0, 1.05, .82, .055, doorMetal, door);
    box(.55, .43, .035, .86, .63, .018, material('doorInset', '#748075'), door);
    box(.55, .43, -.035, .86, .63, .018, material('doorInset', '#748075'), door);
    for (const x of [.026, 1.074]) box(x, 1.12, 0, .052, 2.24, .07, doorMetal, door);
    for (const y of [.025, .86, 2.215]) box(.55, y, 0, 1.1, .055, .07, doorMetal, door);
    box(.55, 1.53, 0, .99, 1.3, .02, glass, door).castShadow = false;
    for (let i = 0; i < 8; i++) box(.55, .93 + i * .17, .022, 1.02, .035, .035, doorMetal, door);
    for (const z of [-.065, .065]) box(.96, 1.03, z, .035, .16, .035, chrome, door);
    for (const x of [-.035, 1.135]) box(x, 1.15, 0, .06, 2.3, .15, doorMetal);
    box(.55, 2.29, 0, 1.23, .06, .15, doorMetal);
    box(.55, .025, .02, 1.1, .05, .22, cream);
    const signTexture = texture(768, 384, (ctx, w, h) => {
        ctx.fillStyle = '#b98851'; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#3e4840'; ctx.fillRect(9, 9, w - 18, h - 18);
        ctx.textAlign = 'center'; ctx.fillStyle = '#fff7de'; ctx.font = '600 146px Segoe UI, sans-serif'; ctx.fillText('A102', w / 2, 204);
        ctx.fillStyle = '#dfd3b5'; ctx.font = '34px Segoe UI, sans-serif'; ctx.fillText('TÒA NHÀ AN TÂM', w / 2, 295);
    });
    box(.55, 2.65, .105, .69, .36, .025, warmWood);
    surface(.55, 2.65, .122, .67, .34, 0, signTexture);
    box(-.25, 3.3, -.12, 1.65, .1, .09, chrome);
    box(-.25, 3.3, -.182, 1.51, .055, .055, glow);

    // Warm wood loft with white support beams and black horizontal balustrade.
    solid(0, 2.30, -4.7, 3.4, .14, 3.8, warmWood, false);
    const loftTop = surface(0, 2.376, -4.7, 3.4, 3.8, 0, warmWoodMap, 3, 2, { roughness: .57 }); loftTop.rotation.x = -Math.PI / 2;
    const loftBottom = surface(0, 2.224, -4.7, 3.4, 3.8, 0, warmWoodMap, 3, 2, { roughness: .64 }); loftBottom.rotation.x = Math.PI / 2;
    for (const z of [-2.85, -3.86, -4.9, -5.93]) box(0, 2.16, z, 3.4, .12, .075, white);
    // The ladder comes up on the left, leaving the forward side of the loft open.
    for (const y of [2.45, 2.65, 2.85, 3.05, 3.25]) box(.36, y, -2.8, 2.65, .032, .035, steel);
    for (const x of [-.965, .38, 1.685]) box(x, 2.85, -2.8, .045, .86, .045, steel);
    for (const x of [-.965, .38]) {
        box(x + .07, 2.85, -2.8, .025, .56, .05, steel);
        for (const y of [2.57, 3.13]) box(x + .035, y, -2.8, .095, .025, .05, steel);
    }
    for (const x of [-1.58, -.99]) {
        const side = box(x, 1.2, -2.02, .07, 2.86, .09, steel);
        side.rotation.x = -.635;
    }
    for (let i = 0; i < 8; i++) {
        const amount = (i + .3) / 8;
        box(-1.285, .06 + amount * 2.31, -1.17 - amount * 1.7, .59, .05, .19, warmWood);
        box(-1.285, .035 + amount * 2.31, -1.17 - amount * 1.7, .63, .028, .14, steel);
    }
    obstacle(-1.285, -2.02, .75, 1.94);

    // Back left bathroom, with an open doorway and the fittings visible in the video.
    solid(-.79, 1.1, -5.86, .11, 2.2, 1.48, white);
    solid(-1.64, 1.1, -5.16, .12, 2.2, .12, white);
    solid(-.86, 1.1, -5.16, .1, 2.2, .12, white);
    solid(-1.25, 2.115, -5.16, .9, .17, .12, white, false);
    surface(-.855, 1.02, -5.86, 1.48, 2.04, -Math.PI / 2, wallTexture, 2.46, 6.8);
    const bathroomDoor = box(-.875, 1.04, -5.57, .035, 2.02, .75, white);
    cameraObstacles.push(bathroomDoor); obstacle(-.875, -5.57, .035, .75);
    box(-.845, 1.04, -5.8, .025, .14, .025, chrome);
    const toiletGroup = new THREE.Group(); toiletGroup.position.set(-1.24, 0, -6.16); world.add(toiletGroup);
    mesh(unitSphere, porcelain, 0, .35, .08, .24, .13, .31, toiletGroup);
    mesh(unitSphere, porcelain, 0, .19, .01, .14, .19, .18, toiletGroup);
    box(0, .57, -.17, .42, .43, .14, porcelain, toiletGroup);
    box(0, .797, -.17, .45, .025, .17, porcelain, toiletGroup);
    const toiletSeat = mesh(new THREE.TorusGeometry(.145, .023, 8, 24), porcelain, 0, .465, .1, 1, 1.22, 1, toiletGroup); toiletSeat.rotation.x = -Math.PI / 2;
    obstacle(-1.24, -6.1, .48, .66);
    rod([-1.67, 1.02, -5.78], [-1.67, 1.89, -5.78], .011, chrome);
    rod([-1.67, 1.89, -5.78], [-1.48, 1.89, -5.78], .011, chrome);
    cylinder(-1.48, 1.875, -5.78, .06, .016, chrome);
    box(-1.665, 1.03, -5.78, .035, .055, .17, chrome);
    const hoseCurve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(-1.66, 1.05, -5.76), new THREE.Vector3(-1.58, .26, -5.6), new THREE.Vector3(-1.66, 1.61, -5.61));
    mesh(new THREE.TubeGeometry(hoseCurve, 18, .007, 6, false), chrome, 0, 0, 0);

    // Mint kitchen wall, bright barred window and black shelves over the sink.
    box(-.3, 1.84, -6.58, .88, .8, .02, mint);
    const windowGlow = material('windowGlow', '#eef5e9', { emissive: '#dceadb', emissiveIntensity: .35, roughness: .2 });
    box(-.3, 1.63, -6.553, .76, .56, .025, windowGlow);
    for (const x of [-.7, .1]) box(x, 1.63, -6.53, .035, .62, .035, white);
    for (const y of [1.32, 1.94]) box(-.3, y, -6.53, .84, .035, .035, white);
    for (let i = 0; i < 4; i++) box(-.3, 1.39 + i * .15, -6.51, .77, .017, .017, chrome);
    solid(-.3, .87, -6.04, .9, .09, .74, material('counterStone', '#a9aa99', { roughness: .42 }));
    for (const x of [-.71, .11]) box(x, .44, -6.05, .075, .8, .62, white);
    box(-.35, .924, -6.1, .49, .025, .37, chrome);
    box(-.35, .94, -6.1, .39, .027, .28, material('basin', '#7d8b83', { metalness: .5, roughness: .32 }));
    const faucetCurve = new THREE.CubicBezierCurve3(new THREE.Vector3(-.42, .94, -6.34), new THREE.Vector3(-.42, 1.39, -6.34), new THREE.Vector3(-.42, 1.4, -6.1), new THREE.Vector3(-.42, 1.15, -6.1));
    mesh(new THREE.TubeGeometry(faucetCurve, 18, .014, 8, false), chrome, 0, 0, 0);
    pleatedCurtain(-.3, .43, -5.657, .87, .78, curtainTexture);
    obstacle(-.3, -6.04, .9, .74);
    for (const x of [-.75, .13]) box(x, 1.5, -6.31, .025, .66, .025, steel);
    for (const y of [1.31, 1.66]) {
        for (const z of [-6.5, -6.16]) box(-.31, y, z, .92, .024, .024, steel);
        for (let i = 0; i < 9; i++) box(-.71 + i * .1, y, -6.33, .014, .018, .34, steel);
    }
    box(-.31, 1.78, -6.31, .92, .023, .023, steel);
    // A small utensil holder and a pale wooden chopping board.
    cylinder(.035, 1.008, -6.2, .055, .18, cream);
    for (let i = 0; i < 3; i++) rod([.01 + i * .025, 1.02, -6.2], [.01 + i * .025, 1.23, -6.19], .008, warmWood);
    box(.07, 1.0, -6.45, .13, .21, .025, paleWood);

    // Distinctive silver refrigerator and pale oak wardrobe on the back right.
    const fridge = material('fridge', '#929995', { metalness: .57, roughness: .4 });
    solid(.49, .82, -6.04, .58, 1.64, .68, material('fridgeSides', '#747c76', { metalness: .5, roughness: .48 }));
    box(.49, .553, -5.686, .55, 1.04, .045, fridge);
    box(.49, 1.371, -5.686, .55, .54, .045, fridge);
    box(.49, 1.105, -5.651, .54, .017, .013, steel);
    box(.26, .79, -5.635, .035, .34, .035, chrome);
    box(.26, 1.32, -5.635, .035, .27, .035, chrome);
    box(.49, .045, -5.685, .49, .035, .038, steel);
    const fridgeLabel = texture(256, 256, (ctx, w, h) => {
        ctx.fillStyle = '#e4eee2'; ctx.fillRect(0, 0, w, h); ctx.strokeStyle = '#50837c'; ctx.lineWidth = 12; ctx.strokeRect(0, 0, w, h);
        ctx.fillStyle = '#54827a'; ctx.font = 'bold 24px Segoe UI, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('INVERTER', w / 2, 49);
        ctx.fillStyle = '#82ad7a'; ctx.beginPath(); ctx.ellipse(130, 130, 51, 24, -.7, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#f1f5e7'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(95, 159); ctx.lineTo(163, 104); ctx.stroke();
        ctx.fillStyle = '#77918b'; ctx.font = '19px Segoe UI, sans-serif'; ctx.fillText('TIẾT KIỆM ĐIỆN', w / 2, 219);
    });
    surface(.51, .7, -5.659, .32, .35, 0, fridgeLabel);
    surface(.51, 1.4, -5.659, .3, .18, 0, fridgeLabel);
    solid(1.255, 1.065, -6.04, .88, 2.13, .69, paleWood);
    const seam = material('wardrobeSeam', '#a99e87');
    box(1.255, 1.075, -5.686, .013, 2.04, .008, seam);
    box(1.474, .45, -5.679, .42, .012, .01, seam);
    box(1.474, .78, -5.679, .42, .012, .01, seam);
    for (const x of [1.205, 1.305]) box(x, 1.46, -5.65, .018, .15, .033, chrome);
    for (const y of [.28, .61]) box(1.474, y, -5.65, .2, .018, .033, chrome);
    box(1.255, .045, -5.678, .88, .055, .045, chrome);
    const botanical = texture(256, 384, (ctx, w, h) => {
        ctx.fillStyle = '#f0efdf'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#75825a'; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(116, 331); ctx.lineTo(132, 85); ctx.stroke();
        for (let i = 0; i < 5; i++) {
            ctx.fillStyle = i % 2 ? '#71885c' : '#496d41'; ctx.beginPath(); ctx.ellipse(132 + i * 4, 235 - i * 25, 20, 73, .3 + i * .08, 0, Math.PI * 2); ctx.fill();
        }
        ctx.strokeStyle = '#c5a75b'; ctx.lineWidth = 7;
        for (let i = 0; i < 5; i++) { ctx.beginPath(); ctx.moveTo(126, 114); ctx.lineTo(91 + i * 15, 52 - Math.sin(i) * 15); ctx.stroke(); }
    });
    box(.42, 1.955, -6.565, .39, .49, .025, steel);
    surface(.42, 1.955, -6.546, .365, .463, 0, botanical);

    // The supplied loft photo shows a floor mattress, gray quilt, cream curtains and a reading lamp.
    solid(-.07, 2.435, -4.62, 2.38, .12, 1.72, material('mattress', '#e8e3d4'), false);
    const quiltMap = quiltTexture.clone(); quiltMap.needsUpdate = true; quiltMap.repeat.set(2, 2);
    const quilt = material('quilt', '#ffffff', { map: quiltMap, roughness: 1 });
    box(.23, 2.525, -4.62, 1.75, .11, 1.7, quilt);
    const quiltTopGeometry = new THREE.PlaneGeometry(1.75, 1.7, 24, 24);
    for (let i = 0; i < quiltTopGeometry.attributes.position.count; i++) {
        const positions = quiltTopGeometry.attributes.position, x = positions.getX(i), y = positions.getY(i);
        positions.setZ(i, .016 * Math.sin(x * 29) * Math.sin(y * 24) + .012 * Math.sin(y * 9 + x * 12));
    }
    quiltTopGeometry.computeVertexNormals();
    const quiltTop = mesh(quiltTopGeometry, quilt, .23, 2.586, -4.62); quiltTop.rotation.x = -Math.PI / 2;
    for (const z of [-4.2, -5.03]) {
        const pillow = mesh(unitSphere, material('pillow', '#9a9a96', { roughness: 1 }), -1.0, 2.59, z, .3, .105, .35); pillow.rotation.y = -.05;
    }
    // The curtains and lamp sit against the left wall, matching the second reference image.
    const curtainCreamMap = texture(256, 256, (ctx, w, h) => {
        ctx.fillStyle = '#ede7d0'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#c3ba96'; ctx.lineWidth = 2;
        for (let i = 0; i < 8; i++) { ctx.beginPath(); ctx.moveTo(i * 32, 0); ctx.lineTo(i * 32, h); ctx.stroke(); }
    });
    pleatedCurtain(-1.665, 3.35, -4.8, 1.85, 1.84, curtainCreamMap, Math.PI / 2, 2);
    rod([-1.6, 4.31, -5.8], [-1.6, 4.31, -3.8], .015, chrome);
    box(-1.535, 3.94, -3.8, .27, .32, .96, porcelain);
    box(-1.385, 3.84, -3.8, .025, .06, .83, material('acVent', '#747d71'));
    for (let i = 0; i < 3; i++) box(-1.368, 3.825 + i * .018, -3.8, .007, .006, .78, cream);
    cylinder(-1.2, 2.393, -3.35, .18, .035, steel);
    rod([-1.2, 2.41, -3.35], [-1.2, 3.65, -3.35], .014, steel);
    rod([-1.2, 3.65, -3.35], [-1.07, 3.7, -3.35], .012, steel);
    const shade = mesh(new THREE.ConeGeometry(.13, .15, 20, 1, true), material('lampShade', '#a68e65', { side: THREE.DoubleSide, metalness: .4, roughness: .5 }), -1.04, 3.63, -3.35);
    shade.rotation.z = -.17;
    mesh(unitSphere, glow, -1.025, 3.58, -3.35, .09, .035, .09);
    plant(-1.41, 2.38, -3.02, .7);
    box(-1.3, 2.414, -3.69, .35, .035, .24, material('bookCover', '#c6a07b'));
    box(-1.3, 2.443, -3.69, .32, .022, .22, cream);
    box(.76, 3.38, -6.57, 1.8, 1.98, .035, material('loftAccent', '#b8a88a'));

    return {
        group: world,
        obstacles,
        cameraObstacles,
        door,
        doorHinge: { x: offsetX, z: 0 },
        spawn: { x: offsetX + .55, y: 0, z: 2.4 },
        roomBounds: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: 0 },
        bounds: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: 3.4 },
        ceiling: { loftFrontZ: -2.8, undersideY: 2.22, roomHeight: 4.5 },
        landmarks: [
            { position: { x: offsetX + .55, y: 1.3, z: .25 }, label: 'Cửa phòng A102' },
            { position: { x: offsetX - 1.28, y: 1.2, z: -2.02 }, label: 'Thang lên gác gỗ' },
            { position: { x: offsetX - 1.2, y: 1.2, z: -5.0 }, label: 'Phòng tắm' },
            { position: { x: offsetX - .3, y: 1.1, z: -5.6 }, label: 'Khu bếp' },
            { position: { x: offsetX + 1.2, y: 1.2, z: -5.6 }, label: 'Tủ lạnh và tủ quần áo' },
        ],
    };
}
