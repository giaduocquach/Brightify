import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useTexture } from '@react-three/drei';
import { AdditiveBlending, SRGBColorSpace, type Mesh } from 'three';
import { engine } from '../../audio/engine';
import { glowTexture } from './glow';
import { SUN_SIZE, SUN_TEXTURE } from './bodies';
import { textureUrl } from './textureUrls';

// The star at the centre. Not one of the twelve colours — a real sun texture with a
// warm corona; lights every body and the system orbits it.
export default function Sun() {
  const core = useRef<Mesh>(null);
  const tex = glowTexture();
  const surface = useTexture(textureUrl(SUN_TEXTURE));
  surface.colorSpace = SRGBColorSpace;

  useFrame((_, dt) => {
    if (core.current) {
      core.current.rotation.y += dt * 0.04;
      core.current.scale.setScalar(1 + engine.features.bass * 0.06);
    }
  });

  return (
    <group>
      <mesh ref={core}>
        <sphereGeometry args={[SUN_SIZE, 48, 48]} />
        <meshBasicMaterial map={surface} toneMapped={false} />
      </mesh>
      <sprite scale={SUN_SIZE * 4.5}>
        <spriteMaterial map={tex} color={'#ffcf6b'} transparent opacity={0.8}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite scale={SUN_SIZE * 9}>
        <spriteMaterial map={tex} color={'#ff9a3c'} transparent opacity={0.32}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
    </group>
  );
}
