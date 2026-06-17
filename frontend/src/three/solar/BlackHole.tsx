import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, type BufferAttribute, Color, DoubleSide, ShaderMaterial } from 'three';
import type { BodyDef } from './bodies';
import { glowTexture } from './glow';
import { solarRefs } from './refs';
import { useDeviceTier } from './deviceTier';
import { ATMO_VERT, ATMO_FRAG, DISK_VERT, DISK_FRAG } from '../shaders';

// Matter spiralling INWARD and vanishing at the event horizon — sells "the hole sucks
// everything in". CPU-updated points (deterministic) inside the tilted disk plane; the opaque
// black horizon sphere occludes them at the rim → they read as swallowed. High-tier only.
function InfallParticles({ size }: { size: number }) {
  const tex = glowTexture();
  const ref = useRef<BufferAttribute>(null);
  const N = 140;
  const { positions, seed, angle0, radius0 } = useMemo(() => {
    const positions = new Float32Array(N * 3);
    const seed = new Float32Array(N);
    const angle0 = new Float32Array(N);
    const radius0 = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      seed[i] = (i * 0.61803398875) % 1;            // golden-ratio → deterministic spread
      angle0[i] = i * 2.39996;
      radius0[i] = size * (3 + ((i % 10) / 10) * 3); // start between 3·size and 6·size
    }
    return { positions, seed, angle0, radius0 };
  }, [size]);

  useFrame((state) => {
    if (solarRefs.reducedMotion) return; // freeze the in-fall spiral
    const t = state.clock.elapsedTime;
    const horizon = size * 0.9;
    for (let i = 0; i < N; i++) {
      const p = (t * 0.12 * (0.5 + seed[i]) + seed[i]) % 1; // 0=outer → 1=horizon
      const radius = horizon + (radius0[i] - horizon) * (1 - p);
      const ang = angle0[i] + p * Math.PI * 2 * 3;          // 3 turns as it falls in
      positions[i * 3] = Math.cos(ang) * radius;
      positions[i * 3 + 1] = Math.sin(ang) * radius;
      positions[i * 3 + 2] = (seed[i] - 0.5) * size * 0.25; // thin disk jitter
    }
    if (ref.current) ref.current.needsUpdate = true;
  });

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute ref={ref} attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial map={tex} color="#ffce9e" size={size * 0.18} transparent opacity={0.8}
        blending={AdditiveBlending} depthWrite={false} sizeAttenuation />
    </points>
  );
}

// A black hole — the visual for the near-black #222222 emotion slot. A pure-black event
// horizon, a crisp bright photon ring (fresnel rim), and a swirling shader accretion disk
// (hot white-blue inner → orange → red outer, Doppler-brightened on one limb). The most
// dramatic "special" object — astrophysically real, so it still reads as realistic.
// No raymarching / gravitational lensing → cheap enough for the deploy perf budget.
export default function BlackHole({ def, selected }: { def: BodyDef; selected: boolean }) {
  const tex = glowTexture();
  const tier = useDeviceTier();
  const diskMat = useRef<ShaderMaterial>(null);

  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uInner: { value: def.size * 1.25 },
    uOuter: { value: def.size * 3.2 },
    uInnerSpeed: { value: 0.9 },
    uOuterSpeed: { value: 0.22 },
    uDoppler: { value: 0.55 },
    uDopplerDir: { value: 0.6 },
    uSelected: { value: 0 },
    uColHot: { value: new Color('#cfe0ff') },
    uColMid: { value: new Color('#ff9a3c') },
    uColOuter: { value: new Color('#b3260f') },
  }), [def.size]);

  // faint fresnel rim — keeps the hole readable when the screen-space lensing (which now owns
  // the bright Einstein ring + the dark void) is disabled on low tier. Softer than before.
  const ringMat = useMemo(() => new ShaderMaterial({
    vertexShader: ATMO_VERT,
    fragmentShader: ATMO_FRAG,
    uniforms: {
      uColor: { value: new Color('#fff0d0') },
      uIntensity: { value: 0.6 },
      uPower: { value: 5.0 },
    },
    transparent: true,
    blending: AdditiveBlending,
    depthWrite: false,
  }), []);

  useFrame((state) => {
    if (diskMat.current) {
      if (!solarRefs.reducedMotion) diskMat.current.uniforms.uTime.value = state.clock.elapsedTime;
      diskMat.current.uniforms.uSelected.value = selected ? 1 : 0;
    }
  });

  return (
    <group>
      {/* event horizon — pure black, opaque + writes depth so it occludes the far disk half.
          Slightly smaller than before so the screen-space lensing shadow reads as the dominant
          "hole". Still the raycast/click target via the CelestialBody wrapper group. */}
      <mesh>
        <sphereGeometry args={[def.size * 0.92, 48, 48]} />
        <meshBasicMaterial color="#000000" />
      </mesh>

      {/* faint photon-ring rim (the bright Einstein ring now comes from the lensing pass) */}
      <mesh material={ringMat}>
        <sphereGeometry args={[def.size, 48, 48]} />
      </mesh>

      {/* accretion disk + in-falling matter — tilted; the disk swirls, particles spiral in */}
      <group rotation={[1.3, 0, 0]}>
        <mesh>
          <ringGeometry args={[def.size * 1.25, def.size * 3.2, 128, 8]} />
          <shaderMaterial
            ref={diskMat}
            vertexShader={DISK_VERT}
            fragmentShader={DISK_FRAG}
            uniforms={uniforms}
            transparent
            blending={AdditiveBlending}
            side={DoubleSide}
            depthWrite={false}
          />
        </mesh>
        {tier === 'high' && <InfallParticles size={def.size} />}
      </group>

      {/* very faint outer glow (kept low so it reads as a void, not a glowing planet) */}
      <sprite scale={def.size * (selected ? 5 : 4)}>
        <spriteMaterial map={tex} color="#ff9a3c" transparent opacity={0.1} blending={AdditiveBlending} depthWrite={false} />
      </sprite>
    </group>
  );
}
