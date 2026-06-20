import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { AdditiveBlending, Color, DoubleSide, Group, Matrix4, type PointLight, Quaternion, Sprite, SpriteMaterial, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { bodyByHex, locomotionFor } from './bodies';
import { glowTexture } from './glow';
import { starShape } from './shapes';

interface Line { vi: string; en: string; }
const SPEECH: Record<string, Line> = {
  intro: { vi: 'Đi đâu hôm nay? ✨', en: 'Where to today?' },
  system: { vi: 'Chạm một hành tinh nhé!', en: 'Tap a planet!' },
};
// Diegetic captions that make the confusing locomotions read as intentional meaning.
const STANCE_CAPTION: Partial<Record<string, Line>> = {
  sink: { vi: 'Hấp dẫn về phía nỗi buồn sâu nhất', en: 'Pulled toward the deepest sadness' },
  surf: { vi: 'Lướt sao chổi — tươi mới, thoáng qua', en: 'Surfing the comet — fresh, fleeting' },
};

// Distance (local model units) from the group origin down to the soles — used to lift
// the runner so its feet sit ON the planet surface instead of sinking in. Derived from
// the geometry: boot box bottom = legL(-0.26) + shinL(-0.17) + boot(-0.15 - 0.11/2) =
// -0.635. The lift (FOOT_DROP * scale) cancels the scaled foot depth for ANY planet
// size, so the soles land on the surface regardless of the body's radius.
const FOOT_DROP = 0.635;

// A realistic PBR EVA spacesuit (NASA xEMU-flavoured): white hard-upper-torso + PLSS backpack,
// gold mirror visor that reflects the galaxy (scene env map), segmented soft joints, grey gloves
// and boots. VN identity kept SUBTLE — a small flag patch + tiny gold star on the chest. The
// animation rig (bob/legL/legR/shinL/shinR/armL/armR/eye groups), FOOT_DROP foot-plant geometry
// and useFrame are UNCHANGED from the prior model. In first-person flight we ARE the pilot, so the
// body isn't drawn (the cockpit shows the dashboard instead).
export default function Astronaut() {
  const camera = useThree((s) => s.camera);
  const root = useRef<Group>(null);
  const bob = useRef<Group>(null);
  const legL = useRef<Group>(null);
  const legR = useRef<Group>(null);
  const shinL = useRef<Group>(null);
  const shinR = useRef<Group>(null);
  const armL = useRef<Group>(null);
  const armR = useRef<Group>(null);
  const eyeL = useRef<Group>(null);
  const eyeR = useRef<Group>(null);
  const helmetLight = useRef<PointLight>(null);

  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const accent = useMemo(() => new Color(sel[0] || '#7cc7ff'), [sel]);
  // Speech bubble: greeting/coach in intro+system; a meaning caption for sink/surf in explore.
  const exBody = mode === 'explore' && sel[0] ? bodyByHex(sel[0]) : undefined;
  const exStance = exBody ? locomotionFor(exBody) : null;
  const bubble: Line | undefined =
    SPEECH[mode] ?? (exStance && STANCE_CAPTION[exStance]) ?? undefined;

  const star = useMemo(() => starShape(0.055, 0.024), []);
  const tex = glowTexture();

  const noteSpriteRefs = useRef<(Sprite | null)[]>([]);
  const noteY = useRef([0, 0.9, 1.8]);

  const tmp = useRef(new Vector3());
  const baseVec = useRef(new Vector3());
  const up = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const xAxis = useRef(new Vector3());
  const m4 = useRef(new Matrix4());
  const quat = useRef(new Quaternion());
  const frozenT = useRef(0); // last live time → reduced-motion holds a static pose

  useFrame((state, dt) => {
    if (!root.current) return;
    const k = 1 - Math.pow(0.002, dt);
    const g = root.current;
    const rm = solarRefs.reducedMotion;
    if (!rm) frozenT.current = state.clock.elapsedTime;
    const t = rm ? frozenT.current : state.clock.elapsedTime; // freeze limb/bob/blink cycles

    const running = mode === 'explore' && solarRefs.runnerActive && !!sel[0];
    const boarding = mode === 'boarding' && solarRefs.runnerActive && !!sel[0];
    const waving = mode === 'intro';

    if (running || boarding) {
      const size = bodyByHex(sel[0])?.size ?? 0.5;
      const scale = Math.max(0.045, size * 0.12);
      // body-appropriate "up" (radial for walk/hop/float/surf; ring-plane normal for ringwalk)
      up.current.copy(solarRefs.runnerUp);
      if (up.current.lengthSq() < 1e-4) up.current.set(0, 1, 0); else up.current.normalize();
      baseVec.current.copy(solarRefs.runnerPos).addScaledVector(up.current, FOOT_DROP * scale);

      if (boarding) {
        // drawn straight up the tractor beam toward the saucer underside, fading near the top
        const lift = solarRefs.boardingLift;
        tmp.current.lerpVectors(baseVec.current, solarRefs.boardingTarget, lift);
        g.position.lerp(tmp.current, Math.min(1, dt * 10));
        const fade = lift > 0.85 ? Math.max(0.01, 1 - (lift - 0.85) / 0.15) : 1;
        g.scale.setScalar(scale * fade);
      } else if (solarRefs.runnerStance === 'sink') {
        // spiralling toward the black hole → follow snappily; linger at the event horizon
        // (don't vanish — that read as "the astronaut died"; the meaning is "pulled toward sadness")
        g.position.lerp(baseVec.current, Math.min(1, dt * 10));
        g.scale.setScalar(scale * Math.max(0.4, 1 - 0.5 * solarRefs.runnerSink));
      } else {
        g.position.lerp(baseVec.current, k);
        g.scale.setScalar(scale);
      }

      // orient feet toward `up` (the body-appropriate surface), nose along forward
      fwd.current.copy(solarRefs.runnerForward).normalize();
      xAxis.current.copy(up.current).cross(fwd.current).normalize();
      fwd.current.copy(xAxis.current).cross(up.current).normalize();
      m4.current.makeBasis(xAxis.current, up.current, fwd.current);
      quat.current.setFromRotationMatrix(m4.current);
      g.quaternion.slerp(quat.current, k);
    } else {
      tmp.current.set(-1.2, -0.95, -3.3).applyMatrix4(camera.matrixWorld);
      g.position.lerp(tmp.current, k);
      g.quaternion.slerp(camera.quaternion, k);
      g.scale.setScalar(0.44);
    }

    // ── animation BY STANCE (walk/ringwalk run-cycle · hop tuck · float+surf arms-out ·
    //    sink curl) — each body moves differently ──
    const stance = solarRefs.runnerStance;
    const stepping = running && (stance === 'walk' || stance === 'ringwalk');
    const hopping = running && stance === 'hop';
    const floating = running && stance === 'float';
    const surfing = running && stance === 'surf';
    const sinkAmt = running && stance === 'sink' ? solarRefs.runnerSink : 0;
    const cad = t * (hopping ? 5 : 7);
    const sw = Math.sin(cad);

    if (bob.current) {
      if (stepping) {
        bob.current.position.y = Math.abs(Math.sin(cad)) * 0.05;
        const sq = Math.max(0, -sw) * 0.12;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else if (hopping) {
        const sq = (1 - Math.abs(Math.sin(t * 2))) * 0.1; // squash on landing (syncs with hop air)
        bob.current.position.y = 0;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else if (surfing) {
        bob.current.position.y = 0; bob.current.scale.set(1, 1, 1);
        bob.current.rotation.x = 0.18 + Math.sin(t * 1.6) * 0.05; // lean into travel + wobble
      } else if (sinkAmt > 0) {
        bob.current.position.y = 0; bob.current.scale.set(1, 1, 1);
        bob.current.rotation.x = 0.6 * sinkAmt; // curl forward as swallowed
      } else {
        bob.current.position.y = Math.sin(t * 0.9) * 0.04; // float / idle breathe
        bob.current.scale.set(1, 1, 1); bob.current.rotation.x = 0;
      }
    }
    if (legL.current && legR.current && shinL.current && shinR.current) {
      if (stepping) {
        legL.current.rotation.x = sw * 0.6; legR.current.rotation.x = -sw * 0.6;
        shinL.current.rotation.x = Math.max(0, -sw) * 1.2; shinR.current.rotation.x = Math.max(0, sw) * 1.2;
      } else if (hopping) {
        const tuck = Math.abs(Math.sin(t * 2)) * 0.8;
        legL.current.rotation.x = tuck; legR.current.rotation.x = tuck;
        shinL.current.rotation.x = tuck * 1.2; shinR.current.rotation.x = tuck * 1.2;
      } else if (surfing) {
        legL.current.rotation.x = 0.28; legR.current.rotation.x = -0.08; // staggered surf stance
        shinL.current.rotation.x = 0.5; shinR.current.rotation.x = 0.5;  // knees bent
      } else if (sinkAmt > 0) {
        legL.current.rotation.x = 1.2 * sinkAmt; legR.current.rotation.x = 1.2 * sinkAmt;
        shinL.current.rotation.x = 1.4 * sinkAmt; shinR.current.rotation.x = 1.4 * sinkAmt;
      } else {
        const dangle = floating ? 0.15 : 0;
        legL.current.rotation.x = dangle; legR.current.rotation.x = dangle;
        shinL.current.rotation.x = 0; shinR.current.rotation.x = 0;
      }
    }
    if (armL.current && armR.current) {
      if (waving) {
        armR.current.rotation.z = -2.3; armR.current.rotation.x = Math.sin(t * 6) * 0.4;
        armL.current.rotation.z = 0.2; armL.current.rotation.x = 0;
      } else if (surfing || floating) {
        armL.current.rotation.z = 0.95; armR.current.rotation.z = -0.95; // arms out
        const sway = Math.sin(t * (surfing ? 1.6 : 1.2)) * 0.15;
        armL.current.rotation.x = sway; armR.current.rotation.x = -sway;
      } else if (sinkAmt > 0) {
        armL.current.rotation.z = 0.2 - 0.8 * sinkAmt; armR.current.rotation.z = -0.2 + 0.8 * sinkAmt;
        armL.current.rotation.x = 1.0 * sinkAmt; armR.current.rotation.x = 1.0 * sinkAmt;
      } else {
        const run = stepping ? sw * 0.5 : 0;
        armL.current.rotation.z = 0.2; armR.current.rotation.z = -0.2;
        armL.current.rotation.x = -run; armR.current.rotation.x = run;
      }
    }
    // ── blink: a quick lid-close every ~4.5s (0.2s V-shaped dip) ──
    if (eyeL.current && eyeR.current) {
      const cyc = t % 4.5;
      let v = 1;
      if (cyc > 4.3) v = 0.1 + 0.9 * Math.abs((cyc - 4.3) / 0.2 - 0.5) * 2; // 1→0.1→1
      eyeL.current.scale.y = v; eyeR.current.scale.y = v;
    }

    // ── add life: gentle EVA tether sway when idle (not in an active stance) + an
    //    audio-reactive helmet lamp that casts moving light as the camera orbits ──
    if (bob.current) {
      const idle = !stepping && !hopping && !surfing && !(sinkAmt > 0);
      bob.current.rotation.z = idle && !rm ? Math.sin(t * 0.5) * 0.04 : 0;
      bob.current.position.x = idle && !rm ? Math.sin(t * 0.37) * 0.015 : 0;
    }
    // helmet lamp pulses with overall energy (audio stays on under reduced-motion, like the ship)
    if (helmetLight.current) helmetLight.current.intensity = 0.5 + engine.features.rms * 1.6;

    // ── music notes: 3 glow sprites rising above the astronaut (not while sinking — sadness;
    //    hidden under reduced-motion since the whole point is the upward drift) ──
    const noteVisible = (running || boarding) && stance !== 'sink' && !rm;
    const noteXZ: [number, number][] = [[0.55, 0.2], [-0.45, -0.25], [0.65, -0.05]];
    noteSpriteRefs.current.forEach((s, i) => {
      if (!s) return;
      s.visible = noteVisible;
      if (!noteVisible) return;
      noteY.current[i] = (noteY.current[i] + dt * 0.7) % 2.4;
      const y = noteY.current[i];
      s.position.set(noteXZ[i][0] + Math.sin(t * 0.8 + i) * 0.03, y + 0.4, noteXZ[i][1]);
      const fade = y < 0.6 ? y / 0.6 : y > 1.9 ? (2.4 - y) / 0.5 : 1;
      (s.material as SpriteMaterial).opacity = Math.max(0, fade * 0.72);
    });
  });

  // ── PBR suit palette ──
  const SUIT = '#eef1f7';        // white soft-goods
  const HARD = '#dfe3ec';        // hard upper torso / helmet shell (slightly cooler white)
  const JOINT = '#9aa1b0';       // grey joint / seal rings
  const DARK = '#39404e';        // PLSS / control panel dark grey
  const GLOVEBOOT = '#b9c0cf';   // gloves + boots
  const VISOR = '#caa23a';       // gold reflective sun-visor
  const RED = '#da251d';         // VN flag red (subtle, chest only)
  const GOLD = '#ffcd00';        // VN star gold

  // First-person flight: we ARE the pilot → the body isn't drawn (cockpit shows the dashboard).
  if (mode === 'journey' || mode === 'fly') return null;

  return (
    <group ref={root}>
      <group ref={bob}>
        {/* ── helmet (white shell + gold mirror sun-visor that reflects the env map) ── */}
        <mesh position={[0, 0.56, 0]}>
          <sphereGeometry args={[0.30, 32, 32]} />
          <meshStandardMaterial color={HARD} roughness={0.2} metalness={0.1} envMapIntensity={0.6} />
        </mesh>
        {/* gold sun-visor: a spherical cap over the front-lower helmet — a galaxy mirror */}
        <mesh position={[0, 0.56, 0]} rotation={[Math.PI / 2 - 0.12, 0, 0]}>
          <sphereGeometry args={[0.305, 32, 22, 0, Math.PI * 2, 0, 1.15]} />
          <meshStandardMaterial color={VISOR} metalness={1} roughness={0.07} envMapIntensity={1.6} side={DoubleSide} />
        </mesh>
        {/* visor seal rim */}
        <mesh position={[0, 0.56, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.28, 0.022, 12, 36]} />
          <meshStandardMaterial color={DARK} roughness={0.5} metalness={0.3} />
        </mesh>
        {/* helmet side lamp housing (light itself added in the add-life pass) */}
        <mesh position={[0.21, 0.62, 0.14]}>
          <boxGeometry args={[0.05, 0.04, 0.05]} />
          <meshStandardMaterial color={DARK} roughness={0.4} metalness={0.4} />
        </mesh>
        <mesh position={[0.21, 0.62, 0.17]}>
          <sphereGeometry args={[0.018, 10, 10]} />
          <meshStandardMaterial color="#fff7e0" emissive="#fff2cf" emissiveIntensity={2.2} toneMapped={false} />
        </mesh>
        <pointLight ref={helmetLight} position={[0.21, 0.62, 0.26]} color="#fff2cf" distance={2.6} decay={1.6} intensity={1} />

        {/* eye groups kept for the blink rig — faint HUD ticks behind the visor (mostly unseen) */}
        <group ref={eyeL} position={[-0.1, 0.57, 0.27]}>
          <mesh><sphereGeometry args={[0.012, 8, 8]} /><meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={1.2} toneMapped={false} /></mesh>
        </group>
        <group ref={eyeR} position={[0.1, 0.57, 0.27]}>
          <mesh><sphereGeometry args={[0.012, 8, 8]} /><meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={1.2} toneMapped={false} /></mesh>
        </group>

        {/* neck seal ring */}
        <mesh position={[0, 0.28, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.155, 0.04, 12, 24]} />
          <meshStandardMaterial color={JOINT} roughness={0.7} metalness={0.2} />
        </mesh>

        {/* ── hard upper torso (bulky EVA HUT) ── */}
        <mesh position={[0, 0.02, 0]}>
          <capsuleGeometry args={[0.27, 0.16, 8, 20]} />
          <meshStandardMaterial color={SUIT} roughness={0.5} metalness={0.05} envMapIntensity={0.4} />
        </mesh>
        {/* lower torso / waist seal (narrower) */}
        <mesh position={[0, -0.18, 0]}>
          <capsuleGeometry args={[0.2, 0.05, 8, 16]} />
          <meshStandardMaterial color={HARD} roughness={0.55} metalness={0.05} envMapIntensity={0.35} />
        </mesh>
        <mesh position={[0, -0.12, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.215, 0.028, 12, 28]} />
          <meshStandardMaterial color={JOINT} roughness={0.7} metalness={0.2} />
        </mesh>

        {/* chest control panel + emotion indicator light */}
        <mesh position={[0.04, 0.04, 0.25]} rotation={[0.1, 0, 0]}>
          <boxGeometry args={[0.18, 0.13, 0.04]} />
          <meshStandardMaterial color={DARK} roughness={0.45} metalness={0.4} />
        </mesh>
        <mesh position={[0.08, 0.06, 0.275]}>
          <sphereGeometry args={[0.02, 12, 12]} />
          <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={2.0} toneMapped={false} />
        </mesh>
        {/* VN flag patch (subtle) — small red square + tiny gold star on the chest */}
        <mesh position={[-0.11, 0.05, 0.255]} rotation={[0.1, 0, 0]}>
          <planeGeometry args={[0.11, 0.075]} />
          <meshStandardMaterial color={RED} roughness={0.6} side={DoubleSide} />
        </mesh>
        <mesh position={[-0.11, 0.05, 0.267]} rotation={[0.1, 0, 0]}>
          <shapeGeometry args={[star]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.25} roughness={0.5} metalness={0.6} side={DoubleSide} />
        </mesh>

        {/* PLSS life-support backpack */}
        <mesh position={[0, 0.02, -0.26]}>
          <boxGeometry args={[0.4, 0.42, 0.18]} />
          <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.25} envMapIntensity={0.4} />
        </mesh>
        <mesh position={[0, 0.02, -0.36]}>
          <boxGeometry args={[0.3, 0.3, 0.03]} />
          <meshStandardMaterial color={HARD} roughness={0.5} metalness={0.1} />
        </mesh>

        {/* ── arms: shoulder pivot → upper arm → elbow seal → grey glove ── */}
        <group ref={armL} position={[-0.3, 0.12, 0]}>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.082, 0.12, 8, 14]} />
            <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
          </mesh>
          <mesh position={[0, -0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.082, 0.022, 10, 18]} />
            <meshStandardMaterial color={JOINT} roughness={0.75} />
          </mesh>
          <mesh position={[0, -0.27, 0]}>
            <sphereGeometry args={[0.095, 16, 16]} />
            <meshStandardMaterial color={GLOVEBOOT} roughness={0.5} metalness={0.1} />
          </mesh>
        </group>
        <group ref={armR} position={[0.3, 0.12, 0]}>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.082, 0.12, 8, 14]} />
            <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
          </mesh>
          <mesh position={[0, -0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.082, 0.022, 10, 18]} />
            <meshStandardMaterial color={JOINT} roughness={0.75} />
          </mesh>
          <mesh position={[0, -0.27, 0]}>
            <sphereGeometry args={[0.095, 16, 16]} />
            <meshStandardMaterial color={GLOVEBOOT} roughness={0.5} metalness={0.1} />
          </mesh>
        </group>

        {/* ── legs: thigh (hip pivot) → knee seal → shin (knee pivot) → boot ──
            offsets UNCHANGED so FOOT_DROP still plants the soles on every planet. ── */}
        <group ref={legL} position={[-0.13, -0.26, 0]}>
          <mesh position={[0, -0.08, 0]}>
            <capsuleGeometry args={[0.1, 0.08, 8, 14]} />
            <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
          </mesh>
          <group ref={shinL} position={[0, -0.17, 0]}>
            <mesh position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.09, 0.022, 10, 18]} />
              <meshStandardMaterial color={JOINT} roughness={0.75} />
            </mesh>
            <mesh position={[0, -0.07, 0]}>
              <capsuleGeometry args={[0.092, 0.07, 8, 14]} />
              <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
            </mesh>
            <mesh position={[0, -0.15, 0.05]}>
              <boxGeometry args={[0.17, 0.11, 0.25]} />
              <meshStandardMaterial color={GLOVEBOOT} roughness={0.5} metalness={0.15} />
            </mesh>
          </group>
        </group>
        <group ref={legR} position={[0.13, -0.26, 0]}>
          <mesh position={[0, -0.08, 0]}>
            <capsuleGeometry args={[0.1, 0.08, 8, 14]} />
            <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
          </mesh>
          <group ref={shinR} position={[0, -0.17, 0]}>
            <mesh position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.09, 0.022, 10, 18]} />
              <meshStandardMaterial color={JOINT} roughness={0.75} />
            </mesh>
            <mesh position={[0, -0.07, 0]}>
              <capsuleGeometry args={[0.092, 0.07, 8, 14]} />
              <meshStandardMaterial color={SUIT} roughness={0.6} metalness={0.05} />
            </mesh>
            <mesh position={[0, -0.15, 0.05]}>
              <boxGeometry args={[0.17, 0.11, 0.25]} />
              <meshStandardMaterial color={GLOVEBOOT} roughness={0.5} metalness={0.15} />
            </mesh>
          </group>
        </group>

        {bubble && (
          <Html center distanceFactor={6} position={[1.0, 1.2, 0]} pointerEvents="none">
            <div className="astro-speech">
              {bubble.vi}
              <span className="astro-speech-sub">{bubble.en}</span>
            </div>
          </Html>
        )}

        {/* ── music note glow sprites — animated in useFrame, visible in explore/boarding ── */}
        {[0, 1, 2].map((i) => (
          <sprite key={i} ref={(el) => { noteSpriteRefs.current[i] = el; }} visible={false}>
            <spriteMaterial map={tex} color="#00eeff" transparent opacity={0} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
        ))}
      </group>
    </group>
  );
}
