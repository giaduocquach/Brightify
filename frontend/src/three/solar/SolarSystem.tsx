import { Suspense, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars, useTexture } from '@react-three/drei';
import { ACESFilmicToneMapping, BackSide, SRGBColorSpace, type Points } from 'three';
import { useStore } from '../../state/store';
import { BODIES, MILKYWAY_TEXTURE, OUTER_RADIUS } from './bodies';
import { textureUrl } from './textureUrls';
import CelestialBody from './CelestialBody';
import Sun from './Sun';
import OrbitRings from './OrbitRings';
import CameraRig from './CameraRig';
import Astronaut from './Astronaut';
import Spaceship from './Spaceship';
import Cockpit from './Cockpit';
import SurfaceRun from './SurfaceRun';
import FreeFlight from './FreeFlight';

const DPR_MAX = typeof window !== 'undefined' && window.innerWidth < 768 ? 1.5 : 2;

function MilkyWay() {
  const tex = useTexture(textureUrl(MILKYWAY_TEXTURE));
  tex.colorSpace = SRGBColorSpace;
  return (
    <mesh scale={320}>
      <sphereGeometry args={[1, 32, 32]} />
      <meshBasicMaterial map={tex} side={BackSide} depthWrite={false} />
    </mesh>
  );
}

// Slow-drifting dust motes — cheap parallax depth between the camera and the planets.
function Dust() {
  const ref = useRef<Points>(null);
  const positions = useMemo(() => {
    const N = 480;
    const arr = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const r = 26 + ((i * 37) % 64);
      const a = i * 2.39996;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = ((i * 0.137) % 2 - 1) * 38;
      arr[i * 3 + 2] = Math.sin(a) * r;
    }
    return arr;
  }, []);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * 0.006; });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.16} color="#9bb8ff" transparent opacity={0.45} sizeAttenuation depthWrite={false} />
    </points>
  );
}

function Scene() {
  const mode = useStore((s) => s.mode);
  const overview = mode === 'system' || mode === 'intro';

  return (
    <>
      <color attach="background" args={['#05050B']} />
      <Suspense fallback={null}>
        <MilkyWay />
      </Suspense>
      <Stars radius={180} depth={80} count={3500} factor={4} saturation={0} fade speed={0.5} />
      <Dust />

      {/* 3-point-ish lighting: the Sun is the key; a dim hemisphere + ambient fill the
          shadow side just enough to read, while keeping the night sides dramatic. */}
      <ambientLight intensity={0.12} />
      <hemisphereLight intensity={0.12} color="#9bb8ff" groundColor="#1a1026" />
      <pointLight position={[0, 0, 0]} intensity={680} distance={260} decay={1.5} color="#ffe6b0" />

      <Suspense fallback={null}>
        <Sun />
        {BODIES.map((b) => (
          <CelestialBody key={b.hex} def={b} />
        ))}
      </Suspense>
      <OrbitRings />

      {mode === 'explore' && <SurfaceRun />}
      {mode === 'journey' && (
        <>
          <Spaceship />
          <Cockpit />
        </>
      )}
      {mode === 'fly' && (
        <>
          <Spaceship />
          <FreeFlight />
        </>
      )}

      <Astronaut />
      <CameraRig />

      {/* Drag-to-orbit only in the overview; the cinematic rig drives the others. */}
      {overview && (
        <OrbitControls
          makeDefault
          enablePan={false}
          enableZoom
          enableRotate
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.55}
          zoomSpeed={0.7}
          minDistance={8}
          maxDistance={OUTER_RADIUS * 2.4}
          target={[0, 0, 0]}
          onChange={() => { (window as unknown as { __orbit?: number }).__orbit = ((window as unknown as { __orbit?: number }).__orbit ?? 0) + 1; }}
        />
      )}
    </>
  );
}

// Root of the immersive solar-system scene.
export default function SolarSystem() {
  return (
    <Canvas
      camera={{ position: [0, 16, 40], fov: 50, near: 0.1, far: 600 }}
      dpr={[1, DPR_MAX]}
      gl={{ antialias: true, powerPreference: 'high-performance', toneMapping: ACESFilmicToneMapping }}
      style={{ position: 'fixed', inset: 0, zIndex: 0 }}
    >
      <Scene />
    </Canvas>
  );
}
