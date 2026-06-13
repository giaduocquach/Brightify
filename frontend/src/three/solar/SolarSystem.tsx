import { Suspense, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars, useTexture } from '@react-three/drei';
import { EffectComposer, Bloom, SMAA, Vignette } from '@react-three/postprocessing';
import { ACESFilmicToneMapping, AdditiveBlending, BackSide, Color, SRGBColorSpace, type Group, type Points } from 'three';
import { useStore } from '../../state/store';
import { BODIES, MILKYWAY_TEXTURE, OUTER_RADIUS } from './bodies';
import { textureUrl } from './textureUrls';
import { glowTexture } from './glow';
import CelestialBody from './CelestialBody';
import Sun from './Sun';
import OrbitRings from './OrbitRings';
import FocusController from './FocusController';
import Astronaut from './Astronaut';
import Spaceship from './Spaceship';
import Cockpit from './Cockpit';
import CockpitInterior from './CockpitInterior';
import WarpStreaks from './WarpStreaks';
import SurfaceRun from './SurfaceRun';
import FreeFlight from './FreeFlight';

const IS_MOBILE = typeof window !== 'undefined' && window.innerWidth < 768;
const DPR_MAX = IS_MOBILE ? 1.5 : 2;
const STAR_COUNT = IS_MOBILE ? 3500 : 6500;
const NEBULA_COUNT = IS_MOBILE ? 4 : 9;

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

// Soft far-field nebula clouds — big additive sprites that drift slowly and tint the
// void with colour (they catch the bloom pass, giving a glowing-gas feel). Deterministic
// placement (no Math.random) so it's stable across renders.
function Nebula() {
  const ref = useRef<Group>(null);
  const tex = glowTexture();
  const puffs = useMemo(() => {
    const HUES = ['#5b3fb0', '#2f6db0', '#b04f8a', '#2f9e8f'];
    return Array.from({ length: NEBULA_COUNT }, (_, i) => {
      const a = i * 2.39996;
      const r = 120 + (i % 4) * 28;
      return {
        pos: [Math.cos(a) * r, ((i * 0.31) % 2 - 1) * 70, Math.sin(a) * r] as [number, number, number],
        scale: 90 + (i % 5) * 26,
        color: new Color(HUES[i % HUES.length]),
        opacity: 0.1 + (i % 3) * 0.04,
      };
    });
  }, []);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * 0.004; });
  return (
    <group ref={ref}>
      {puffs.map((p, i) => (
        <sprite key={i} position={p.pos} scale={p.scale}>
          <spriteMaterial map={tex} color={p.color} transparent opacity={p.opacity}
            blending={AdditiveBlending} depthWrite={false} />
        </sprite>
      ))}
    </group>
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
  const flight = mode === 'journey' || mode === 'fly';

  return (
    <>
      <color attach="background" args={['#05050B']} />
      <Suspense fallback={null}>
        <MilkyWay />
      </Suspense>
      <Nebula />
      <Stars radius={180} depth={80} count={STAR_COUNT} factor={4} saturation={0} fade speed={0.5} />
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
      {flight && (
        <>
          <CockpitInterior />
          {!IS_MOBILE && <WarpStreaks />}
        </>
      )}

      <Astronaut />

      {/* One OrbitControls owns rotate + zoom in EVERY mode; FocusController only moves
          the focus point (Sun → planet → ship) so the user keeps their angle/zoom. */}
      <OrbitControls
        makeDefault
        enablePan={false}
        enableZoom
        enableRotate
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.55}
        zoomSpeed={0.7}
        minDistance={2}
        maxDistance={OUTER_RADIUS * 2.4}
        onChange={() => { (window as unknown as { __orbit?: number }).__orbit = ((window as unknown as { __orbit?: number }).__orbit ?? 0) + 1; }}
      />
      <FocusController />

      {/* Flicker-free postprocessing on macOS (Metal/ANGLE): the MSAA HDR framebuffer —
          both the composer's own (multisampling) and the canvas hardware one (gl.antialias)
          — flickers black. So we disable BOTH and anti-alias inside the composer with a
          cheap SMAA pass instead (the documented r3f postprocessing pattern). */}
      <EffectComposer enableNormalPass={false} multisampling={0}>
        {[
          <Bloom key="bloom" intensity={IS_MOBILE ? 0.4 : 0.55} luminanceThreshold={0.42}
            luminanceSmoothing={0.9} mipmapBlur radius={0.6} />,
          <Vignette key="vignette" eskil={false} offset={0.3} darkness={0.65} />,
          <SMAA key="smaa" />,
        ]}
      </EffectComposer>
    </>
  );
}

// Root of the immersive solar-system scene.
export default function SolarSystem() {
  return (
    <Canvas
      camera={{ position: [0, 16, 40], fov: 50, near: 0.1, far: 600 }}
      dpr={[1, DPR_MAX]}
      gl={{ antialias: false, powerPreference: 'high-performance', toneMapping: ACESFilmicToneMapping }}
      style={{ position: 'fixed', inset: 0, zIndex: 0 }}
    >
      <Scene />
    </Canvas>
  );
}
