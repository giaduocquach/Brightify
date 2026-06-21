import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, Color, DoubleSide, type ShaderMaterial } from 'three';
import { AURORA_VERT, AURORA_FRAG } from '../shaders';
import { solarRefs } from './refs';
import { vibeRefs } from '../vibe/vibeRefs';

// Scientifically-placed aurora: real auroras form in a planet's upper atmosphere where the
// magnetosphere funnels solar-wind particles to the POLES — they never float in open space. So
// this renders two curtain bands hugging the explored planet's poles (mounted inside the body's
// axial-tilt group, so they follow the spin axis). Vertical-curtain FBM (shared AURORA shader on
// open cylinders → uv.x around the pole = striations, uv.y = the band height). Opacity ramps with
// calm/happy mood (Q4/Q1); reduced-motion freezes the scroll but keeps a static glow.
export default function PlanetAurora({ size }: { size: number }) {
  const mats = useRef<(ShaderMaterial | null)[]>([]);
  const uniforms = useMemo(
    () => [0, 1].map((i) => ({
      uTime: { value: i * 7 }, uOpacity: { value: 0 }, uShimmer: { value: 1 },
      uColA: { value: new Color('#4fd2c2') }, uColB: { value: new Color('#7c6bff') },
    })),
    [],
  );

  useFrame((state) => {
    const v = vibeRefs.current;
    const op = Math.min(0.85, v.q4 * 0.9 + v.q1 * 0.5); // calm/happy show it; sad/intense fade to 0
    mats.current.forEach((m) => {
      if (!m) return;
      m.uniforms.uTime.value = solarRefs.reducedMotion ? 0 : state.clock.elapsedTime;
      m.uniforms.uOpacity.value = op;
      m.uniforms.uShimmer.value = 0.6 + v.arousal * 1.4;
      (m.uniforms.uColA.value as Color).copy(v.primary); // tint = mood colour
    });
  });

  const r = size * 0.58;   // auroral-oval radius (smaller than the equator → rings the pole)
  const h = size * 0.85;   // curtain height
  const y = size * 0.6;    // sit over each pole

  return (
    <>
      {[1, -1].map((s, i) => (
        <mesh key={s} position={[0, y * s, 0]}>
          <cylinderGeometry args={[r * (s > 0 ? 1.3 : 1), r * (s > 0 ? 1 : 1.3), h, 44, 1, true]} />
          <shaderMaterial
            ref={(el) => { mats.current[i] = el; }}
            vertexShader={AURORA_VERT}
            fragmentShader={AURORA_FRAG}
            uniforms={uniforms[i]}
            transparent
            depthWrite={false}
            blending={AdditiveBlending}
            side={DoubleSide}
          />
        </mesh>
      ))}
    </>
  );
}
