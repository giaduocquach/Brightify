import { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useTexture } from '@react-three/drei';
import { AdditiveBlending, SRGBColorSpace, type Mesh, type SpriteMaterial } from 'three';
import { engine } from '../../audio/engine';
import { glowTexture } from './glow';
import { solarRefs } from './refs';
import { vibeRefs } from '../vibe/vibeRefs';
import { SUN_SIZE, SUN_TEXTURE } from './bodies';
import { textureUrl } from './textureUrls';

const CORONA_INNER = 0.4;
const CORONA_OUTER = 0.12;
// Solar flares (Q2 mãnh liệt): tongues that erupt from the limb on the beat. Golden-angle placed.
const FLARES = Array.from({ length: 5 }, (_, i) => i * 2.39996);

// The star at the centre. Not one of the twelve colours — a real sun texture with a
// warm corona; lights every body and the system orbits it. The core is `transparent` +
// `depthWrite={false}` so it works as the GodRays light source (postprocessing requirement).
export default function Sun({ onReady }: { onReady?: (m: Mesh | null) => void }) {
  const core = useRef<Mesh>(null);
  const coronaInner = useRef<SpriteMaterial>(null);
  const coronaOuter = useRef<SpriteMaterial>(null);
  const flares = useRef<(SpriteMaterial | null)[]>([]);
  const tex = glowTexture();
  const surface = useTexture(textureUrl(SUN_TEXTURE));
  surface.colorSpace = SRGBColorSpace;

  // Report the core mesh once (stable) so the scene can wire GodRays to it.
  useEffect(() => { onReady?.(core.current); return () => onReady?.(null); }, [onReady]);

  useFrame((_, dt) => {
    if (core.current) {
      if (!solarRefs.reducedMotion) core.current.rotation.y += dt * 0.04;
      core.current.scale.setScalar(1 + engine.features.bass * 0.06); // audio pulse — kept
    }
    // Corona flares with the song's vibe (intense/upbeat = bigger), with a faint beat lift.
    const { corona, beat, q2 } = vibeRefs.current;
    if (coronaInner.current) coronaInner.current.opacity = CORONA_INNER * corona + beat * 0.06;
    if (coronaOuter.current) coronaOuter.current.opacity = CORONA_OUTER * corona + beat * 0.03;
    // Solar-flare tongues: only for intense (Q2) songs, bursting on the beat.
    const flare = q2 * (0.25 + beat * 0.85);
    flares.current.forEach((m) => { if (m) m.opacity = flare; });
  });

  return (
    <group>
      <mesh ref={(m) => { core.current = m; solarRefs.sunMesh = m; }}>
        <sphereGeometry args={[SUN_SIZE, 48, 48]} />
        <meshBasicMaterial map={surface} transparent depthWrite={false} />
      </mesh>
      <sprite scale={SUN_SIZE * 3.4}>
        <spriteMaterial ref={coronaInner} map={tex} color={'#ffcf6b'} transparent opacity={CORONA_INNER}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite scale={SUN_SIZE * 6}>
        <spriteMaterial ref={coronaOuter} map={tex} color={'#ff9a3c'} transparent opacity={CORONA_OUTER}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      {/* Q2 solar-flare tongues around the limb (opacity driven in useFrame) */}
      {FLARES.map((a, i) => (
        <sprite key={i} position={[Math.cos(a) * SUN_SIZE * 1.3, Math.sin(a) * SUN_SIZE * 1.3, 0]}
          scale={[SUN_SIZE * 0.9, SUN_SIZE * 2.4, 1]}>
          <spriteMaterial ref={(el) => { flares.current[i] = el; }} map={tex} color={'#ff5a1e'}
            transparent opacity={0} blending={AdditiveBlending} depthWrite={false} />
        </sprite>
      ))}
    </group>
  );
}
