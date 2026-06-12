import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { Color, DoubleSide, Group, Matrix4, Quaternion, Shape, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';

const SPEECH: Record<string, string> = {
  intro: 'Đi đâu hôm nay? ✨',
  system: 'Chạm vào một hành tinh nhé!',
};

// A 5-point star (for the Vietnamese gold star on the flag patch + helmet).
function starShape(outer: number, inner: number, points = 5): Shape {
  const s = new Shape();
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 ? inner : outer;
    const a = (i / (points * 2)) * Math.PI * 2 - Math.PI / 2;
    const x = Math.cos(a) * r, y = Math.sin(a) * r;
    if (i === 0) s.moveTo(x, y); else s.lineTo(x, y);
  }
  s.closePath();
  return s;
}

// A realistic-but-stylized Vietnamese astronaut (no chibi big-head). Detailed suit,
// helmet with a gold visor + gold star, PLSS backpack, gloves and boots, plus VN
// identity: a red flag patch with the gold star on the chest and an Đông Sơn-style
// brocade band of gold studs at the waist. Animation states: idle / wave / run / sit.
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

  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const accent = useMemo(() => new Color(sel[0] || '#7cc7ff'), [sel]);
  const speech = SPEECH[mode];

  const star = useMemo(() => starShape(0.09, 0.038), []);
  const helmetStar = useMemo(() => starShape(0.12, 0.05), []);
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

    const seated = mode === 'journey' || mode === 'fly';
    const running = mode === 'explore' && solarRefs.runnerActive && !!sel[0];
    const waving = mode === 'intro';

    if (running) {
      const center = solarRefs.bodyPos[sel[0]];
      const size = bodyByHex(sel[0])?.size ?? 0.5;
      g.position.lerp(solarRefs.runnerPos, k);
      up.current.copy(solarRefs.runnerPos).sub(center ?? solarRefs.runnerPos).normalize();
      if (up.current.lengthSq() < 1e-4) up.current.set(0, 1, 0);
      fwd.current.copy(solarRefs.runnerForward).normalize();
      xAxis.current.copy(up.current).cross(fwd.current).normalize();
      fwd.current.copy(xAxis.current).cross(up.current).normalize();
      m4.current.makeBasis(xAxis.current, up.current, fwd.current);
      quat.current.setFromRotationMatrix(m4.current);
      g.quaternion.slerp(quat.current, k);
      g.scale.setScalar(Math.max(0.28, size * 0.5));
    } else if (seated) {
      g.position.lerp(solarRefs.shipPos, 1 - Math.pow(0.002, dt));
      fwd.current.copy(solarRefs.shipForward).normalize();
      if (fwd.current.lengthSq() < 1e-4) fwd.current.set(0, 0, 1);
      xAxis.current.set(0, 1, 0).cross(fwd.current).normalize();
      up.current.copy(fwd.current).cross(xAxis.current).normalize();
      m4.current.makeBasis(xAxis.current, up.current, fwd.current);
      quat.current.setFromRotationMatrix(m4.current);
      g.quaternion.slerp(quat.current, k);
      g.scale.setScalar(0.4);
    } else {
      tmp.current.set(-1.25, -0.95, -3.4).applyMatrix4(camera.matrixWorld);
      g.position.lerp(tmp.current, k);
      g.quaternion.slerp(camera.quaternion, k);
      g.scale.setScalar(0.52);
    }

    // ── animation cycle ──
    const cad = t * 12;            // running cadence ≈ 1.9 Hz
    const sw = Math.sin(cad);
    const sit = seated ? -1.3 : 0;

    // body bobs twice per stride while running; gentle float when idle
    if (bob.current) {
      bob.current.position.y = running ? Math.abs(Math.sin(cad)) * 0.06
        : seated ? 0 : Math.sin(t * 2) * 0.04;
    }
    // thighs swing; shins bend on the back-swing (knee), or fold when seated
    if (legL.current && legR.current) {
      legL.current.rotation.x = sit + (running ? sw * 0.6 : 0);
      legR.current.rotation.x = sit - (running ? sw * 0.6 : 0);
    }
    if (shinL.current && shinR.current) {
      shinL.current.rotation.x = running ? Math.max(0, -sw) * 1.2 : seated ? 1.15 : 0;
      shinR.current.rotation.x = running ? Math.max(0, sw) * 1.2 : seated ? 1.15 : 0;
    }
    // arms counter-swing the legs; raised wave on intro
    if (armL.current && armR.current) {
      if (waving) {
        armR.current.rotation.z = -2.3; armR.current.rotation.x = Math.sin(t * 6) * 0.4;
        armL.current.rotation.z = 0.15; armL.current.rotation.x = 0;
      } else {
        const run = running ? sw * 0.5 : 0;
        const seatA = seated ? 0.5 : 0;
        armL.current.rotation.z = 0.15; armR.current.rotation.z = -0.15;
        armL.current.rotation.x = -run + seatA;
        armR.current.rotation.x = run + seatA;
      }
    }
  });

  const SUIT = '#eef1f7';
  const SUIT_D = '#c7cede';
  const RED = '#da251d';   // VN flag red
  const GOLD = '#ffcd00';  // VN star gold

  // First-person flight: we ARE the pilot, so the body isn't drawn.
  if (mode === 'journey' || mode === 'fly') return null;

  return (
    <group ref={root}>
      <group ref={bob}>
        {/* ── head / helmet ── (model faces +Z) */}
        <mesh position={[0, 0.74, 0]}>
          <sphereGeometry args={[0.34, 32, 32]} />
          <meshStandardMaterial color={SUIT} roughness={0.35} metalness={0.15} />
        </mesh>
        {/* gold visor */}
        <mesh position={[0, 0.72, 0.18]} scale={[0.82, 0.62, 0.5]}>
          <sphereGeometry args={[0.3, 24, 24]} />
          <meshStandardMaterial color="#3a2e0a" roughness={0.08} metalness={0.9}
            emissive={accent} emissiveIntensity={0.35} />
        </mesh>
        {/* gold star on the helmet crown */}
        <mesh position={[0, 0.96, 0.16]} rotation={[-0.5, 0, 0]}>
          <shapeGeometry args={[helmetStar]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.7} side={DoubleSide} />
        </mesh>
        {/* neck ring */}
        <mesh position={[0, 0.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.22, 0.05, 12, 24]} />
          <meshStandardMaterial color={SUIT_D} metalness={0.6} roughness={0.4} />
        </mesh>

        {/* ── torso ── */}
        <mesh position={[0, 0.16, 0]}>
          <capsuleGeometry args={[0.27, 0.5, 8, 16]} />
          <meshStandardMaterial color={SUIT} roughness={0.55} metalness={0.1} />
        </mesh>
        {/* chest control box + emotion indicator */}
        <mesh position={[0, 0.2, 0.26]}>
          <boxGeometry args={[0.2, 0.16, 0.06]} />
          <meshStandardMaterial color={SUIT_D} roughness={0.5} />
        </mesh>
        <mesh position={[0.04, 0.2, 0.3]}>
          <sphereGeometry args={[0.025, 12, 12]} />
          <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={1.6} />
        </mesh>
        {/* VN flag patch (red) + gold star, on the chest */}
        <mesh position={[-0.12, 0.26, 0.27]}>
          <planeGeometry args={[0.16, 0.11]} />
          <meshStandardMaterial color={RED} roughness={0.6} side={DoubleSide} />
        </mesh>
        <mesh position={[-0.12, 0.26, 0.281]}>
          <shapeGeometry args={[star]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.5} side={DoubleSide} />
        </mesh>
        {/* PLSS backpack */}
        <mesh position={[0, 0.18, -0.28]}>
          <boxGeometry args={[0.42, 0.6, 0.22]} />
          <meshStandardMaterial color={SUIT_D} roughness={0.6} metalness={0.2} />
        </mesh>

        {/* ── Đông Sơn brocade band (red waist belt + ring of gold studs) ── */}
        <mesh position={[0, -0.12, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.28, 0.045, 12, 32]} />
          <meshStandardMaterial color={RED} roughness={0.5} metalness={0.2} />
        </mesh>
        {dongSon.map((a, i) => (
          <mesh key={i} position={[Math.cos(a) * 0.3, -0.12, Math.sin(a) * 0.3]} rotation={[0, -a, 0]}>
            <boxGeometry args={[0.03, 0.05, 0.03]} />
            <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.35} />
          </mesh>
        ))}

        {/* ── arms (shoulder pivot) → glove ── */}
        <group ref={armL} position={[-0.32, 0.42, 0]}>
          <mesh position={[0, -0.24, 0]}>
            <capsuleGeometry args={[0.095, 0.4, 6, 12]} />
            <meshStandardMaterial color={SUIT} roughness={0.55} />
          </mesh>
          <mesh position={[0, -0.5, 0]}>
            <sphereGeometry args={[0.1, 16, 16]} />
            <meshStandardMaterial color={RED} roughness={0.5} />
          </mesh>
        </group>
        <group ref={armR} position={[0.32, 0.42, 0]}>
          <mesh position={[0, -0.24, 0]}>
            <capsuleGeometry args={[0.095, 0.4, 6, 12]} />
            <meshStandardMaterial color={SUIT} roughness={0.55} />
          </mesh>
          <mesh position={[0, -0.5, 0]}>
            <sphereGeometry args={[0.1, 16, 16]} />
            <meshStandardMaterial color={RED} roughness={0.5} />
          </mesh>
        </group>

        {/* ── legs: thigh (hip pivot) → shin (knee pivot) → boot ── */}
        <group ref={legL} position={[-0.13, -0.2, 0]}>
          <mesh position={[0, -0.15, 0]}>
            <capsuleGeometry args={[0.115, 0.24, 6, 12]} />
            <meshStandardMaterial color={SUIT} roughness={0.55} />
          </mesh>
          <group ref={shinL} position={[0, -0.32, 0]}>
            <mesh position={[0, -0.13, 0]}>
              <capsuleGeometry args={[0.1, 0.22, 6, 12]} />
              <meshStandardMaterial color={SUIT} roughness={0.55} />
            </mesh>
            <mesh position={[0, -0.28, 0.05]}>
              <boxGeometry args={[0.16, 0.1, 0.24]} />
              <meshStandardMaterial color={SUIT_D} roughness={0.6} />
            </mesh>
          </group>
        </group>
        <group ref={legR} position={[0.13, -0.2, 0]}>
          <mesh position={[0, -0.15, 0]}>
            <capsuleGeometry args={[0.115, 0.24, 6, 12]} />
            <meshStandardMaterial color={SUIT} roughness={0.55} />
          </mesh>
          <group ref={shinR} position={[0, -0.32, 0]}>
            <mesh position={[0, -0.13, 0]}>
              <capsuleGeometry args={[0.1, 0.22, 6, 12]} />
              <meshStandardMaterial color={SUIT} roughness={0.55} />
            </mesh>
            <mesh position={[0, -0.28, 0.05]}>
              <boxGeometry args={[0.16, 0.1, 0.24]} />
              <meshStandardMaterial color={SUIT_D} roughness={0.6} />
            </mesh>
          </group>
        </group>

        {speech && (
          <Html center distanceFactor={6} position={[1.1, 1.3, 0]} pointerEvents="none">
            <div className="astro-speech">{speech}</div>
          </Html>
        )}
      </group>
    </group>
  );
}
