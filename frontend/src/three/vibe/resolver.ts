import { clamp01 } from '../va';
import type { Song } from '../../api/client';

// Pure, deterministic mapping from a song's valence-arousal mood to the cosmic vibe targets.
// No model calls, no genre field (there isn't one) — the four Russell quadrants ARE the vibe:
//   Q1 hi-v hi-a = vui + sôi động   Q2 lo-v hi-a = mãnh liệt / căng
//   Q3 lo-v lo-a = buồn             Q4 hi-v lo-a = thư thái
// Membership is continuous so transitions blend; mood_quadrant only nudges the dominant weight.
export interface VibeTarget {
  valence: number;
  arousal: number;
  q1: number; q2: number; q3: number; q4: number;
  saturation: number;
  bloom: number;
  bloomThreshold: number;
  vignette: number;
  nebulaSpeed: number;
  corona: number;
}

export function quadrantWeights(v: number, a: number) {
  const q1 = clamp01(v) * clamp01(a);
  const q2 = clamp01(1 - v) * clamp01(a);
  const q3 = clamp01(1 - v) * clamp01(1 - a);
  const q4 = clamp01(v) * clamp01(1 - a);
  const s = q1 + q2 + q3 + q4 || 1;
  return { q1: q1 / s, q2: q2 / s, q3: q3 / s, q4: q4 / s };
}

export function vibeTargetFromSong(song: Song | null): VibeTarget {
  const v = clamp01(song?.valence ?? 0.5);
  const a = clamp01(song?.arousal ?? 0.5);
  let w = quadrantWeights(v, a);

  // Nudge toward the backend's discrete label so a Q-labelled song commits to its quadrant,
  // without ever hard-switching (keeps blends smooth).
  const q = song?.mood_quadrant;
  if (q === 'Q1' || q === 'Q2' || q === 'Q3' || q === 'Q4') {
    const key = q.toLowerCase() as 'q1' | 'q2' | 'q3' | 'q4';
    const b = { ...w, [key]: w[key] + 0.15 };
    const s = b.q1 + b.q2 + b.q3 + b.q4;
    w = { q1: b.q1 / s, q2: b.q2 / s, q3: b.q3 / s, q4: b.q4 / s };
  }

  return {
    valence: v,
    arousal: a,
    ...w,
    saturation: 1 - 0.45 * w.q3,                              // sad desaturates
    bloom: 0.35 + 0.35 * v + 0.15 * a,                        // bright/energetic glow more
    bloomThreshold: clamp01(0.5 - 0.18 * (w.q1 + w.q4) + 0.12 * w.q2), // soft moods glow low
    vignette: 0.55 + 0.35 * w.q3 + 0.15 * w.q2 - 0.2 * w.q1,  // sad/intense darker, upbeat opens
    nebulaSpeed: 0.4 + 1.4 * a,                               // arousal drives drift
    corona: 1 + 0.8 * w.q2 + 0.4 * w.q1,                      // intense/upbeat = bigger flaring sun
  };
}
