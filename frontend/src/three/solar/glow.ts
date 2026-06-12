// A soft radial-gradient sprite texture, shared by every glow halo in the scene
// (sun corona, planet atmospheres, nebulae, comet tail). Built once on a canvas;
// colour comes from the sprite material so one texture tints to anything.
import { CanvasTexture, type Texture } from 'three';

let cached: Texture | null = null;

export function glowTexture(): Texture {
  if (cached) return cached;
  const size = 128;
  const cv = document.createElement('canvas');
  cv.width = cv.height = size;
  const ctx = cv.getContext('2d')!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.25, 'rgba(255,255,255,0.55)');
  g.addColorStop(0.6, 'rgba(255,255,255,0.12)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  cached = new CanvasTexture(cv);
  return cached;
}
