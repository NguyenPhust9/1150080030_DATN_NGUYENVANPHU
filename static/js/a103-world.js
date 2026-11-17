/* A103: reconstructed from its two room photos and the supplied 10-second tour. */
export function buildA103World(THREE, scene, { offsetX = 3.6 } = {}) {
    const group = new THREE.Group();
    group.name = 'a103-room-world';
    group.position.x = offsetX;
    scene.add(group);
    const obstacles = [], cameraObstacles = [];
    const unitBox = new THREE.BoxGeometry(1, 1, 1);
    const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 16);
    const unitSphere = new THREE.SphereGeometry(1, 16, 10);
    const materials = new Map();
    let seed = 103;
    const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    function mat(name, color, extra = {}) {
        if (!materials.has(name)) materials.set(name, new THREE.MeshStandardMaterial({ color, roughness: .73, ...extra }));
        return materials.get(name);
    }
    const white = mat('white', '#f3f1eb');
    const porcelain = mat('porcelain', '#f5f6ee', { roughness: .3 });
    const iron = mat('iron', '#272d2b', { metalness: .48, roughness: .48 });
    const chrome = mat('chrome', '#bbc1bb', { metalness: .82, roughness: .28 });
    const facade = mat('facade', '#e7dfcf');
    const darkCeiling = mat('darkCeiling', '#363b3c');
    const glow = mat('glow', '#fffbe7', { emissive: '#fff4cd', emissiveIntensity: .8, roughness: .35 });
    function texture(width, height, draw) {
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
        draw(canvas.getContext('2d'), width, height);
        const result = new THREE.CanvasTexture(canvas);
        result.colorSpace = THREE.SRGBColorSpace;
        result.wrapS = result.wrapT = THREE.RepeatWrapping;
        result.anisotropy = 4;
        return result;
    }
    const floorMap = texture(1024, 1024, (ctx, w, h) => {
        ctx.fillStyle = '#d4d2c5'; ctx.fillRect(0, 0, w, h);
        const plankWidth = 128, plankLength = 512;
        for (let column = 0; column < 8; column++) {
            const stagger = column % 3 * plankLength / 3;
            for (let row = -1; row < 3; row++) {
                const x = column * plankWidth, y = row * plankLength + stagger, tone = Math.floor(random() * 23);
                ctx.fillStyle = `rgb(${132 + tone},${104 + tone},${79 + tone})`;
                ctx.fillRect(x + 1, y + 1, plankWidth - 2, plankLength - 2);
                ctx.save(); ctx.beginPath(); ctx.rect(x + 2, y + 2, plankWidth - 4, plankLength - 4); ctx.clip();
                for (let grain = 0; grain < 38; grain++) {
                    const start = x + random() * plankWidth;
                    ctx.strokeStyle = grain % 3 ? 'rgba(229,206,174,.23)' : 'rgba(66,45,29,.17)';
                    ctx.lineWidth = .5 + random() * 1.9;
                    ctx.beginPath(); ctx.moveTo(start, y);
                    ctx.bezierCurveTo(start + 12, y + 160, start - 15, y + 350, start + 4, y + plankLength); ctx.stroke();
                }
                for (let ring = 1; ring < 6; ring++) {
                    ctx.strokeStyle = 'rgba(73,51,33,.19)'; ctx.lineWidth = 1.4;
                    ctx.beginPath(); ctx.ellipse(x + 47, y + 240, ring * 3, ring * 16, -.04, 0, Math.PI * 2); ctx.stroke();
                }
                ctx.restore();
            }
        }
    });
    function marbleTexture(dark = false) {
        return texture(512, 512, (ctx, w, h) => {
            ctx.fillStyle = dark ? '#899792' : '#efefea'; ctx.fillRect(0, 0, w, h);
            for (let i = 0; i < (dark ? 55 : 23); i++) {
                const x = random() * w, y = random() * h;
                ctx.strokeStyle = dark ? `rgba(231,238,224,${.1 + random() * .2})` : `rgba(165,169,160,${.06 + random() * .08})`;
                ctx.lineWidth = .6 + random() * (dark ? 4 : 1.5);
                ctx.beginPath(); ctx.moveTo(x, y);
                ctx.bezierCurveTo(x + 55, y - 45, x + 92, y - 12, x + 180, y - 130); ctx.stroke();
            }
            ctx.strokeStyle = dark ? '#cbd1c4' : '#d7dbd0'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, w, h);
        });
    }
    const whiteMarbleMap = marbleTexture(), bathMarbleMap = marbleTexture(true);
    const woodMap = texture(512, 1024, (ctx, w, h) => {
        ctx.fillStyle = '#c39a6d'; ctx.fillRect(0, 0, w, h);
        for (let plank = 0; plank < 4; plank++) {
            const tone = Math.floor(random() * 15);
            ctx.fillStyle = `rgb(${185 + tone},${139 + tone},${91 + tone})`; ctx.fillRect(plank * 128, 0, 128, h);
            for (let i = 0; i < 43; i++) {
                const x = plank * 128 + random() * 128;
                ctx.strokeStyle = i % 2 ? 'rgba(239,199,151,.22)' : 'rgba(120,76,39,.16)'; ctx.lineWidth = .5 + random();
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.bezierCurveTo(x - 7, 250, x + 9, 750, x, h); ctx.stroke();
            }
            ctx.fillStyle = 'rgba(112,70,37,.13)'; ctx.fillRect(plank * 128, 0, 1, h);
        }
    });
    const stoneMap = texture(512, 512, (ctx, w, h) => {
        ctx.fillStyle = '#3e4240'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < 1900; i++) {
            ctx.fillStyle = i % 2 ? 'rgba(196,199,186,.11)' : 'rgba(16,22,19,.15)';
            const x = random() * w, y = random() * h;
            ctx.beginPath(); ctx.ellipse(x, y, 1 + random() * 5, 1 + random() * 2, random() * Math.PI, 0, Math.PI * 2); ctx.fill();
        }
        for (let i = 0; i < 12; i++) {
            const x = random() * w, y = random() * h; ctx.strokeStyle = 'rgba(211,214,203,.16)'; ctx.lineWidth = .7;
            ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 140, y - 56); ctx.stroke();
        }
    });
    const warmWood = mat('warmWood', '#ffffff', { map: woodMap, roughness: .57 });
    const cabinetWood = mat('cabinetWood', '#846044', { roughness: .68 });
    const stone = mat('stone', '#ffffff', { map: stoneMap, roughness: .36 });
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
        const item = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshStandardMaterial({ map: clone, roughness: .66, ...extra }));
        item.position.set(x, y, z); item.rotation.y = ry; item.receiveShadow = true; group.add(item); return item;
    }
    function rod(from, to, radius, material = chrome, parent = group) {
        const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to), center = a.clone().add(b).multiplyScalar(.5);
        const item = cylinder(center.x, center.y, center.z, radius, a.distanceTo(b), material, parent);
        item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize()); return item;
    }

    // Long brown ceramic planks, white marble lower walls and the dark ceiling distinguish A103.
    solid(0, -.08, -3.3, 3.76, .16, 6.92, cabinetWood, false);
    const floor = surface(0, .006, -3.3, 3.4, 6.6, 0, floorMap, 2, 3, { roughness: .49 });
    floor.rotation.x = -Math.PI / 2; cameraObstacles.push(floor);
    solid(-1.79, 2.2, -3.3, .18, 4.4, 6.8, white);
    solid(1.79, 2.2, -3.3, .18, 4.4, 6.8, white);
    solid(0, 2.2, -6.69, 3.76, 4.4, .18, white);
    solid(0, 4.46, -3.3, 3.76, .12, 6.8, darkCeiling, false);
    surface(-1.694, .73, -3.3, 6.6, 1.46, Math.PI / 2, whiteMarbleMap, 11, 2.43);
    surface(1.694, .73, -3.3, 6.6, 1.46, -Math.PI / 2, whiteMarbleMap, 11, 2.43);
    surface(0, .73, -6.594, 3.4, 1.46, 0, whiteMarbleMap, 5.67, 2.43);
    for (const x of [-1.682, 1.682]) box(x, .065, -3.3, .025, .13, 6.6, cabinetWood);
    for (const x of [-1.62, 1.62]) box(x, 4.22, -3.3, .16, .15, 6.6, white);
    box(0, 4.38, -1.25, .4, .025, .4, porcelain);
    box(0, 4.36, -1.25, .33, .012, .33, glow);
    // The left-wall air conditioner is above the staircase, as seen in the video.
    solid(-1.55, 3.72, -1.3, .25, .32, .92, porcelain);
    box(-1.411, 3.62, -1.3, .023, .052, .81, iron);
    for (let i = 0; i < 3; i++) box(-1.395, 3.607 + i * .018, -1.3, .006, .005, .78, white);

    // The interior video shows a dark metal entry frame. The outside follows the shared building.
    solid(-1.475, 2.2, 0, .45, 4.4, .18, facade);
    solid(-.225, 2.2, 0, .45, 4.4, .18, facade);
    solid(-.85, .51, 0, .8, 1.02, .18, facade);
    solid(-.85, 3.34, 0, .8, 2.12, .18, facade, false);
    solid(1.4, 2.2, 0, .6, 4.4, .18, facade);
    solid(.55, 3.325, 0, 1.1, 2.15, .18, facade, false);
    obstacle(-.85, 0, 1.7, .2, 0, 2.3);
    const glass = mat('glass', '#c7d4cc', { transparent: true, opacity: .2, roughness: .2, depthWrite: false });
    box(-.85, 1.65, 0, .8, 1.26, .025, glass).castShadow = false;
    for (const x of [-1.27, -.43]) box(x, 1.65, 0, .045, 1.34, .1, iron);
    for (const y of [1.01, 2.3]) box(-.85, y, 0, .88, .045, .1, iron);
    for (let i = 0; i < 8; i++) box(-.85, 1.1 + i * .16, .025, .8, .021, .026, iron);
    surface(-.85, .49, -.096, 1.7, .98, Math.PI, whiteMarbleMap, 2.83, 1.63);
    surface(1.4, .73, -.096, .6, 1.46, Math.PI, whiteMarbleMap, 1, 2.43);
    const door = new THREE.Group(); door.name = 'a103-front-door'; group.add(door);
    for (const x of [.028, 1.072]) box(x, 1.12, 0, .056, 2.24, .075, iron, door);
    for (const y of [.028, .67, 2.212]) box(.55, y, 0, 1.1, .056, .075, iron, door);
    box(.55, .335, 0, .99, .58, .028, mat('doorPanel', '#8e9991', { metalness: .35, roughness: .5 }), door);
    box(.55, 1.44, 0, .99, 1.48, .022, glass, door).castShadow = false;
    for (const z of [-.07, .07]) box(.97, 1.05, z, .13, .028, .035, iron, door);
    for (const x of [-.035, 1.135]) box(x, 1.15, 0, .06, 2.3, .15, iron);
    box(.55, 2.29, 0, 1.23, .06, .15, iron);
    box(.55, .025, .02, 1.1, .05, .22, mat('threshold', '#c4c7bd'));
    const signMap = texture(768, 384, (ctx, w, h) => {
        ctx.fillStyle = '#b98851'; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#3e4840'; ctx.fillRect(9, 9, w - 18, h - 18);
        ctx.textAlign = 'center'; ctx.fillStyle = '#fff7de'; ctx.font = '600 146px Segoe UI, sans-serif'; ctx.fillText('A103', w / 2, 204);
        ctx.fillStyle = '#dfd3b5'; ctx.font = '34px Segoe UI, sans-serif'; ctx.fillText('TÒA NHÀ AN TÂM', w / 2, 295);
    });
    box(.55, 2.65, .105, .69, .36, .025, warmWood);
    surface(.55, 2.65, .122, .67, .34, 0, signMap);

    // An open, unfurnished wooden loft: the media does not show a bed or other upper furniture.
    solid(0, 2.29, -4.7, 3.4, .14, 3.8, warmWood, false);
    const loftFloor = surface(0, 2.362, -4.7, 3.4, 3.8, 0, woodMap, 3, 2, { roughness: .57 }); loftFloor.rotation.x = -Math.PI / 2;
    const loftUnder = surface(0, 2.218, -4.7, 3.4, 3.8, 0, woodMap, 3, 2, { roughness: .65 }); loftUnder.rotation.x = Math.PI / 2;
    box(0, 2.24, -2.8, 3.4, .07, .055, iron);
    // The opening on the left is wider than the character's body and aligns with the last tread.
    for (const y of [2.39, 3.23]) cameraObstacles.push(box(.45, y, -2.8, 2.5, .055, .055, iron));
    for (const x of [-.8, 1.67]) cameraObstacles.push(box(x, 2.81, -2.8, .06, .9, .06, iron));
    for (let i = 0; i <= 13; i++) cameraObstacles.push(box(-.78 + i * (2.44 / 13), 2.81, -2.8, .026, .83, .026, iron));
    obstacle(.45, -2.8, 2.58, .08, 2.36, 3.28, { tag: 'loft-rail' });
    // This room has rectangular stair frames and broad wooden treads, not A101/A102's ladder.
    const bottomZ = -.85, topZ = -2.8, topY = 2.36, stepCount = 9, stairX = -1.23;
    for (let i = 1; i <= stepCount; i++) {
        const top = topY * i / stepCount, previous = topY * (i - 1) / stepCount;
        const z = bottomZ + (topZ - bottomZ) * i / stepCount;
        box(stairX, top - .024, z, .74, .048, .31, warmWood);
        box(stairX, top - .063, z + .12, .77, .032, .035, iron);
        for (const x of [-1.6, -.86]) {
            box(x, (top + previous) / 2 - .024, z + .125, .035, top - previous, .035, iron);
            box(x, top - .06, z, .035, .035, .29, iron);
        }
    }
    obstacle(stairX, (bottomZ + topZ) / 2, .82, bottomZ - topZ, 0, topY, { tag: 'stairs' });
    // The black handrail is fixed to the wall and follows the gentler stair pitch.
    rod([-1.645, .92, -.94], [-1.645, 3.08, -2.75], .028, iron);
    rod([-1.69, .89, -.94], [-1.645, .92, -.94], .027, iron);
    rod([-1.69, 3.13, -2.8], [-1.645, 3.08, -2.75], .027, iron);

    // White wardrobe with brown trim and the narrow open shelf visible behind the stairs.
    solid(-.96, 1.06, -3.74, 1.28, 2.12, .72, cabinetWood);
    box(-.795, 1.08, -3.365, .91, 2.0, .035, porcelain);
    box(-.795, 1.08, -3.342, .012, 1.98, .008, mat('cabinetSeam', '#b1b2a8'));
    for (const x of [-.835, -.755]) box(x, 1.12, -3.31, .018, .22, .035, chrome);
    box(-1.43, 1.21, -3.36, .28, 1.73, .025, mat('shelfBack', '#745039'));
    for (const y of [.29, .72, 1.15, 1.58, 2.04]) box(-1.43, y, -3.32, .28, .035, .13, cabinetWood);
    for (const y of [.14, .43]) {
        box(-1.43, y, -3.286, .265, .25, .03, porcelain);
        box(-1.43, y, -3.265, .12, .012, .02, chrome);
    }

    // Rear-left bathroom: charcoal frame, gray marble, toilet, basin and electric shower heater.
    solid(-.4, 1.12, -5.9, .11, 2.24, 1.4, white);
    solid(-1.59, 1.12, -5.2, .22, 2.24, .12, white);
    solid(-.55, 1.12, -5.2, .3, 2.24, .12, white);
    solid(-1.1, 2.2, -5.2, 1.2, .08, .12, white, false);
    surface(-1.694, .68, -5.9, 1.4, 1.36, Math.PI / 2, bathMarbleMap, 2.33, 2.26);
    surface(-1.05, .68, -6.587, 1.3, 1.36, 0, bathMarbleMap, 2.16, 2.26);
    surface(-.461, .68, -5.9, 1.4, 1.36, -Math.PI / 2, bathMarbleMap, 2.33, 2.26);
    const bathFloor = surface(-1.05, .014, -5.9, 1.3, 1.4, 0, bathMarbleMap, 2.16, 2.33, { roughness: .42 }); bathFloor.rotation.x = -Math.PI / 2;
    for (const x of [-1.48, -.7]) box(x, 1.08, -5.124, .055, 2.16, .085, iron);
    box(-1.09, 2.15, -5.124, .84, .055, .085, iron);
    const bathroomDoor = solid(-.685, 1.055, -5.6, .036, 2.1, .76, mat('bathDoor', '#9ca8a0'));
    box(-.661, 1.03, -5.8, .025, .12, .025, iron);
    const bathCeiling = surface(-1.05, 2.216, -5.91, 1.3, 1.4, 0, bathMarbleMap, 1.5, 1.5, { color: '#bac4ad', roughness: .8 }); bathCeiling.rotation.x = Math.PI / 2;
    for (const z of [-5.45, -6.15]) box(-1.05, 2.19, z, 1.3, .06, .06, chrome);
    const toilet = new THREE.Group(); toilet.position.set(-.89, 0, -6.16); group.add(toilet);
    mesh(unitSphere, porcelain, 0, .35, .08, .23, .13, .3, toilet);
    mesh(unitSphere, porcelain, 0, .18, .01, .14, .18, .17, toilet);
    box(0, .58, -.16, .4, .43, .14, porcelain, toilet);
    box(0, .803, -.16, .43, .025, .17, porcelain, toilet);
    const seat = mesh(new THREE.TorusGeometry(.143, .023, 8, 24), porcelain, 0, .466, .095, 1, 1.2, 1, toilet); seat.rotation.x = -Math.PI / 2;
    obstacle(-.89, -6.1, .47, .64, 0, .82);
    const basin = mesh(unitSphere, porcelain, -1.5, .73, -5.8, .19, .09, .28); cameraObstacles.push(basin);
    box(-1.615, .64, -5.8, .12, .23, .28, porcelain);
    obstacle(-1.5, -5.8, .38, .56, .54, .82);
    rod([-1.59, .76, -5.92], [-1.59, .93, -5.92], .013, chrome);
    rod([-1.59, .93, -5.92], [-1.44, .93, -5.92], .013, chrome);
    box(-1.665, 1.31, -5.8, .025, .62, .46, chrome);
    box(-1.645, 1.31, -5.8, .008, .56, .4, mat('mirror', '#b1c6c0', { metalness: .9, roughness: .13 }));
    // The white heater's gold fascia and black control panel are especially distinctive in the close-up.
    solid(-1.1, 1.66, -6.49, .35, .56, .17, porcelain, false);
    box(-1.075, 1.69, -6.396, .16, .45, .018, mat('heaterGold', '#b39862', { metalness: .28, roughness: .47 }));
    box(-1.075, 1.76, -6.382, .07, .16, .015, iron);
    const control = cylinder(-1.075, 1.568, -6.372, .033, .014, iron); control.rotation.x = Math.PI / 2;
    for (const x of [-1.18, -.99]) rod([x, 1.39, -6.48], [x, 1.28, -6.48], .016, porcelain);
    rod([-1.48, 1.32, -6.49], [-1.48, 1.94, -6.49], .016, porcelain);
    const showerHead = cylinder(-1.48, 1.98, -6.44, .07, .025, chrome); showerHead.rotation.x = .4;
    const hose = new THREE.CubicBezierCurve3(new THREE.Vector3(-1.46, 1.9, -6.44), new THREE.Vector3(-1.73, .8, -6.31), new THREE.Vector3(-1.05, .68, -6.26), new THREE.Vector3(-1.18, 1.28, -6.48));
    mesh(new THREE.TubeGeometry(hose, 24, .009, 7, false), porcelain, 0, 0, 0);

    // Compact L-shaped black stone counter with open black supports and wood shelves underneath.
    solid(.48, .87, -6.21, 1.7, .055, .64, stone);
    solid(1.38, .87, -5.68, .59, .055, 1.7, stone);
    for (const [x, z] of [[-.31, -5.92], [.95, -5.92], [1.13, -4.9], [1.64, -4.9]]) box(x, .43, z, .035, .86, .035, iron);
    box(.41, .115, -6.19, 1.47, .035, .52, warmWood);
    box(1.38, .115, -5.45, .49, .035, 1.13, warmWood);
    for (const z of [-6.47, -5.9]) box(.44, .09, z, 1.55, .035, .035, iron);
    for (const x of [1.12, 1.64]) box(x, .09, -5.48, .035, .035, 1.2, iron);
    solid(1.38, .44, -4.835, .59, .88, .045, mat('counterEnd', '#c5c1b2'));
    obstacle(.48, -6.21, 1.7, .64, 0, .9);
    obstacle(1.38, -5.68, .59, 1.7, 0, .9);
    box(.14, .908, -6.2, .58, .021, .44, chrome);
    box(.14, .924, -6.2, .48, .022, .33, mat('sinkBasin', '#7d8781', { metalness: .65, roughness: .28 }));
    const faucet = new THREE.CubicBezierCurve3(new THREE.Vector3(.39, .92, -6.43), new THREE.Vector3(.39, 1.4, -6.43), new THREE.Vector3(.06, 1.42, -6.3), new THREE.Vector3(.06, 1.19, -6.22));
    mesh(new THREE.TubeGeometry(faucet, 20, .015, 8, false), chrome, 0, 0, 0);
    rod([.4, 1.0, -6.43], [.48, 1.05, -6.43], .008, chrome);
    cylinder(.14, .73, -6.2, .155, .22, chrome);
    rod([.14, .65, -6.2], [.14, .46, -6.2], .033, iron);
    rod([.14, .46, -6.2], [.14, .46, -6.48], .033, iron);
    // Stainless two-tier dish rack and the small hanging utensil basket.
    for (const x of [-.28, .58]) box(x, 1.62, -6.4, .015, .59, .015, chrome);
    for (const y of [1.37, 1.81]) {
        for (const z of [-6.52, -6.25]) box(.15, y, z, .88, .016, .016, chrome);
        for (let i = 0; i < 13; i++) box(-.26 + i * .067, y, -6.385, .01, .01, .27, chrome);
        box(.15, y + .075, -6.25, .88, .012, .012, chrome);
        for (const x of [-.28, .58]) box(x, y + .037, -6.25, .012, .075, .012, chrome);
    }
    for (const y of [1.48, 1.72]) box(.73, y, -6.37, .2, .012, .18, chrome);
    for (let i = 0; i < 5; i++) box(.65 + i * .04, 1.6, -6.27, .006, .24, .006, chrome);
    for (const x of [.63, .83]) box(x, 1.6, -6.37, .008, .25, .18, chrome);
    // Plain wall sockets, matching the uncluttered service area in the source.
    for (const z of [-4.5, -5.9]) {
        box(1.675, 1.4, z, .024, .13, .08, porcelain);
        for (const y of [1.385, 1.425]) box(1.66, y, z, .005, .015, .008, iron);
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
        ceiling: { loftFrontZ: -2.8, undersideY: 2.22, roomHeight: 4.4 },
        headClearance: 2.16,
        stairs: { minX: offsetX - 1.6, maxX: offsetX - .86, bottomZ, topZ, bottomY: 0, topY },
        loft: { minX: offsetX - 1.7, maxX: offsetX + 1.7, minZ: -6.6, maxZ: -2.8, y: topY, ceilingY: 4.4 },
        landmarks: [
            { position: { x: offsetX + .55, y: 1.3, z: .25 }, label: 'Cửa phòng A103' },
            { position: { x: offsetX - 1.23, y: 1.2, z: -1.75 }, label: 'Cầu thang khung sắt, bậc gỗ' },
            { position: { x: offsetX - .95, y: 1.1, z: -3.3 }, label: 'Tủ quần áo' },
            { position: { x: offsetX - 1.05, y: 1.2, z: -5.1 }, label: 'Phòng tắm và máy nước nóng' },
            { position: { x: offsetX + .6, y: 1.1, z: -5.8 }, label: 'Bếp chữ L và bồn rửa' },
        ],
    };
}
