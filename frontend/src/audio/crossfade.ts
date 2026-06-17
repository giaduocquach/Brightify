// Smart crossfade policy — TypeScript port of static/js/crossfade.js (unchanged
// research/policy: Camelot key compatibility, ITU-R BS.1770 LUFS matching, tempo/
// energy/mood-based fade duration tiers, beat-aligned cue points). Pure functions;
// every field is optional and the policy degrades gracefully when data is missing.

export interface CrossfadeTrack {
  track_name?: string;
  tempo?: number;
  energy?: number;
  duration_s?: number;
  key?: number;
  mode?: number;
  mood_quadrant?: string;
  loudness_lufs?: number;
  fade_out_cue_s?: number;
  fade_in_cue_s?: number;
  danceability?: number;
  downbeat_times_json?: string | number[];
  vocal_start_s?: number;   // first vocal onset (≈ end of instrumental intro) — Tier 3
  vocal_end_s?: number;     // last vocal offset (≈ start of instrumental outro) — Tier 3
}

// One adaptive overlapping transition, ANCHORED to where A's vocals end (vocal_end_A):
//   • The fade-out never starts before A's vocals finish (C1) — we never talk over A's singing.
//   • B enters at its musical groove/drop and stays instrumental through the overlap (C2) — so at
//     most one voice is ever heard.
//   • EARLY vocal-end (long instrumental tail) → transition early, fade A down over the tail.
//   • LATE vocal-end (sings to the song's end) → A plays its short tail to its true end at full
//     while B fades in underneath and continues PAST A's end (holdOutgoing). No hard cut.
export interface CrossfadePlan {
  duration_s: number;        // overlap length L
  fadeOutStartAt_s: number;  // anchored at/after vocal_end_A, downbeat-snapped
  fadeInStartAt_s: number;   // B's groove/drop entry, downbeat-snapped
  gainA: number;
  gainB: number;
  curve: 'linear' | 'equal-power';
  holdOutgoing: boolean;     // late-vocal → engine must NOT ramp A down; A plays to its natural end
  fadeInDur_s: number;       // B's fade-in length (may exceed A's remaining tail in the late regime)
  rateFactor: number;        // tempo nudge for B's deck (1.0 = none) — set in P3
  bassSwap: boolean;         // DJ low-shelf bass swap during the overlap — set in P4
  lateVocal: boolean;        // A sang (near) to its end → late-transition regime
}

type Camelot = { n: number; letter: 'A' | 'B' };

const CAMELOT_MAP: Record<string, Camelot> = {
  '0,1': { n: 8, letter: 'B' }, '1,1': { n: 3, letter: 'B' }, '2,1': { n: 10, letter: 'B' },
  '3,1': { n: 5, letter: 'B' }, '4,1': { n: 12, letter: 'B' }, '5,1': { n: 7, letter: 'B' },
  '6,1': { n: 2, letter: 'B' }, '7,1': { n: 9, letter: 'B' }, '8,1': { n: 4, letter: 'B' },
  '9,1': { n: 11, letter: 'B' }, '10,1': { n: 6, letter: 'B' }, '11,1': { n: 1, letter: 'B' },
  '0,0': { n: 5, letter: 'A' }, '1,0': { n: 12, letter: 'A' }, '2,0': { n: 7, letter: 'A' },
  '3,0': { n: 2, letter: 'A' }, '4,0': { n: 9, letter: 'A' }, '5,0': { n: 4, letter: 'A' },
  '6,0': { n: 11, letter: 'A' }, '7,0': { n: 6, letter: 'A' }, '8,0': { n: 1, letter: 'A' },
  '9,0': { n: 8, letter: 'A' }, '10,0': { n: 3, letter: 'A' }, '11,0': { n: 10, letter: 'A' },
};

function toCamelot(key: number, mode: number): Camelot {
  return CAMELOT_MAP[`${key},${mode}`] || { n: 1, letter: 'A' };
}

function camelotCompatible(keyA: number, modeA: number, keyB: number, modeB: number): number {
  const a = toCamelot(keyA, modeA);
  const b = toCamelot(keyB, modeB);
  if (a.n === b.n && a.letter === b.letter) return 1.0;
  if (a.n === b.n) return 0.8;
  if (a.letter === b.letter) {
    const diff = Math.abs(a.n - b.n);
    if (diff === 1 || diff === 11) return 0.7;
  }
  return 0.4;
}

const dbToLin = (db: number) => Math.pow(10, db / 20);

