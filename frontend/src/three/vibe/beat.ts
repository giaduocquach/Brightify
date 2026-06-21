import { engine } from '../../audio/engine';

// Cheap live beat detector: spectral-flux on the already-computed bass band. A slow EMA tracks
// the baseline; a transient above 1.4× it (with a refractory gap) is a beat. Pure scalar math on
// engine.features — effectively free, genre-agnostic, no static tempo needed. Module-scoped state
// is fine: there is only ever one audio stream.
let bassSlow = 0;
let lastBeat = -1;
const ONSET = 0.06;
const MIN_GAP = 0.18; // ~330 BPM ceiling refractory

export function detectBeat(elapsed: number): boolean {
  const bass = engine.features.bass;
  bassSlow = 0.92 * bassSlow + 0.08 * bass;
  const flux = bass - bassSlow * 1.4;
  if (flux > ONSET && elapsed - lastBeat > MIN_GAP) {
    lastBeat = elapsed;
    return true;
  }
  return false;
}
