import { useEffect } from 'react';
import { useThree } from '@react-three/fiber';
import { useTexture } from '@react-three/drei';
import { PMREMGenerator, SRGBColorSpace } from 'three';
import { MILKYWAY_TEXTURE } from './bodies';
import { textureUrl } from './textureUrls';

// Image-based lighting baked from the existing milky-way equirect so every meshStandardMaterial
// (astronaut visor + suit metal, ship hull) reflects the galaxy — the single biggest realism
// lever for the photoreal heroes. One-shot PMREM bake → negligible per-frame cost.
//
// We bake + assign `scene.environment` ourselves (instead of drei <Environment files=...>, whose
// extension-based loader is fragile with Vite-hashed URLs). `scene.environmentIntensity` is kept
// LOW so the rough planets barely change (their dramatic dark sides stay intact); hero metals
// compensate with a higher per-material `envMapIntensity` (product lands ~0.4–0.7, just under bloom).
// The dimmed MilkyWay mesh remains the actual sky — this only feeds reflections/ambient.
export default function EnvMap() {
  const tex = useTexture(textureUrl(MILKYWAY_TEXTURE));
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    tex.colorSpace = SRGBColorSpace;
    const pmrem = new PMREMGenerator(gl);
    const envRT = pmrem.fromEquirectangular(tex);
    scene.environment = envRT.texture;
    scene.environmentIntensity = 0.35;
    pmrem.dispose();
    return () => {
      if (scene.environment === envRT.texture) scene.environment = null;
      envRT.dispose();
    };
  }, [tex, gl, scene]);

  return null;
}
