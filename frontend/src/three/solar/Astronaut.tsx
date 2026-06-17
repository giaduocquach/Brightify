import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html, Outlines } from '@react-three/drei';
import { AdditiveBlending, Color, DoubleSide, Group, Matrix4, Quaternion, Sprite, SpriteMaterial, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex, locomotionFor } from './bodies';
import { glowTexture } from './glow';
import { starShape } from './shapes';
import { toonRamp, OUTLINE } from './toon';

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

// A cel-shaded CHIBI Vietnamese astronaut mascot: oversized helmet head with a friendly
// FACE behind the visor (big shiny eyes, smile, rosy cheeks), round stubby body + limbs,
// ink outline. Keeps the VN identity — gold star on the helmet, a red flag patch with the
// gold star on the chest, an Đông Sơn ring of gold studs at the waist. Animation: blink,
// idle float, run (squash & stretch + foot dust), wave. In first-person flight we ARE the
// pilot, so the body isn't drawn (the cockpit shows the pilot's hands instead).
export default function Astronaut() {
  const camera = useThree((s) => s.camera);
  const ramp = toonRamp();
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

  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const accent = useMemo(() => new Color(sel[0] || '#7cc7ff'), [sel]);
  // Speech bubble: greeting/coach in intro+system; a meaning caption for sink/surf in explore.
  const exBody = mode === 'explore' && sel[0] ? bodyByHex(sel[0]) : undefined;
  const exStance = exBody ? locomotionFor(exBody) : null;
  const bubble: Line | undefined =
    SPEECH[mode] ?? (exStance && STANCE_CAPTION[exStance]) ?? undefined;

  const star = useMemo(() => starShape(0.07, 0.03), []);
  const helmetStar = useMemo(() => starShape(0.13, 0.055), []);
  const dongSon = useMemo(() => Array.from({ length: 12 }, (_, i) => (i / 12) * Math.PI * 2), []);
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
    const cad = t * (hopping ? 8 : 12);
    const sw = Math.sin(cad);

    if (bob.current) {
      if (stepping) {
        bob.current.position.y = Math.abs(Math.sin(cad)) * 0.05;
        const sq = Math.max(0, -sw) * 0.12;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else if (hopping) {
        const sq = (1 - Math.abs(Math.sin(t * 3))) * 0.1; // squash on landing
        bob.current.position.y = 0;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else if (surfing) {
        bob.current.position.y = 0; bob.current.scale.set(1, 1, 1);
        bob.current.rotation.x = 0.18 + Math.sin(t * 3) * 0.05; // lean into travel + wobble
      } else if (sinkAmt > 0) {
        bob.current.position.y = 0; bob.current.scale.set(1, 1, 1);
        bob.current.rotation.x = 0.6 * sinkAmt; // curl forward as swallowed
      } else {
        bob.current.position.y = Math.sin(t * 1.4) * 0.04; // float / idle breathe
        bob.current.scale.set(1, 1, 1); bob.current.rotation.x = 0;
      }
    }
    if (legL.current && legR.current && shinL.current && shinR.current) {
      if (stepping) {
        legL.current.rotation.x = sw * 0.6; legR.current.rotation.x = -sw * 0.6;
        shinL.current.rotation.x = Math.max(0, -sw) * 1.2; shinR.current.rotation.x = Math.max(0, sw) * 1.2;
      } else if (hopping) {
        const tuck = Math.abs(Math.sin(t * 3)) * 0.8;
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
        const sway = Math.sin(t * (surfing ? 3 : 1.2)) * 0.15;
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
    // ── blink: a quick lid-close every ~3.4s (0.2s V-shaped dip) ──
    if (eyeL.current && eyeR.current) {
      const cyc = t % 3.4;
      let v = 1;
      if (cyc > 3.2) v = 0.1 + 0.9 * Math.abs((cyc - 3.2) / 0.2 - 0.5) * 2; // 1→0.1→1
      eyeL.current.scale.y = v; eyeR.current.scale.y = v;
    }

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
      s.position.set(noteXZ[i][0], y + 0.4, noteXZ[i][1]);
      const fade = y < 0.6 ? y / 0.6 : y > 1.9 ? (2.4 - y) / 0.5 : 1;
      (s.material as SpriteMaterial).opacity = Math.max(0, fade * 0.72);
    });
  });

  const SUIT = '#eef1f7';
  const SUIT_D = '#c7cede';
  const RED = '#da251d';   // VN flag red
  const GOLD = '#ffcd00';  // VN star gold
  const SKIN_SCREEN = '#121a30'; // dark visor screen the face sits on

  // First-person flight: we ARE the pilot → the body isn't drawn (cockpit shows hands).
  if (mode === 'journey' || mode === 'fly') return null;

  return (
    <group ref={root}>
      <group ref={bob}>
        {/* ── oversized helmet head (model faces +Z) ── */}
        <mesh position={[0, 0.56, 0]}>
          <sphereGeometry args={[0.5, 32, 32]} />
          <meshToonMaterial color={SUIT} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* dark visor screen the face reads on */}
        <mesh position={[0, 0.55, 0.31]} scale={[0.82, 0.66, 0.34]}>
          <sphereGeometry args={[0.42, 24, 24]} />
          <meshToonMaterial color={SKIN_SCREEN} gradientMap={ramp} emissive={accent} emissiveIntensity={0.12} />
        </mesh>
        {/* gold rim around the visor */}
        <mesh position={[0, 0.55, 0.30]} rotation={[0.1, 0, 0]}>
          <torusGeometry args={[0.3, 0.028, 12, 32]} />
          <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.3} />
        </mesh>

        {/* ── FACE: big shiny eyes + smile + rosy cheeks ── */}
        <group ref={eyeL} position={[-0.16, 0.6, 0.47]}>
          <mesh scale={[0.85, 1.15, 0.6]}>
            <sphereGeometry args={[0.095, 16, 16]} />
            <meshBasicMaterial color="#0c1020" />
          </mesh>
          <mesh position={[0.035, 0.045, 0.06]}>
            <sphereGeometry args={[0.032, 10, 10]} />
            <meshBasicMaterial color="#ffffff" />
          </mesh>
        </group>
        <group ref={eyeR} position={[0.16, 0.6, 0.47]}>
          <mesh scale={[0.85, 1.15, 0.6]}>
            <sphereGeometry args={[0.095, 16, 16]} />
            <meshBasicMaterial color="#0c1020" />
          </mesh>
          <mesh position={[0.035, 0.045, 0.06]}>
            <sphereGeometry args={[0.032, 10, 10]} />
            <meshBasicMaterial color="#ffffff" />
          </mesh>
        </group>
        {/* rosy cheeks */}
        <mesh position={[-0.26, 0.49, 0.41]} scale={[1, 0.72, 0.4]}>
          <sphereGeometry args={[0.063, 12, 12]} />
          <meshBasicMaterial color="#ff8fa6" transparent opacity={0.85} />
        </mesh>
        <mesh position={[0.26, 0.49, 0.41]} scale={[1, 0.72, 0.4]}>
          <sphereGeometry args={[0.063, 12, 12]} />
          <meshBasicMaterial color="#ff8fa6" transparent opacity={0.85} />
        </mesh>
        {/* smile (lower half of a thin torus arc) */}
        <mesh position={[0, 0.5, 0.46]} rotation={[Math.PI / 2, 0, Math.PI]}>
          <torusGeometry args={[0.06, 0.013, 8, 16, Math.PI]} />
          <meshBasicMaterial color="#0c1020" />
        </mesh>

        {/* gold star on the helmet crown */}
        <mesh position={[0, 0.92, 0.2]} rotation={[-0.55, 0, 0]}>
          <shapeGeometry args={[helmetStar]} />
          <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.8} side={DoubleSide} />
        </mesh>

        {/* ── blue headphones — band arcs from right ear over crown to left ear ── */}
        <group position={[0, 0.56, 0]}>
          {/* half-torus band: sweeps +X → +Y → -X (XY plane, no rotation needed) */}
          <mesh>
            <torusGeometry args={[0.52, 0.03, 8, 24, Math.PI]} />
            <meshToonMaterial color="#2277dd" gradientMap={ramp} />
          </mesh>
          {/* right ear cup — cylinder axis along X (rotation [0,0,π/2]) */}
          <mesh position={[0.52, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.09, 0.09, 0.08, 16]} />
            <meshToonMaterial color="#1a66cc" gradientMap={ramp} />
          </mesh>
          {/* left ear cup */}
          <mesh position={[-0.52, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.09, 0.09, 0.08, 16]} />
            <meshToonMaterial color="#1a66cc" gradientMap={ramp} />
          </mesh>
        </group>

        {/* neck ring */}
        <mesh position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.2, 0.05, 12, 24]} />
          <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
        </mesh>

        {/* ── round stubby torso (small, to exaggerate the big chibi head) ── */}
        <mesh position={[0, -0.04, 0]}>
          <capsuleGeometry args={[0.25, 0.1, 8, 16]} />
          <meshToonMaterial color={SUIT} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* chest control box + emotion indicator */}
        <mesh position={[0.02, 0.0, 0.27]}>
          <boxGeometry args={[0.16, 0.12, 0.05]} />
          <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
        </mesh>
        <mesh position={[0.05, 0.0, 0.31]}>
          <sphereGeometry args={[0.022, 12, 12]} />
          <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={1.8} />
        </mesh>
        {/* VN flag patch (red) + gold star, on the chest */}
        <mesh position={[-0.13, 0.04, 0.27]}>
          <planeGeometry args={[0.15, 0.1]} />
          <meshBasicMaterial color={RED} side={DoubleSide} />
        </mesh>
        <mesh position={[-0.13, 0.04, 0.281]}>
          <shapeGeometry args={[star]} />
          <meshBasicMaterial color={GOLD} side={DoubleSide} />
        </mesh>
        {/* small PLSS backpack */}
        <mesh position={[0, 0.0, -0.27]}>
          <boxGeometry args={[0.34, 0.34, 0.16]} />
          <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>

        {/* ── Đông Sơn brocade band (red waist belt + ring of gold studs) ── */}
        <mesh position={[0, -0.16, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.28, 0.04, 12, 32]} />
          <meshToonMaterial color={RED} gradientMap={ramp} />
        </mesh>
        {dongSon.map((a, i) => (
          <mesh key={i} position={[Math.cos(a) * 0.29, -0.16, Math.sin(a) * 0.29]} rotation={[0, -a, 0]}>
            <boxGeometry args={[0.028, 0.045, 0.028]} />
            <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.4} />
          </mesh>
        ))}

        {/* ── stubby arms (shoulder pivot) → red glove ── */}
        <group ref={armL} position={[-0.3, 0.12, 0]}>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.082, 0.1, 6, 12]} />
            <meshToonMaterial color={SUIT} gradientMap={ramp} />
            <Outlines {...OUTLINE} />
          </mesh>
          <mesh position={[0, -0.26, 0]}>
            <sphereGeometry args={[0.12, 16, 16]} />
            <meshToonMaterial color={RED} gradientMap={ramp} />
          </mesh>
        </group>
        <group ref={armR} position={[0.3, 0.12, 0]}>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.082, 0.1, 6, 12]} />
            <meshToonMaterial color={SUIT} gradientMap={ramp} />
            <Outlines {...OUTLINE} />
          </mesh>
          <mesh position={[0, -0.26, 0]}>
            <sphereGeometry args={[0.12, 16, 16]} />
            <meshToonMaterial color={RED} gradientMap={ramp} />
          </mesh>
        </group>

        {/* ── stubby legs: thigh (hip pivot) → shin (knee pivot) → boot ── */}
        <group ref={legL} position={[-0.13, -0.26, 0]}>
          <mesh position={[0, -0.08, 0]}>
            <capsuleGeometry args={[0.1, 0.08, 6, 12]} />
            <meshToonMaterial color={SUIT} gradientMap={ramp} />
          </mesh>
          <group ref={shinL} position={[0, -0.17, 0]}>
            <mesh position={[0, -0.07, 0]}>
              <capsuleGeometry args={[0.092, 0.07, 6, 12]} />
              <meshToonMaterial color={SUIT} gradientMap={ramp} />
            </mesh>
            <mesh position={[0, -0.15, 0.05]}>
              <boxGeometry args={[0.17, 0.11, 0.25]} />
              <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
            </mesh>
          </group>
        </group>
        <group ref={legR} position={[0.13, -0.26, 0]}>
          <mesh position={[0, -0.08, 0]}>
            <capsuleGeometry args={[0.1, 0.08, 6, 12]} />
            <meshToonMaterial color={SUIT} gradientMap={ramp} />
          </mesh>
          <group ref={shinR} position={[0, -0.17, 0]}>
            <mesh position={[0, -0.07, 0]}>
              <capsuleGeometry args={[0.092, 0.07, 6, 12]} />
              <meshToonMaterial color={SUIT} gradientMap={ramp} />
            </mesh>
            <mesh position={[0, -0.15, 0.05]}>
              <boxGeometry args={[0.17, 0.11, 0.25]} />
              <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
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
