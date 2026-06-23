// Valence-Arousal colour math (Russell circumplex).
import { Color } from 'three';
import { EMOTION_COLORS } from '../data/colors';

// Lookup of the 12 pickable colours → backend V-A (single source of truth).
const VA_BY_HEX = new Map(EMOTION_COLORS.map((c) => [c.hex.toUpperCase(), { v: c.v, a: c.a }]));

function linearize(c: number) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function labF(t: number) {
  return t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
}

/** sRGB hex → CIELAB {L, C}. Internal helper for hexToVA's arbitrary-hex fallback. */
function hexToLab(hex: string): { L: number; C: number } {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const rl = linearize(r), gl = linearize(g), bl = linearize(b);
  const X = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047;
  const Y = (0.2126729 * rl + 0.7151522 * gl + 0.072175 * bl) / 1.0;
  const Z = (0.0193339 * rl + 0.119192 * gl + 0.9503041 * bl) / 1.08883;
  const L = 116 * labF(Y) - 16;
  const a = 500 * (labF(X) - labF(Y));
  const bStar = 200 * (labF(Y) - labF(Z));
  return { L, C: Math.sqrt(a * a + bStar * bStar) };
}

export function clamp01(x: number) {
  return Math.max(0, Math.min(1, x));
}

/** CIELAB → Valence/Arousal (Valdez–Mehrabian coefficients). Internal helper for hexToVA. */
function labToVA(L: number, C: number): { v: number; a: number } {
  const Ln = L / 100, Cn = C / 130;
  return {
    v: clamp01(0.69 * Ln + 0.22 * Cn),
    a: clamp01(-0.31 * Ln + 0.6 * Cn),
  };
}

export function hexToVA(hex: string): { v: number; a: number } {
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return { v: 0.5, a: 0.5 };
  // Pickable palette colours use the backend's V-A so the picker atmosphere matches
  // the actual recommendation target. Arbitrary hexes fall back to the CIELAB formula.
  const known = VA_BY_HEX.get(hex.toUpperCase());
  if (known) return known;
  const { L, C } = hexToLab(hex);
  return labToVA(L, C);
}

/** VA → a hue/sat/light Color for atmosphere (cool indigo → warm amber). */
export function vaToColor(v: number, a: number, target = new Color()): Color {
  const hue = (250 + (35 - 250) * v) / 360;
  const sat = 0.3 + 0.55 * a;
  const light = 0.32 + 0.34 * v;
  return target.setHSL(((hue % 1) + 1) % 1, sat, light);
}

/** VA → a CSS hex string. Used for result swatches so each song's dot reflects its
 *  mood (its V-A), not its album-art palette colour (which is unrelated to emotion). */
export function vaToHex(v: number, a: number): string {
  return '#' + vaToColor(v, a).getHexString();
}
