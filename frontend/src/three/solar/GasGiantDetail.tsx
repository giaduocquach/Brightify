import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, Color, type ShaderMaterial } from 'three';
import type { BodyDef } from './bodies';
import type { GiantParams } from './giantConfig';
import { solarRefs } from './refs';
import { GIANT_VERT, GIANT_FRAG } from '../shaders';

// A thin additive shell over an ice giant adding faint bands + streaks + limb haze, so Uranus/
// Neptune read as real atmospheres rather than flat discs. Rendered inside the planet's spin
// group (rotates with it), just above the surface. Mirrors the BlackHole shader-shell pattern.
export default function GasGiantDetail({ def, params }: { def: BodyDef; params: GiantParams }) {
  const matRef = useRef<ShaderMaterial>(null);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uBandStrength: { value: params.bandStrength },
    uBandFreq: { value: params.bandFreq },
    uStreakStrength: { value: params.streakStrength },
    uOpacity: { value: params.detailOpacity },
    uTint: { value: new Color(params.tint) },
  }), [params]);

  useFrame((s) => { if (matRef.current && !solarRefs.reducedMotion) matRef.current.uniforms.uTime.value = s.clock.elapsedTime; });

  return (
    <mesh scale={def.size * 1.012}>
      <sphereGeometry args={[1, 48, 48]} />
      <shaderMaterial ref={matRef} vertexShader={GIANT_VERT} fragmentShader={GIANT_FRAG}
        uniforms={uniforms} transparent blending={AdditiveBlending} depthWrite={false} />
    </mesh>
  );
}
