import { useMemo } from 'react';
import { AdditiveBlending, BackSide, Color } from 'three';
import { ATMO_VERT, ATMO_FRAG } from '../shaders';

// A thin fresnel-rim shell that glows in the body's emotion hue, so a photoreal
// planet still carries its colour identity. Rendered on the inside of a slightly
// larger sphere (BackSide) with additive blending.
export default function Atmosphere({
  hex,
  size,
  intensity = 1.2,
  power = 3.2,
}: {
  hex: string;
  size: number;
  intensity?: number;
  power?: number;
}) {
  const uniforms = useMemo(
    () => ({
      uColor: { value: new Color(hex) },
      uIntensity: { value: intensity },
      uPower: { value: power },
    }),
    [hex, intensity, power],
  );

  return (
    <mesh scale={size * 1.18}>
      <sphereGeometry args={[1, 48, 48]} />
      <shaderMaterial
        vertexShader={ATMO_VERT}
        fragmentShader={ATMO_FRAG}
        uniforms={uniforms}
        transparent
        side={BackSide}
        blending={AdditiveBlending}
        depthWrite={false}
      />
    </mesh>
  );
}