const TARGET_LUFS = -14;
const MAX_GAIN_BOOST_DB = 12.0;
const SAFETY_S = 0.4;        // keep the overlap this far clear of the incoming vocal line
const OVERLAP_MIN_S = 3.0;   // floor for a still-smooth crossfade
const OVERLAP_MAX_S = 12.0;  // cap — a longer mix drags
const LEAD_BARS = 2;         // enter B this many bars before its vocals (beat-relative, not fixed s)
const MIN_FADE_IN_S = 0.5;   // shortest B fade-in (cold-open tracks → voice arrives almost at once)
// downbeat_times_json is already a bar/downbeat grid (~every 4 beats, 1.6–1.9s apart), so we snap
// directly to it — no further re-binning needed.

// Parse the stored downbeat grid (JSON string or array) into ascending seconds.
function parseDownbeats(j?: string | number[]): number[] {
  if (!j) return [];
  try {
    const arr = typeof j === 'string' ? JSON.parse(j) : j;
    return Array.isArray(arr) ? (arr.filter((t) => Number.isFinite(t)) as number[]) : [];
  } catch { return []; }
}

// Snap a time to the grid. 'before' never returns a beat later than t (so a fade can't be
// pulled into a vocal); 'after' never earlier; 'nearest' minimises |Δ|. Identity if empty.
function snapToDownbeat(t: number, grid: number[], dir: 'nearest' | 'before' | 'after'): number {
  if (!grid.length) return t;
  if (dir === 'before') {
    let best = t;
    for (const d of grid) { if (d <= t) best = d; else break; }
    return best;
  }
  if (dir === 'after') {
    for (const d of grid) { if (d >= t) return d; }
    return grid[grid.length - 1];
  }
  let best = grid[0];
  for (const d of grid) { if (Math.abs(d - t) < Math.abs(best - t)) best = d; }
  return best;
}

const quadOf = (s?: string) => {
  const m = s && s.match(/Q(\d)/);
  return m ? parseInt(m[1], 10) : 0;
};
const QUAD_ADJACENT = new Set(['1-2', '2-1', '1-4', '4-1', '2-3', '3-2', '3-4', '4-3']);
function moodScoreOf(mqA?: string, mqB?: string): number {
  const a = quadOf(mqA), b = quadOf(mqB);
  if (!a || !b) return 0.5;
  if (a === b) return 1.0;
  if (QUAD_ADJACENT.has(`${a}-${b}`)) return 0.5;
  return 0.0;
}

