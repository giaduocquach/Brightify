import { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useTexture } from '@react-three/drei';
import { AdditiveBlending, SRGBColorSpace, type Mesh } from 'three';
import { engine } from '../../audio/engine';
import { glowTexture } from './glow';
import { solarRefs } from './refs';
import { SUN_SIZE, SUN_TEXTURE } from './bodies';
import { textureUrl } from './textureUrls';

// The star at the centre. Not one of the twelve colours — a real sun texture with a
// warm corona; lights every body and the system orbits it. The core is `transparent` +
// `depthWrite={false}` so it works as the GodRays light source (postprocessing requirement).
export default function Sun({ onReady }: { onReady?: (m: Mesh | null) => void }) {
  const core = useRef<Mesh>(null);
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
  });

  return (
    <group>
      <mesh ref={(m) => { core.current = m; solarRefs.sunMesh = m; }}>
        <sphereGeometry args={[SUN_SIZE, 48, 48]} />
        <meshBasicMaterial map={surface} transparent depthWrite={false} />
      </mesh>
      <sprite scale={SUN_SIZE * 3.4}>
        <spriteMaterial map={tex} color={'#ffcf6b'} transparent opacity={0.4}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite scale={SUN_SIZE * 6}>
        <spriteMaterial map={tex} color={'#ff9a3c'} transparent opacity={0.12}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
    </group>
  );
}
