import { Color } from 'three';

// Live, smoothed vibe state — a mutable singleton read directly in useFrame (same zero-re-render
// pattern as solarRefs / engine.features). The driver (useVibeDriver) lerps these toward the
// per-song target each frame; every reactive system (grade, bloom, vignette, nebula, sun) reads
// vibeRefs.current and writes its own materials. Never a React state in the render loop.
export interface Vibe {
  valence: number;
  arousal: number;
  q1: number; q2: number; q3: number; q4: number; // soft Russell-quadrant membership (sums ~1)
  primary: Color;     // vaToColor(valence, arousal) — the mood hue
  gradeTint: Color;   // white → primary, the screen-grade multiply colour
  saturation: number; // 1 = full colour, <1 desaturates (sad)
  bloom: number;          // Bloom.intensity target
  bloomThreshold: number; // Bloom.luminanceMaterial.threshold target
  vignette: number;       // Vignette.darkness target
  nebulaSpeed: number;    // multiplier on nebula drift
  corona: number;         // Sun corona opacity multiplier
  beat: number;           // 0→1 audio beat impulse, decays each frame
}

export const vibeRefs: { current: Vibe; heavy: boolean } = {
  heavy: false,
  current: {
    valence: 0.5,
    arousal: 0.5,
    q1: 0.25, q2: 0.25, q3: 0.25, q4: 0.25,
    primary: new Color('#a78bfa'),
    gradeTint: new Color(1, 1, 1),
    saturation: 1,
    bloom: 0.5,
    bloomThreshold: 0.5,
    vignette: 0.65,
    nebulaSpeed: 1,
    corona: 1,
    beat: 0,
  },
};
