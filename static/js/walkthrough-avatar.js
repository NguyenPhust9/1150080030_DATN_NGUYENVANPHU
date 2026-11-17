/** A lightweight, self-contained visitor for the room walkthrough. Faces +Z. */
export function createWalker(THREE) {
    const group = new THREE.Group();
    group.name = 'walker';

    const material = (color, roughness = 0.85) => new THREE.MeshStandardMaterial({ color, roughness });
    const skin = material(0xf1bd97);
    const hair = material(0x292020);
    const hoodie = material(0xd76d42);
    const hoodieDark = material(0xb65134);
    const trousers = material(0x28384b);
    const shoes = material(0xf4ecde);
    const soles = material(0xc6baaa);
    const eyes = material(0x2b2524);
    const cheeks = material(0xdf9681);
    const cream = material(0xffe7be);
    const sphere = new THREE.SphereGeometry(1, 16, 12);
    const cylinder = new THREE.CylinderGeometry(1, 1, 1, 12);
    const box = new THREE.BoxGeometry(1, 1, 1);

    function mesh(parent, geometry, surface, position, scale) {
        const part = new THREE.Mesh(geometry, surface);
        part.position.set(...position);
        part.scale.set(...scale);
        part.castShadow = true;
        part.receiveShadow = true;
        parent.add(part);
        return part;
    }

    const body = new THREE.Group();
    group.add(body);
    mesh(body, cylinder, hoodie, [0, 0.725, 0], [0.165, 0.35, 0.12]);
    mesh(body, sphere, hoodie, [0, 0.86, 0], [0.19, 0.08, 0.125]);
    mesh(body, cylinder, hoodieDark, [0, 0.565, 0], [0.165, 0.035, 0.12]);
    mesh(body, sphere, trousers, [0, 0.535, 0], [0.16, 0.09, 0.115]);
    mesh(body, cylinder, skin, [0, 0.93, 0], [0.071, 0.095, 0.071]);

    // Soft hood and seams remain visible when following the character from behind.
    mesh(body, sphere, hoodieDark, [0, 0.864, -0.106], [0.145, 0.082, 0.078]);
    mesh(body, sphere, hoodie, [0, 0.883, -0.108], [0.119, 0.052, 0.063]);
    mesh(body, sphere, hoodieDark, [0, 0.66, 0.117], [0.1, 0.052, 0.011]);
    for (const side of [-1, 1]) {
        mesh(body, cylinder, cream, [side * 0.036, 0.822, 0.121], [0.006, 0.086, 0.006]);
        mesh(body, sphere, cream, [side * 0.036, 0.775, 0.122], [0.009, 0.011, 0.009]);
    }

    const head = new THREE.Group();
    head.position.set(0, 1.105, 0);
    body.add(head);
    mesh(head, sphere, skin, [0, 0, 0], [0.224, 0.229, 0.205]);
    for (const side of [-1, 1]) {
        mesh(head, sphere, skin, [side * 0.215, -0.017, -0.002], [0.034, 0.054, 0.033]);
        mesh(head, sphere, eyes, [side * 0.074, 0.018, 0.19], [0.021, 0.031, 0.014]);
        mesh(head, sphere, shoes, [side * 0.075 - 0.005, 0.027, 0.202], [0.0055, 0.007, 0.003]);
        mesh(head, sphere, cheeks, [side * 0.116, -0.036, 0.176], [0.027, 0.013, 0.007]);
        const brow = mesh(head, sphere, hair, [side * 0.077, 0.072, 0.184], [0.034, 0.008, 0.006]);
        brow.rotation.z = side * -0.08;
    }
    mesh(head, sphere, skin, [0, -0.022, 0.205], [0.023, 0.027, 0.025]);
    const smile = new THREE.Mesh(
        new THREE.TorusGeometry(0.027, 0.004, 5, 12, Math.PI * 0.7),
        hoodieDark,
    );
    smile.position.set(0, -0.052, 0.198);
    smile.rotation.z = Math.PI * 1.15;
    head.add(smile);

    const hairCap = new THREE.SphereGeometry(1, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.52);
    mesh(head, hairCap, hair, [0, 0.008, -0.016], [0.235, 0.235, 0.216]);
    // A swept fringe and short sideburns give the silhouette some personality.
    const fringe = mesh(head, sphere, hair, [-0.055, 0.136, 0.149], [0.151, 0.062, 0.063]);
    fringe.rotation.z = -0.22;
    const fringeTip = mesh(head, sphere, hair, [-0.161, 0.075, 0.11], [0.047, 0.089, 0.054]);
    fringeTip.rotation.z = -0.3;
    for (const side of [-1, 1]) {
        mesh(head, sphere, hair, [side * 0.205, 0.033, -0.013], [0.029, 0.082, 0.092]);
    }

    const arms = [];
    const legs = [];
    const knees = [];
    for (const side of [-1, 1]) {
        const arm = new THREE.Group();
        arm.position.set(side * 0.19, 0.855, 0);
        arm.rotation.z = side * 0.11;
        body.add(arm);
        mesh(arm, sphere, hoodie, [0, -0.025, 0], [0.073, 0.09, 0.073]);
        mesh(arm, cylinder, hoodie, [0, -0.15, 0], [0.057, 0.25, 0.062]);
        mesh(arm, cylinder, hoodieDark, [0, -0.283, 0], [0.05, 0.035, 0.055]);
        mesh(arm, sphere, skin, [0, -0.323, 0.009], [0.046, 0.058, 0.047]);
        arms.push(arm);

        const leg = new THREE.Group();
        leg.position.set(side * 0.084, 0.53, 0);
        group.add(leg);
        mesh(leg, cylinder, trousers, [0, -0.103, 0], [0.068, 0.206, 0.077]);
        mesh(leg, sphere, trousers, [0, -0.205, 0], [0.068, 0.067, 0.077]);
        const knee = new THREE.Group();
        knee.position.y = -0.205;
        leg.add(knee);
        mesh(knee, cylinder, trousers, [0, -0.1, 0], [0.068, 0.2, 0.077]);
        mesh(knee, cylinder, trousers, [0, -0.196, 0], [0.07, 0.035, 0.078]);
        mesh(knee, sphere, soles, [0, -0.282, 0.043], [0.079, 0.034, 0.135]);
        mesh(knee, sphere, shoes, [0, -0.255, 0.041], [0.077, 0.052, 0.131]);
        mesh(knee, box, cream, [0, -0.219, 0.081], [0.057, 0.012, 0.033]);
        legs.push(leg);
        knees.push(knee);
    }

    let previousTime;
    let walkingBlend = 0;
    let airborneBlend = 0;
    function animate(time, moving, { airborne = false, verticalVelocity = 0 } = {}) {
        const elapsed = previousTime === undefined ? 0 : Math.max(0, Math.min(time - previousTime, 0.1));
        previousTime = time;
        walkingBlend = THREE.MathUtils.damp(walkingBlend, moving && !airborne ? 1 : 0, 12, elapsed);
        airborneBlend = THREE.MathUtils.damp(airborneBlend, airborne ? 1 : 0, 18, elapsed);
        const onGround = 1 - airborneBlend;
        const rising = THREE.MathUtils.clamp(verticalVelocity / 3, -1, 1);
        const stride = Math.sin(time * 9) * walkingBlend * onGround;
        // Only joints animate here; the controller owns the root's jump height.
        const tuckedHip = (-0.25 - rising * 0.06) * airborneBlend;
        legs[0].rotation.x = stride * 0.43 + tuckedHip;
        legs[1].rotation.x = -stride * 0.43 + tuckedHip;
        knees.forEach(knee => { knee.rotation.x = (0.65 + rising * 0.1) * airborneBlend; });
        arms[0].rotation.x = (-stride * 0.39 - 0.05) * onGround + (-0.7 - rising * 0.12) * airborneBlend;
        arms[1].rotation.x = (stride * 0.39 - 0.05) * onGround + (-0.7 - rising * 0.12) * airborneBlend;
        arms[0].rotation.z = -0.11 - airborneBlend * 0.13;
        arms[1].rotation.z = 0.11 + airborneBlend * 0.13;
        body.position.y = (Math.abs(Math.cos(time * 9)) * 0.018 * walkingBlend
            + Math.sin(time * 2.2) * 0.003 * (1 - walkingBlend)) * onGround;
        body.rotation.x = airborneBlend * 0.035;
        body.rotation.z = Math.sin(time * 9) * 0.015 * walkingBlend * onGround;
        head.rotation.z = Math.sin(time * 1.5) * 0.014 * (1 - walkingBlend) * onGround;
    }

    return { group, animate };
}
