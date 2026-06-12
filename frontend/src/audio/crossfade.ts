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
}

export interface CrossfadePlan {
  duration_s: number;
  fadeOutStartAt_s: number;
  fadeInStartAt_s: number;
  gainA: number;
  gainB: number;
  curve: 'linear' | 'equal-power';
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
const DUR_MIN = 2.0;
const DUR_MAX = 12.0;
const MAX_GAIN_BOOST_DB = 12.0;

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
  const BdurS = Number.isFinite(trackB?.duration_s) ? (trackB.duration_s as number) : 180;

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

  let duration: number;
  if (dTempo > 0.10 || dEnergy > 0.4) duration = 3.0;
  else if (moodScore >= 1.0 && dTempo < 0.06 && keyCompat >= 0.7) duration = 10.0;
  else if (moodScore >= 0.5 && dTempo < 0.06 && keyCompat >= 0.7) duration = 8.0;
  else if (Aenergy > 0.75 && Benergy > 0.75) duration = 8.0;
  else if (moodScore === 0.0) duration = 4.0;
  else duration = 6.0;
  if (AdurS > 0) duration = Math.min(duration, AdurS * 0.3);
  duration = Math.max(DUR_MIN, Math.min(DUR_MAX, duration));

  const fadeOutStart = Number.isFinite(trackA?.fade_out_cue_s)
    ? (trackA.fade_out_cue_s as number)
    : Math.max(0, AdurS - duration - 5);
  let fadeInStart = Number.isFinite(trackB?.fade_in_cue_s)
    ? (trackB.fade_in_cue_s as number)
    : (BdurS > 45 ? 10 : 0);

  const danceableA = Number.isFinite(trackA?.danceability) && (trackA.danceability as number) > 0.7;
  const danceableB = Number.isFinite(trackB?.danceability) && (trackB.danceability as number) > 0.7;
  if (danceableA && danceableB && dTempo < 0.08 && trackB?.downbeat_times_json) {
    try {
      const dbs = typeof trackB.downbeat_times_json === 'string'
        ? JSON.parse(trackB.downbeat_times_json)
        : trackB.downbeat_times_json;
      if (Array.isArray(dbs) && dbs.length > 0) {
        const snap = dbs.find((t) => t >= fadeInStart);
        if (Number.isFinite(snap)) fadeInStart = snap as number;
      }
    } catch { /* ignore invalid downbeat data */ }
  }

  const hasLUFS = Number.isFinite(trackA?.loudness_lufs) && Number.isFinite(trackB?.loudness_lufs);
  const clamp = (v: number) => Math.min(1.0, Math.max(0, v));
  const lufsGain = (lufs: number) =>
    Math.min(dbToLin(MAX_GAIN_BOOST_DB), dbToLin(TARGET_LUFS - lufs));
  const gainA = hasLUFS ? clamp(userBaseVolume * lufsGain(trackA.loudness_lufs as number)) : userBaseVolume;
  const gainB = hasLUFS ? clamp(userBaseVolume * lufsGain(trackB.loudness_lufs as number)) : userBaseVolume;

  const correlated = sameQuad && dTempo < 0.03 && keyCompat === 1.0;
  const curve: 'linear' | 'equal-power' = correlated ? 'linear' : 'equal-power';

  return { duration_s: duration, fadeOutStartAt_s: fadeOutStart, fadeInStartAt_s: fadeInStart, gainA, gainB, curve };
}
