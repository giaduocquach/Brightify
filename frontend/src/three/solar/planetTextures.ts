import { useMemo } from 'react';
import { useTexture } from '@react-three/drei';
import { SRGBColorSpace, type Texture } from 'three';
import type { BodyDef } from './bodies';
import { textureUrl } from './textureUrls';

export interface BodyTextures {
  map?: Texture;
  clouds?: Texture;
  night?: Texture;
  bump?: Texture;
  ring?: Texture;
}

// Loads a body's equirectangular maps via drei useTexture (suspends until ready).
// Only call from a component that renders for a body with `def.texture` set, so the
// hook input is non-empty and stable for that instance.
export function useBodyTextures(def: BodyDef): BodyTextures {
  const urls = useMemo(() => {
    const u: Record<string, string> = {};
    if (def.texture) u.map = textureUrl(def.texture);
    if (def.clouds) u.clouds = textureUrl(def.clouds);
    if (def.night) u.night = textureUrl(def.night);
    if (def.bump) u.bump = textureUrl(def.bump);
    if (def.ring) u.ring = textureUrl(def.ring);
    return u;
  }, [def.texture, def.clouds, def.night, def.bump, def.ring]);

  const tex = useTexture(urls) as unknown as BodyTextures;
  // colour maps are sRGB; bump is linear data (leave as-is)
  if (tex.map) tex.map.colorSpace = SRGBColorSpace;
  if (tex.clouds) tex.clouds.colorSpace = SRGBColorSpace;
  if (tex.night) tex.night.colorSpace = SRGBColorSpace;
  if (tex.ring) tex.ring.colorSpace = SRGBColorSpace;
  return tex;
}
