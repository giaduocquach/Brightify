import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import {
  AdditiveBlending, Vector3,
  type Points, type Sprite, type SpriteMaterial, type PointsMaterial,
} from 'three';
import { glowTexture } from '../solar/glow';
import { solarRefs } from '../solar/refs';
import { vibeRefs } from './vibeRefs';

// In-scene cosmic set-pieces that ramp in/out with the song's mood weights (already smoothed in
// vibeRefs, so opacity fades are graceful — no hysteresis needed). All deterministic placement
// (golden-angle, no Math.random) and reduced-motion gated (motion freezes; opacity/mood stays).
//   Q1 vui/sôi động → meteor shower      Q3 buồn → drifting stardust + a lone distant star
//   Q2 mãnh liệt    → rising embers       Q1/Q4 → aurora curtains   (embers/aurora = heavy tier)

const TEX = () => glowTexture();

// ── Q3: slow indigo stardust raining down ───────────────────────────────────
function Stardust() {
  const ref = useRef<Points>(null);
  const matRef = useRef<PointsMaterial>(null);
  const N = 140;
  const positions = useMemo(() => {
    const a = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const g = i * 2.39996, r = 8 + ((i * 53) % 60);
      a[i * 3] = Math.cos(g) * r; a[i * 3 + 1] = ((i * 0.137) % 2 - 1) * 40; a[i * 3 + 2] = Math.sin(g) * r;
    }
    return a;
  }, []);
  useFrame((_, dt) => {
    if (matRef.current) matRef.current.opacity = 0.5 * vibeRefs.current.q3;
    const pts = ref.current;
    if (!pts || solarRefs.reducedMotion) return;
    const arr = pts.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < N; i++) { arr[i * 3 + 1] -= dt * 1.2; if (arr[i * 3 + 1] < -40) arr[i * 3 + 1] = 40; }
    pts.geometry.attributes.position.needsUpdate = true;
  });
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial ref={matRef} map={TEX()} color="#9fb6ff" size={0.5} transparent opacity={0}
        alphaTest={0.02} sizeAttenuation depthWrite={false} />
    </points>
  );
}

// ── Q3: a single bright, slowly-pulsing far star ────────────────────────────
function LoneStar() {
  const matRef = useRef<SpriteMaterial>(null);
  useFrame((state) => {
    if (!matRef.current) return;
    const pulse = solarRefs.reducedMotion ? 1 : 0.8 + 0.2 * Math.sin(state.clock.elapsedTime * 0.6);
    matRef.current.opacity = vibeRefs.current.q3 * 0.9 * pulse;
  });
  return (
    <sprite position={[42, 24, -64]} scale={6}>
      <spriteMaterial ref={matRef} map={TEX()} color="#cfe0ff" transparent opacity={0}
        blending={AdditiveBlending} depthWrite={false} />
    </sprite>
  );
}

// ── Q1: shooting-star shower (sprites streaked along a fall direction, faster on the beat) ──
const FALL = new Vector3(-0.6, -1, -0.2).normalize();
function MeteorShower() {
  const refs = useRef<(Sprite | null)[]>([]);
  const N = 18;
  const starts = useMemo(
    () => Array.from({ length: N }, (_, i) => {
      const g = i * 2.39996;
      return new Vector3(Math.cos(g) * 50, 35 + ((i * 7) % 20), Math.sin(g) * 50);
    }),
    [],
  );
  const prog = useRef(new Float32Array(Array.from({ length: N }, (_, i) => (i * 0.137) % 1)));
  useFrame((_, dt) => {
    const { q1, beat } = vibeRefs.current;
    const adv = solarRefs.reducedMotion ? 0 : dt * (0.18 + beat * 0.6);
    refs.current.forEach((s, i) => {
      if (!s) return;
      s.visible = q1 > 0.04;
      if (!s.visible) return;
      let p = prog.current[i] + adv; if (p > 1) p -= 1; prog.current[i] = p;
      s.position.set(starts[i].x + FALL.x * p * 90, starts[i].y + FALL.y * p * 90, starts[i].z + FALL.z * p * 90);
      const fade = p < 0.1 ? p / 0.1 : (1 - p) / 0.9; // bright burst then taper
      (s.material as SpriteMaterial).opacity = Math.max(0, fade) * q1 * (0.6 + beat * 0.4);
    });
  });
  return (
    <>
      {starts.map((st, i) => (
        <sprite key={i} ref={(el) => { refs.current[i] = el; }} position={st} scale={[0.18, 2.4, 1]}>
          <spriteMaterial map={TEX()} color="#fff3c0" transparent opacity={0}
            blending={AdditiveBlending} depthWrite={false} />
        </sprite>
      ))}
    </>
  );
}

// ── Q2: rising orange embers (heavy tier) ───────────────────────────────────
function Embers() {
  const ref = useRef<Points>(null);
  const matRef = useRef<PointsMaterial>(null);
  const N = 70;
  const positions = useMemo(() => {
    const a = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const g = i * 2.39996, r = 4 + ((i * 37) % 30);
      a[i * 3] = Math.cos(g) * r; a[i * 3 + 1] = ((i * 0.21) % 2 - 1) * 20; a[i * 3 + 2] = Math.sin(g) * r;
    }
    return a;
  }, []);
  useFrame((_, dt) => {
    if (matRef.current) matRef.current.opacity = 0.7 * vibeRefs.current.q2;
    const pts = ref.current;
    if (!pts || solarRefs.reducedMotion) return;
    const arr = pts.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < N; i++) { arr[i * 3 + 1] += dt * (1.5 + (i % 3)); if (arr[i * 3 + 1] > 20) arr[i * 3 + 1] = -20; }
    pts.geometry.attributes.position.needsUpdate = true;
  });
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial ref={matRef} map={TEX()} color="#ff7a2c" size={0.45} transparent opacity={0}
        alphaTest={0.02} sizeAttenuation depthWrite={false} />
    </points>
  );
}

// NOTE: aurora is NOT here — auroras are a planetary-atmosphere phenomenon (polar, magnetosphere-
// funnelled), so it lives in PlanetAurora wrapped around the explored planet's poles, not floating
// in open space.
export default function VibeEffects({ heavy }: { heavy: boolean }) {
  return (
    <>
      <Stardust />
      <LoneStar />
      <MeteorShower />
      {heavy && <Embers />}
    </>
  );
}