export function planCrossfade(
  trackA: CrossfadeTrack,
  trackB: CrossfadeTrack,
  userBaseVolume: number,
): CrossfadePlan {
  const Atempo = Number.isFinite(trackA?.tempo) ? (trackA.tempo as number) : 120;
  const Btempo = Number.isFinite(trackB?.tempo) ? (trackB.tempo as number) : 120;
  const Aenergy = Number.isFinite(trackA?.energy) ? (trackA.energy as number) : 0.5;
  const Benergy = Number.isFinite(trackB?.energy) ? (trackB.energy as number) : 0.5;
  const AdurS = Number.isFinite(trackA?.duration_s) ? (trackA.duration_s as number) : 180;

  const moodKnown = !!trackA?.mood_quadrant && !!trackB?.mood_quadrant;
  const keyKnown = Number.isFinite(trackA?.key) && Number.isFinite(trackB?.key)
    && Number.isFinite(trackA?.mode) && Number.isFinite(trackB?.mode);

  const dTempo = Math.abs(Atempo - Btempo) / Math.max(Atempo, 1);
  const dEnergy = Math.abs(Aenergy - Benergy);
  const moodScore = moodKnown ? moodScoreOf(trackA.mood_quadrant, trackB.mood_quadrant) : 0.5;
  const sameQuad = moodScore >= 1.0;
  const keyCompat = keyKnown
    ? camelotCompatible(Math.round(trackA.key as number), trackA.mode as number,
        Math.round(trackB.key as number), trackB.mode as number)
    : 0.4;

  const dbA = parseDownbeats(trackA?.downbeat_times_json);
  const dbB = parseDownbeats(trackB?.downbeat_times_json);

  // ── LUFS-matched levels (ITU-R BS.1770) ──
  const hasLUFS = Number.isFinite(trackA?.loudness_lufs) && Number.isFinite(trackB?.loudness_lufs);
  const clamp = (v: number) => Math.min(1.0, Math.max(0, v));
  const lufsGain = (lufs: number) =>
    Math.min(dbToLin(MAX_GAIN_BOOST_DB), dbToLin(TARGET_LUFS - lufs));
  const gainA = hasLUFS ? clamp(userBaseVolume * lufsGain(trackA.loudness_lufs as number)) : userBaseVolume;
  const gainB = hasLUFS ? clamp(userBaseVolume * lufsGain(trackB.loudness_lufs as number)) : userBaseVolume;

  // ── Desired overlap length L by musical compatibility (harmonic + tempo + energy + mood) ──
  let L: number;
  if (dTempo > 0.12 || dEnergy > 0.45) L = 4.0;                              // clashing → short but smooth
  else if (moodScore >= 1.0 && dTempo < 0.06 && keyCompat >= 0.8) L = 11.0;  // ideal long blend
  else if (moodScore >= 0.5 && dTempo < 0.07 && keyCompat >= 0.7) L = 9.0;
  else if (Aenergy > 0.7 && Benergy > 0.7) L = 9.0;
  else if (moodScore === 0.0) L = 5.0;
  else L = 7.0;
  L = Math.min(L, OVERLAP_MAX_S);

  // ── Anchor A's fade-out at the first downbeat AT/AFTER its vocals end (C1: never over A's voice) ──
  const vEndA = trackA?.vocal_end_s;
  const anchorRaw = Number.isFinite(vEndA)
    ? (vEndA as number)
    : (Number.isFinite(trackA?.fade_out_cue_s) ? (trackA.fade_out_cue_s as number) : Math.max(0, AdurS - L - 5));
  let fadeOutStart = snapToDownbeat(anchorRaw, dbA, 'after');
  fadeOutStart = Math.max(anchorRaw, Math.min(fadeOutStart, Math.max(0, AdurS - 0.2)));
  const tailA = AdurS - fadeOutStart;   // A's instrumental runway to its natural end

  // ── B's musical entry: a couple of bars BEFORE its vocals (beat-relative, never a fixed number of
  // seconds), snapped to a downbeat. Adapts per song — B that sings immediately → entry ≈ 0; B with a
  // long intro → enter ~LEAD_BARS bars before the first vocal, skipping the dragged intro but NEVER
  // cutting into the lyrics. We deliberately do NOT use fade_in_cue_s as the entry: it's a structural
  // "drop" boundary that often lands at/after the first vocal → that's what ate B's opening lyrics.
  const vStartB = trackB?.vocal_start_s;
  let entryB: number;
  if (Number.isFinite(vStartB)) {
    const barSec = (4 * 60) / Math.max(60, Math.min(200, Btempo));   // one bar = 4 beats
    const targetLead = Math.max(2.5, Math.min(6, LEAD_BARS * barSec));
    entryB = snapToDownbeat(Math.max(0, (vStartB as number) - targetLead), dbB, 'nearest');
    entryB = Math.min(Math.max(0, entryB), Math.max(0, (vStartB as number) - SAFETY_S));  // never past the vocals
  } else {
    // no vocal data → only trim genuinely-small leading silence; never seek deep
    const fInB = trackB?.fade_in_cue_s;
    entryB = (Number.isFinite(fInB) && (fInB as number) <= 2.0) ? (fInB as number) : 0;
  }

  // ── Two regimes — vocals-end-early (fade over the tail) vs sings-to-the-end (hold A, B continues) ──
  const isLateVocal = tailA < (OVERLAP_MIN_S + SAFETY_S);
  let holdOutgoing: boolean;
  if (isLateVocal) {
    holdOutgoing = true;                                  // A plays its short tail to its true end at full
    L = Math.max(OVERLAP_MIN_S, Math.min(L, OVERLAP_MAX_S));      // L not clamped to the tiny tail → B carries past A's end
  } else {
    holdOutgoing = false;                                 // fade A down over its instrumental tail
    L = Math.max(OVERLAP_MIN_S, Math.min(L, tailA, OVERLAP_MAX_S));
  }

  // B-side fade-in: reach full volume BEFORE B's vocals so the opening lyrics are clear (never buried
  // mid-fade). Long intro → fade over the whole lead-in; cold-open → a short fade so the voice lands.
  const fadeInDur = Number.isFinite(vStartB)
    ? Math.max(MIN_FADE_IN_S, Math.min(L, (vStartB as number) - entryB - SAFETY_S))
    : L;

  const correlated = sameQuad && dTempo < 0.03 && keyCompat === 1.0;
  const curve: 'linear' | 'equal-power' = correlated ? 'linear' : 'equal-power';

  // P3 — nudge B toward A's tempo only when they're already close (≤6%), so beats lock during the
  // mix without an audible stretch. P4 — bass-swap only on longer, harmonically-compatible blends.
  const rateFactor = (dTempo <= 0.06 && Atempo > 0 && Btempo > 0)
    ? Math.max(0.94, Math.min(1.06, Atempo / Btempo))
    : 1.0;
  const bassSwap = L >= 6 && keyCompat >= 0.7;

  return {
    duration_s: L,
    fadeOutStartAt_s: fadeOutStart,
    fadeInStartAt_s: entryB,
    gainA, gainB, curve,
    holdOutgoing,
    fadeInDur_s: fadeInDur,
    rateFactor,
    bassSwap,
    lateVocal: isLateVocal,
  };
}
