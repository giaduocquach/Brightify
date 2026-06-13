import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html, Outlines, Sparkles } from '@react-three/drei';
import { Color, DoubleSide, Group, Matrix4, Quaternion, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';
import { starShape } from './shapes';
import { toonRamp, OUTLINE } from './toon';

const SPEECH: Record<string, string> = {
  intro: 'Đi đâu hôm nay? ✨',
  system: 'Chạm vào một hành tinh nhé!',
};

// Distance (local units) from the model origin down to the soles — used to lift the
// runner so its feet sit on the planet surface instead of sinking in.
const FOOT_DROP = 0.62;

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
  const speech = SPEECH[mode];

  const star = useMemo(() => starShape(0.07, 0.03), []);
  const helmetStar = useMemo(() => starShape(0.13, 0.055), []);
  const dongSon = useMemo(() => Array.from({ length: 12 }, (_, i) => (i / 12) * Math.PI * 2), []);

  const tmp = useRef(new Vector3());
  const up = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const xAxis = useRef(new Vector3());
  const m4 = useRef(new Matrix4());
  const quat = useRef(new Quaternion());

  useFrame((state, dt) => {
    if (!root.current) return;
    const k = 1 - Math.pow(0.002, dt);
    const g = root.current;
    const t = state.clock.elapsedTime;

    const running = mode === 'explore' && solarRefs.runnerActive && !!sel[0];
    const waving = mode === 'intro';

    if (running) {
      const center = solarRefs.bodyPos[sel[0]];
      const size = bodyByHex(sel[0])?.size ?? 0.5;
      const scale = Math.max(0.1, size * 0.2);
      up.current.copy(solarRefs.runnerPos).sub(center ?? solarRefs.runnerPos).normalize();
      if (up.current.lengthSq() < 1e-4) up.current.set(0, 1, 0);
      tmp.current.copy(solarRefs.runnerPos).addScaledVector(up.current, FOOT_DROP * scale);
      g.position.lerp(tmp.current, k);
      fwd.current.copy(solarRefs.runnerForward).normalize();
      xAxis.current.copy(up.current).cross(fwd.current).normalize();
      fwd.current.copy(xAxis.current).cross(up.current).normalize();
      m4.current.makeBasis(xAxis.current, up.current, fwd.current);
      quat.current.setFromRotationMatrix(m4.current);
      g.quaternion.slerp(quat.current, k);
      g.scale.setScalar(scale);
    } else {
      tmp.current.set(-1.2, -0.95, -3.3).applyMatrix4(camera.matrixWorld);
      g.position.lerp(tmp.current, k);
      g.quaternion.slerp(camera.quaternion, k);
      g.scale.setScalar(0.44);
    }

    // ── animation cycle ──
    const cad = t * 12;            // running cadence ≈ 1.9 Hz
    const sw = Math.sin(cad);
    const impact = Math.max(0, -sw); // foot plant → squash

    if (bob.current) {
      bob.current.position.y = running ? Math.abs(Math.sin(cad)) * 0.05 : Math.sin(t * 2) * 0.035;
      // squash & stretch on the foot-plant while running; gentle breathe when idle
      const sq = running ? impact * 0.12 : Math.sin(t * 2) * 0.015;
      bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
    }
    if (legL.current && legR.current) {
      legL.current.rotation.x = running ? sw * 0.6 : 0;
      legR.current.rotation.x = running ? -sw * 0.6 : 0;
    }
    if (shinL.current && shinR.current) {
      shinL.current.rotation.x = running ? Math.max(0, -sw) * 1.2 : 0;
      shinR.current.rotation.x = running ? Math.max(0, sw) * 1.2 : 0;
    }
    if (armL.current && armR.current) {
      if (waving) {
        armR.current.rotation.z = -2.3; armR.current.rotation.x = Math.sin(t * 6) * 0.4;
        armL.current.rotation.z = 0.2; armL.current.rotation.x = 0;
      } else {
        const run = running ? sw * 0.5 : 0;
        armL.current.rotation.z = 0.2; armR.current.rotation.z = -0.2;
        armL.current.rotation.x = -run;
        armR.current.rotation.x = run;
      }
    }
    // ── blink: a quick lid-close every ~3.4s (0.2s V-shaped dip) ──
    if (eyeL.current && eyeR.current) {
      const cyc = t % 3.4;
      let v = 1;
      if (cyc > 3.2) v = 0.1 + 0.9 * Math.abs((cyc - 3.2) / 0.2 - 0.5) * 2; // 1→0.1→1
      eyeL.current.scale.y = v; eyeR.current.scale.y = v;
    }
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

        {speech && (
          <Html center distanceFactor={6} position={[1.0, 1.2, 0]} pointerEvents="none">
            <div className="astro-speech">{speech}</div>
          </Html>
        )}
      </group>

      {/* foot dust kicked up while running */}
      {mode === 'explore' && sel[0] && (
        <Sparkles count={14} scale={[0.9, 0.3, 0.9]} position={[0, -0.55, 0]}
          size={2.5} speed={0.6} color={accent} opacity={0.5} />
      )}
    </group>
  );
}
