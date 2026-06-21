import { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color } from 'three';
import { useStore } from '../../state/store';
import { vaToColor } from '../va';
import { solarRefs } from '../solar/refs';
import { vibeRefs } from './vibeRefs';
import { vibeTargetFromSong, type VibeTarget } from './resolver';
import { detectBeat } from './beat';

// Smooths vibeRefs.current toward the per-song target each frame (graceful ~1.5s cross-fade on
// track change) and layers the live beat impulse on top. The target recomputes only when the
// current song changes (React effect) — the per-frame work is pure scalar lerps + one HSL eval,
// zero re-render. Call once, high in the scene (Scene).
const TAU = 0.4;        // exp-smoothing time constant → ~4·TAU ≈ 1.6s to settle
const BEAT_DECAY = 0.25; // seconds for a beat impulse to fall back to 0
const WHITE = new Color(1, 1, 1);

export function useVibeDriver() {
  const current = useStore((s) => s.current);
  const target = useRef<VibeTarget>(vibeTargetFromSong(null));
  useEffect(() => { target.current = vibeTargetFromSong(current); }, [current]);

  useFrame((state, dt) => {
    const k = 1 - Math.exp(-dt / TAU);
    const v = vibeRefs.current;
    const t = target.current;
    v.valence += (t.valence - v.valence) * k;
    v.arousal += (t.arousal - v.arousal) * k;
    v.q1 += (t.q1 - v.q1) * k;
    v.q2 += (t.q2 - v.q2) * k;
    v.q3 += (t.q3 - v.q3) * k;
    v.q4 += (t.q4 - v.q4) * k;
    v.saturation += (t.saturation - v.saturation) * k;
    v.bloom += (t.bloom - v.bloom) * k;
    v.bloomThreshold += (t.bloomThreshold - v.bloomThreshold) * k;
    v.vignette += (t.vignette - v.vignette) * k;
    v.nebulaSpeed += (t.nebulaSpeed - v.nebulaSpeed) * k;
    v.corona += (t.corona - v.corona) * k;

    // Palette from the SMOOTHED mood so the grade colour glides, not snaps.
    vaToColor(v.valence, v.arousal, v.primary);
    v.gradeTint.copy(WHITE).lerp(v.primary, 0.22 + 0.12 * v.arousal);

    // Beat = a gentle brightness pulse (kin to the existing Sun bass-pulse). Suppressed under
    // reduced-motion so motion-sensitive users get a steady mood grade, no flashing.
    if (!solarRefs.reducedMotion && detectBeat(state.clock.elapsedTime)) v.beat = 1;
    v.beat = Math.max(0, v.beat - dt / BEAT_DECAY);
  });
}
