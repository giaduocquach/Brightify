// Appearance config for the ice giants Uranus/Neptune — the single place to tune their look
// without touching the fixed emotion hexes in bodies.ts. The tint is applied via the planet
// material's `color` (multiplies the equirect map); the band/streak/opacity drive the subtle
// procedural detail shell (GasGiantDetail).
//
// NEPTUNE_PALETTE: '2024 Oxford/Irwin reprocessing proved the iconic deep-blue Neptune is an
// artifact — both giants are actually a similar pale greenish-blue. We default to 'familiar'
// (the recognizable deep blue) per product choice; flip to 'accurate' for the true science.
export const NEPTUNE_PALETTE: 'accurate' | 'familiar' = 'familiar';

export interface GiantParams {
  tint: string;           // multiplied over the equirect map
  bandStrength: number;   // latitudinal band amplitude
  bandFreq: number;       // number of latitude bands
  streakStrength: number; // faint cloud-streak amplitude
  detailOpacity: number;  // overall detail-shell opacity
}

const URANUS = '#3AB09E';
const NEPTUNE = '#9C4F96';

// Tints are light (near-neutral) so the existing photoreal textures show through; they only
// nudge hue. 'familiar' keeps Uranus pale-cyan + Neptune deep-blue; 'accurate' makes both a
// similar pale greenish-blue.
export const GIANT_PARAMS: Record<string, GiantParams> = {
  [URANUS]: {
    tint: '#e6f3f4',
    bandStrength: 0.04, bandFreq: 7, streakStrength: 0.02, detailOpacity: 0.10,
  },
  [NEPTUNE]: {
    tint: NEPTUNE_PALETTE === 'familiar' ? '#dce8ff' : '#bcd0cf',
    bandStrength: 0.07, bandFreq: 9, streakStrength: 0.05, detailOpacity: 0.16,
  },
};

export function giantParamsFor(hex: string): GiantParams | undefined {
  return GIANT_PARAMS[hex];
}
