import { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';
import Skydome from './Skydome';
import ColorOrb from './ColorOrb';
import MoodCore from './MoodCore';
import ParticleField from './ParticleField';

const HALF_X = 4.2;
const HALF_Y = 3.0;

// Map each colour's (V,A) into the explorable plane, fitting the data range so
// orbs spread evenly instead of clustering.
function useOrbLayout() {
  return useMemo(() => {
    const vs = EMOTION_COLORS.map((c) => c.v);
    const as = EMOTION_COLORS.map((c) => c.a);
    const vMin = Math.min(...vs), vMax = Math.max(...vs);
    const aMin = Math.min(...as), aMax = Math.max(...as);
    const norm = (x: number, lo: number, hi: number) => (hi - lo < 1e-6 ? 0.5 : (x - lo) / (hi - lo));
    return EMOTION_COLORS.map((c, i) => ({
      color: c,
      phase: i * 0.9,
      position: [
        (norm(c.v, vMin, vMax) - 0.5) * 2 * HALF_X,
        (norm(c.a, aMin, aMax) - 0.5) * 2 * HALF_Y,
        ((i % 3) - 1) * 0.7,
      ] as [number, number, number],
    }));
  }, []);
}

function Scene() {
  const orbs = useOrbLayout();
  const nowPlaying = useStore((s) => s.nowPlayingOpen);

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[0, 2, 8]} intensity={40} distance={40} decay={1.4} />
      <Skydome />

      {!nowPlaying &&
        orbs.map((o) => (
          <ColorOrb key={o.color.hex} color={o.color} position={o.position} phase={o.phase} />
        ))}

      <MoodCore visible={nowPlaying} />
      <ParticleField visible={nowPlaying} />

      <OrbitControls
        enablePan={false}
        enableZoom
        minDistance={5.5}
        maxDistance={15}
        rotateSpeed={0.5}
        zoomSpeed={0.6}
        autoRotate
        autoRotateSpeed={nowPlaying ? 0.6 : 0.32}
        enableDamping
        dampingFactor={0.06}
        minPolarAngle={0.6}
        maxPolarAngle={2.5}
      />
    </>
  );
}

export default function EmotionSpace() {
  return (
    <Canvas
      camera={{ position: [0, 0.4, 9], fov: 55, near: 0.1, far: 120 }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      style={{ position: 'fixed', inset: 0, zIndex: 0 }}
    >
      <Scene />
    </Canvas>
  );
}
