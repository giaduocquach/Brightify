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

let cachedNebula: Texture | null = null;

// A wispier, non-circular cloud texture for the far-field nebula puffs — several offset
// radial gradients plus a faint deterministic speckle, so the gas reads as a ragged cloud
// rather than a clean glowing ball. Tinted per-sprite via the material colour (like glow).
export function nebulaTexture(): Texture {
  if (cachedNebula) return cachedNebula;
  const size = 256;
  const cv = document.createElement('canvas');
  cv.width = cv.height = size;
  const ctx = cv.getContext('2d')!;
  // layered offset lobes → irregular silhouette
  const lobes: [number, number, number, number][] = [
    [0.5, 0.5, 0.5, 0.9],
    [0.38, 0.44, 0.30, 0.6],
    [0.62, 0.56, 0.34, 0.5],
    [0.46, 0.64, 0.22, 0.45],
  ];
  for (const [cx, cy, rad, alpha] of lobes) {
    const g = ctx.createRadialGradient(cx * size, cy * size, 0, cx * size, cy * size, rad * size);
    g.addColorStop(0, `rgba(255,255,255,${alpha})`);
    g.addColorStop(0.5, `rgba(255,255,255,${alpha * 0.22})`);
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  // faint deterministic speckle (golden-angle spiral) for fine structure
  ctx.globalAlpha = 0.05;
  ctx.fillStyle = '#ffffff';
  for (let i = 0; i < 420; i++) {
    const a = i * 2.39996;
    const rr = ((i % 60) / 60) * 0.5 * size;
    ctx.fillRect(size / 2 + Math.cos(a) * rr, size / 2 + Math.sin(a) * rr, 1, 1);
  }
  ctx.globalAlpha = 1;
  cachedNebula = new CanvasTexture(cv);
  return cachedNebula;
}

let cachedComet: Texture | null = null;

// Grayscale bump map for the comet nucleus — deterministic craters (dark pits with lighter
// rims) + fine speckle on a neutral mid-grey, so the dark rock-ice reads as cratered relief
// under the Sun's light instead of a smooth plastic blob.
export function cometSurfaceTexture(): Texture {
  if (cachedComet) return cachedComet;
  const size = 256;
  const cv = document.createElement('canvas');
  cv.width = cv.height = size;
  const ctx = cv.getContext('2d')!;
  ctx.fillStyle = '#808080'; // neutral = no displacement
  ctx.fillRect(0, 0, size, size);
  // craters (deterministic golden-angle placement)
  for (let i = 0; i < 44; i++) {
    const a = i * 2.39996;
    const rr = ((i * 53) % 100) / 100;
    const x = (0.5 + Math.cos(a) * rr * 0.46) * size;
    const y = (0.5 + Math.sin(a * 1.3) * rr * 0.46) * size;
    const cr = 5 + (i % 5) * 5;
    const g = ctx.createRadialGradient(x, y, 0, x, y, cr);
    g.addColorStop(0, '#454545');
    g.addColorStop(0.7, '#6c6c6c');
    g.addColorStop(1, '#9a9a9a');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, cr, 0, Math.PI * 2);
    ctx.fill();
  }
  // fine speckle
  for (let i = 0; i < 2600; i++) {
    const a = i * 2.39996;
    const rr = ((i * 17) % 100) / 100;
    ctx.fillStyle = (i % 2) ? 'rgba(60,60,60,0.5)' : 'rgba(180,180,180,0.4)';
    ctx.fillRect((0.5 + Math.cos(a) * rr * 0.49) * size, (0.5 + Math.sin(a) * rr * 0.49) * size, 1, 1);
  }
  cachedComet = new CanvasTexture(cv);
  return cachedComet;
}
