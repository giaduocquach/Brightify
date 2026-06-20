import { Suspense, useMemo, useRef, useState, type ReactElement } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerformanceMonitor, Stars, useTexture, usePerformanceMonitor } from '@react-three/drei';
import { EffectComposer, Bloom, GodRays, SMAA, Vignette } from '@react-three/postprocessing';
import { ACESFilmicToneMapping, AdditiveBlending, BackSide, Color, type Mesh, type PerspectiveCamera, SRGBColorSpace, type Group, type Points, type ShaderMaterial, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { BODIES, CAMERA_START, MILKYWAY_TEXTURE, OUTER_RADIUS, bodyByHex } from './bodies';
import { textureUrl } from './textureUrls';
import { glowTexture, nebulaTexture } from './glow';
import { solarRefs } from './refs';
import { useDeviceTier } from './deviceTier';
import { STAR_VERT, STAR_FRAG } from '../shaders';
import { LensingEffectImpl } from './LensingEffect';
import CelestialBody from './CelestialBody';
import Sun from './Sun';
import OrbitRings from './OrbitRings';
import FocusController from './FocusController';
import Astronaut from './Astronaut';
import Spaceship from './Spaceship';
import CockpitInterior from './CockpitInterior';
import SurfaceRun from './SurfaceRun';
import BoardingSequence from './BoardingSequence';
import FreeFlight from './FreeFlight';
import EnvMap from './EnvMap';

const IS_MOBILE = typeof window !== 'undefined' && window.innerWidth < 768;
const DPR_MAX = IS_MOBILE ? 1.5 : 2;
const STAR_COUNT = IS_MOBILE ? 3500 : 6500;
const COLOR_STARS = IS_MOBILE ? 500 : 1300;
const NEBULA_COUNT = IS_MOBILE ? 4 : 11;

function MilkyWay() {
  const tex = useTexture(textureUrl(MILKYWAY_TEXTURE));
  tex.colorSpace = SRGBColorSpace;
  // Dim the backdrop a touch so the galactic band sits just UNDER the bloom threshold —
  // the planets, accretion disk and comet coma stay the bright "heroes", not the sky.
  return (
    <mesh scale={320}>
      <sphereGeometry args={[1, 48, 48]} />
      <meshBasicMaterial map={tex} color="#cfcfcf" side={BackSide} depthWrite={false} />
    </mesh>
  );
}

// Far-field nebula — additive cloud sprites in three drifting shells (parallax) tinting the
// void with colour (they catch the bloom pass for a glowing-gas feel). A wispier texture +
// more hues + layered depth read as real nebulosity. Deterministic placement (no Math.random).
function Nebula() {
  const layers = useRef<(Group | null)[]>([]);
  const tex = nebulaTexture();
  const shells = useMemo(() => {
    const HUES = ['#5b3fb0', '#2f6db0', '#b04f8a', '#2f9e8f', '#c8923f', '#7d3fb0', '#2f86b0'];
    const perShell = Math.max(2, Math.round(NEBULA_COUNT / 3));
    return [0, 1, 2].map((shell) => {
      const baseR = 105 + shell * 45;
      const puffs = Array.from({ length: perShell }, (_, i) => {
        const idx = shell * perShell + i;
        const a = idx * 2.39996;
        const r = baseR + (i % 3) * 20;
        return {
          pos: [Math.cos(a) * r, ((idx * 0.31) % 2 - 1) * 60, Math.sin(a) * r] as [number, number, number],
          scale: 80 + (idx % 5) * 30,
          color: new Color(HUES[idx % HUES.length]),
          opacity: 0.08 + (idx % 3) * 0.035,
        };
      });
      return { puffs, speed: 0.004 * (1 - shell * 0.25) }; // outer shells drift slower → parallax
    });
  }, []);
  useFrame((state, dt) => {
    if (solarRefs.reducedMotion) return;
    const tt = state.clock.elapsedTime;
    layers.current.forEach((g, i) => {
      if (!g) return;
      g.rotation.y += dt * shells[i].speed;
      g.position.y = Math.sin(tt * 0.02 + i) * 2; // slow vertical parallax breathing
    });
  });
  return (
    <>
      {shells.map((s, si) => (
        <group key={si} ref={(el) => { layers.current[si] = el; }}>
          {s.puffs.map((p, i) => (
            <sprite key={i} position={p.pos} scale={p.scale}>
              <spriteMaterial map={tex} color={p.color} transparent opacity={p.opacity}
                blending={AdditiveBlending} depthWrite={false} />
            </sprite>
          ))}
        </group>
      ))}
    </>
  );
}

// A layer of COLOURED stars (blue/white/warm) for depth + realism — real starfields are
// not monochrome. Deterministic golden-spiral placement on a large shell, per-star colour,
// size and brightness, very slow drift. On high tier the points twinkle subtly + a few bright
// "hero" stars stand out (shader); low tier keeps a static pointsMaterial (no per-frame work).
function ColorStars() {
  const ref = useRef<Points>(null);
  const matRef = useRef<ShaderMaterial>(null);
  const tier = useDeviceTier();
  const gl = useThree((s) => s.gl);
  const [positions, colors, phases, sizes] = useMemo(() => {
    const pos = new Float32Array(COLOR_STARS * 3);
    const col = new Float32Array(COLOR_STARS * 3);
    const pha = new Float32Array(COLOR_STARS);
    const siz = new Float32Array(COLOR_STARS);
    const pal = [[0.65, 0.78, 1.0], [1, 1, 1], [1, 1, 1], [1, 0.93, 0.78], [1, 0.78, 0.6], [0.8, 0.86, 1]];
    for (let i = 0; i < COLOR_STARS; i++) {
      const y = 1 - (i / (COLOR_STARS - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const a = i * 2.39996;
      const rad = 150 + ((i * 53) % 70);
      pos[i * 3] = Math.cos(a) * r * rad;
      pos[i * 3 + 1] = y * rad;
      pos[i * 3 + 2] = Math.sin(a) * r * rad;
      const c = pal[(i * 7) % pal.length];
      const b = 0.55 + ((i * 13) % 45) / 100;
      col[i * 3] = c[0] * b; col[i * 3 + 1] = c[1] * b; col[i * 3 + 2] = c[2] * b;
      pha[i] = (i * 1.7) % 6.283;
      // a few bright "hero" stars, most small
      siz[i] = (i % 80 === 0) ? 4.5 + (i % 3) : 1.0 + ((i * 29) % 80) / 100;
    }
    return [pos, col, pha, siz];
  }, []);
  useFrame((state) => {
    if (solarRefs.reducedMotion) return; // freeze drift + twinkle
    if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * 0.003;
    if (matRef.current) matRef.current.uniforms.uTime.value = state.clock.elapsedTime;
  });
  const uniforms = useMemo(() => ({ uTime: { value: 0 }, uPixelRatio: { value: gl.getPixelRatio() } }), [gl]);
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        <bufferAttribute attach="attributes-aPhase" args={[phases, 1]} />
        <bufferAttribute attach="attributes-aSize" args={[sizes, 1]} />
      </bufferGeometry>
      {tier === 'high' ? (
        <shaderMaterial ref={matRef} vertexShader={STAR_VERT} fragmentShader={STAR_FRAG}
          uniforms={uniforms} transparent depthWrite={false} />
      ) : (
        <pointsMaterial map={glowTexture()} size={1.4} vertexColors transparent opacity={0.9}
          alphaTest={0.02} sizeAttenuation depthWrite={false} />
      )}
    </points>
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
  useFrame((_, dt) => { if (ref.current && !solarRefs.reducedMotion) ref.current.rotation.y += dt * 0.006; });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      {/* round soft motes (map gives a circular alpha → no square GL-point quads) */}
      <pointsMaterial map={glowTexture()} size={0.5} color="#9bb8ff" transparent opacity={0.4}
        alphaTest={0.02} sizeAttenuation depthWrite={false} />
    </points>
  );
}

// Smoothstep on [a,b] → [0,1].
function smoothstep01(a: number, b: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

// Gravitational-lensing pass: owns the effect instance directly (via useMemo) and renders it
// as a <primitive> so the EffectComposer collects it — same pattern GodRays uses, avoiding the
// wrapEffect JSON.stringify(props) crash. Each frame it projects the black hole (#222222) to
// screen space and feeds the effect position / apparent radius / strength (→0 off-screen/far).
function LensingPass() {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const effect = useMemo(() => new LensingEffectImpl(), []);
  const v = useMemo(() => new Vector3(), []);
  const hole = useMemo(() => bodyByHex('#222222'), []);
  useFrame(() => {
    const pos = solarRefs.bodyPos['#222222'];
    if (!pos || !hole) { effect.set(0.5, 0.5, 0.12, 0); return; }
    v.copy(pos).project(camera);
    const ux = v.x * 0.5 + 0.5;
    const uy = v.y * 0.5 + 0.5;
    const onScreen = v.z < 1 && ux > -0.3 && ux < 1.3 && uy > -0.3 && uy < 1.3;
    const dist = camera.position.distanceTo(pos);
    const worldR = hole.size * 3.2;                       // covers the accretion disk extent (matches uOuter)
    const fov = (camera.fov * Math.PI) / 180;
    const screenR = worldR / dist / (2 * Math.tan(fov / 2)); // apparent radius in UV-Y units
    const strength = onScreen ? 1 - smoothstep01(60, 170, dist) : 0;
    effect.set(ux, uy, Math.min(screenR, 0.45), strength);
  });
  return <primitive object={effect} dispose={null} />;
}

function Scene() {
  const mode = useStore((s) => s.mode);
  const reducedMotion = useStore((s) => s.reducedMotion);
  const flight = mode === 'journey' || mode === 'fly';
  const tier = useDeviceTier();
  const [degraded, setDegraded] = useState(false);
  const [sunMesh, setSunMesh] = useState<Mesh | null>(null);
  usePerformanceMonitor({ onDecline: () => setDegraded(true) });
  const heavy = tier === 'high' && !IS_MOBILE && !degraded;
  const lensOn = heavy;
  const godRaysOn = heavy && !flight && !!sunMesh; // rays only when the Sun is framed in space

  return (
    <>
      <color attach="background" args={['#05050B']} />
      <Suspense fallback={null}>
        <MilkyWay />
        <EnvMap />
      </Suspense>
      <Nebula />
      {!flight && <Stars radius={180} depth={80} count={STAR_COUNT} factor={4} saturation={0} fade speed={reducedMotion ? 0 : 0.5} />}
      <ColorStars />
      <Dust />

      {/* 3-point-ish lighting: the Sun is the key; a dim hemisphere + ambient fill the
          shadow side just enough to read, while keeping the night sides dramatic. */}
      <ambientLight intensity={0.15} />
      <hemisphereLight intensity={0.14} color="#9bb8ff" groundColor="#1a1026" />
      <pointLight position={[0, 0, 0]} intensity={680} distance={260} decay={1.5} color="#ffe6b0" />

      <Suspense fallback={null}>
        <Sun onReady={setSunMesh} />
        {BODIES.map((b) => (
          <CelestialBody key={b.hex} def={b} />
        ))}
      </Suspense>
      <OrbitRings />

      {(mode === 'explore' || mode === 'boarding') && <SurfaceRun />}
      {mode === 'boarding' && <Suspense fallback={null}><BoardingSequence /></Suspense>}
      {mode === 'journey' && <Spaceship />}
      {mode === 'fly' && (
        <>
          <Spaceship />
          <FreeFlight />
        </>
      )}
      {flight && <CockpitInterior />}

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
          cheap SMAA pass instead (the documented r3f postprocessing pattern).
          Lensing runs FIRST so the bent disk + Einstein ring feed into Bloom. */}
      <EffectComposer enableNormalPass={false} multisampling={0}>
        {[
          lensOn ? <LensingPass key="lens" /> : null,
          godRaysOn && sunMesh
            ? <GodRays key="godrays" sun={sunMesh} samples={60} density={0.92} decay={0.9}
                weight={0.3} exposure={0.4} clampMax={0.85} blur />
            : null,
          <Bloom key="bloom" intensity={godRaysOn ? 0.4 : (IS_MOBILE ? 0.38 : 0.5)} luminanceThreshold={0.5}
            luminanceSmoothing={0.9} mipmapBlur radius={0.6} />,
          <Vignette key="vignette" eskil={false} offset={0.3} darkness={0.65} />,
          <SMAA key="smaa" />,
        ].filter(Boolean) as ReactElement[]}
      </EffectComposer>
    </>
  );
}

// Root of the immersive solar-system scene. PerformanceMonitor steps the resolution (DPR)
// down on sustained frame-rate decline, so weak devices / heavy moments stay smooth.
export default function SolarSystem() {
  const [dpr, setDpr] = useState(DPR_MAX);
  return (
    <Canvas
      camera={{ position: CAMERA_START, fov: 50, near: 0.1, far: 600 }}
      dpr={dpr}
      gl={{ antialias: false, powerPreference: 'high-performance', toneMapping: ACESFilmicToneMapping }}
      style={{ position: 'fixed', inset: 0, zIndex: 0 }}
    >
      <PerformanceMonitor onDecline={() => setDpr((d) => Math.max(1, +(d - 0.5).toFixed(1)))}>
        <Scene />
      </PerformanceMonitor>
    </Canvas>
  );
}
