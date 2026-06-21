import { DataTexture, NearestFilter, RedFormat, type Texture } from 'three';

// Shared cel-shading ramp for the HERO (astronaut + ship + cockpit). A 3-tone gradient
// map turns MeshToonMaterial's lighting into banded cartoon shading. Planets/Sun/Nebula
// keep their PBR materials, so the toon hero pops against a realistic space backdrop.
// Built once and reused (NearestFilter = hard bands, no mipmaps).
let _ramp: Texture | null = null;
export function toonRamp(): Texture {
  if (_ramp) return _ramp;
  const tones = new Uint8Array([95, 175, 255]); // dark → mid → light
  const t = new DataTexture(tones, tones.length, 1, RedFormat);
  t.minFilter = NearestFilter;
  t.magFilter = NearestFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  _ramp = t;
  return t;
}

// Ink outline tuned once. Pixel-constant width (drei Outlines default screenspace=false →
// thickness ≈ pixels), so the silhouette reads at every scale the astronaut takes.
//
// OUTLINE BUDGET: each <Outlines> is an extra back-face draw. Apply ONLY to the largest
// silhouette masses — astronaut = head, torso, backpack, 2 arms (max 5); ship = disc (max 2).
// Never outline small accents (gloves, boots, shoulder pads, antenna, pods, emblem, lights):
// they sit inside a larger outlined silhouette, so an outline there only adds cost + clutter.
export const OUTLINE = { color: '#171225', thickness: 5 } as const;
