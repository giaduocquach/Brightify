/**
 * Brightify — Music Player Module v6.0
 * HTML5 Audio with visualizer, radio mode, sleep timer, queue management
 */

// ═════════════════════════════════════════════════════════════════════════
// SMART CROSSFADE POLICY (Phase 1+2+3)
// Research: Bittner 2017 (ISMIR), Vande Veire & De Bie 2018, Camelot Wheel,
//           ITU-R BS.1770 (LUFS), Zehren 2020 (cue points)
// ═════════════════════════════════════════════════════════════════════════

// Camelot Wheel: (key 0-11, mode 0/1) → {n: 1-12, letter: 'A'|'B'}
// Map produced from circle-of-fifths. Major=B, Minor=A.
const CAMELOT_MAP = {
    // Major (mode=1)
    '0,1':  {n: 8,  letter: 'B'},   // C  major
    '1,1':  {n: 3,  letter: 'B'},   // C# major
    '2,1':  {n: 10, letter: 'B'},   // D  major
    '3,1':  {n: 5,  letter: 'B'},   // D# / Eb major
    '4,1':  {n: 12, letter: 'B'},   // E  major
    '5,1':  {n: 7,  letter: 'B'},   // F  major
    '6,1':  {n: 2,  letter: 'B'},   // F# major
    '7,1':  {n: 9,  letter: 'B'},   // G  major
    '8,1':  {n: 4,  letter: 'B'},   // G# / Ab major
    '9,1':  {n: 11, letter: 'B'},   // A  major
    '10,1': {n: 6,  letter: 'B'},   // A# / Bb major
    '11,1': {n: 1,  letter: 'B'},   // B  major
    // Minor (mode=0)
    '0,0':  {n: 5,  letter: 'A'},   // C  minor
    '1,0':  {n: 12, letter: 'A'},   // C# minor
    '2,0':  {n: 7,  letter: 'A'},   // D  minor
    '3,0':  {n: 2,  letter: 'A'},   // D# / Eb minor
    '4,0':  {n: 9,  letter: 'A'},   // E  minor
    '5,0':  {n: 4,  letter: 'A'},   // F  minor
    '6,0':  {n: 11, letter: 'A'},   // F# minor
    '7,0':  {n: 6,  letter: 'A'},   // G  minor
    '8,0':  {n: 1,  letter: 'A'},   // G# / Ab minor
    '9,0':  {n: 8,  letter: 'A'},   // A  minor
    '10,0': {n: 3,  letter: 'A'},   // A# / Bb minor
    '11,0': {n: 10, letter: 'A'},   // B  minor
};

function toCamelot(key, mode) {
    return CAMELOT_MAP[`${key},${mode}`] || { n: 1, letter: 'A' };
}

function camelotCompatible(keyA, modeA, keyB, modeB) {
    const camA = toCamelot(keyA, modeA);
    const camB = toCamelot(keyB, modeB);
    if (camA.n === camB.n && camA.letter === camB.letter) return 1.0;   // identical key
    if (camA.n === camB.n) return 0.8;                                   // mode flip (relative major↔minor)
    if (camA.letter === camB.letter) {
        const diff = Math.abs(camA.n - camB.n);
        if (diff === 1 || diff === 11) return 0.7;                       // adjacent same letter (+wrap 12↔1)
    }
    return 0.4;                                                          // incompatible
}

function dbToLin(db) {
    return Math.pow(10, db / 20);
}

const CROSSFADE_TARGET_LUFS        = -14;   // Spotify standard
const CROSSFADE_DURATION_MIN       = 2.0;
const CROSSFADE_DURATION_MAX       = 12.0;
const CROSSFADE_MAX_GAIN_BOOST_DB  = 12.0;  // cap LUFS compensation at +12 dB to avoid clipping quiet outliers

// Mood distance helpers — Q1..Q4 from mood_quadrant strings like "Q1: Happy/Excited"
function _quadOf(mqStr) {
    const m = mqStr && mqStr.match(/Q(\d)/);
    return m ? parseInt(m[1], 10) : 0;
}

// Adjacent quads share exactly one V-A axis boundary:
//   Q1(V+A+) ↔ Q2(V-A+), Q1 ↔ Q4(V+A-), Q2 ↔ Q3(V-A-), Q3 ↔ Q4
// Opposite quads differ on both axes: Q1↔Q3, Q2↔Q4
const _QUAD_ADJACENT = new Set(['1-2','2-1','1-4','4-1','2-3','3-2','3-4','4-3']);

// Returns 1.0 = same quad | 0.5 = adjacent | 0.0 = opposite quad
function _moodScore(mqA, mqB) {
    const a = _quadOf(mqA), b = _quadOf(mqB);
    if (!a || !b) return 0.5;       // unknown → neutral
    if (a === b)  return 1.0;
    if (_QUAD_ADJACENT.has(`${a}-${b}`)) return 0.5;
    return 0.0;
}

/**
 * Compute a complete crossfade plan from track features.
 *
 * @param {Object} trackA - Current track (needs tempo, energy, key, mode, mood_quadrant,
 *                          duration_s; optional: loudness_lufs, fade_out_cue_s, downbeat_times_json)
 * @param {Object} trackB - Next track (same shape as trackA, optional fade_in_cue_s)
 * @param {number} userBaseVolume - User's current volume 0..1
 * @returns {{duration_s, fadeOutStartAt_s, fadeInStartAt_s, gainA, gainB, curve, debug}}
 */
function planCrossfade(trackA, trackB, userBaseVolume) {
    // Safe defaults nếu thiếu data — never crash, but never assume "perfect match"
    // when data is absent (would lead to over-optimistic 10s smooth blend on unknown pairs).
    const Atempo  = Number.isFinite(trackA?.tempo) ? trackA.tempo : 120;
    const Btempo  = Number.isFinite(trackB?.tempo) ? trackB.tempo : 120;
    const Aenergy = Number.isFinite(trackA?.energy) ? trackA.energy : 0.5;
    const Benergy = Number.isFinite(trackB?.energy) ? trackB.energy : 0.5;
    const AdurS   = Number.isFinite(trackA?.duration_s) ? trackA.duration_s : 180;
    const BdurS   = Number.isFinite(trackB?.duration_s) ? trackB.duration_s : 180;

    // Track which features actually exist (without defaults) so we don't claim "same key"
    // when in reality both are just falling back to "key=0 major".
    const moodKnown = !!trackA?.mood_quadrant && !!trackB?.mood_quadrant;
    const keyKnown  = Number.isFinite(trackA?.key) && Number.isFinite(trackB?.key)
                   && Number.isFinite(trackA?.mode) && Number.isFinite(trackB?.mode);

    // 1. Feature deltas
    const dTempo    = Math.abs(Atempo - Btempo) / Math.max(Atempo, 1);
    const dEnergy   = Math.abs(Aenergy - Benergy);
    const moodScore = moodKnown ? _moodScore(trackA.mood_quadrant, trackB.mood_quadrant) : 0.5;
    const sameQuad  = moodScore >= 1.0;   // kept for correlated-curve check below
    const keyCompat = keyKnown
        ? camelotCompatible(Math.round(trackA.key), trackA.mode, Math.round(trackB.key), trackB.mode)
        : 0.4;   // unknown key → treat as incompatible (safe)

    // 2. Duration policy (Bittner 2017 + Spotify defaults)
    // Priority tiers (if/else, cannot override each other):
    //   clash (3s) > perfect (10s) > adjacent+key (8s) = EDM pair (8s) > mood-clash (4s) > default (6s)
    let duration;
    if (dTempo > 0.10 || dEnergy > 0.4) {
        duration = 3.0;    // audio clash: big tempo or energy jump → fast cut
    } else if (moodScore >= 1.0 && dTempo < 0.06 && keyCompat >= 0.7) {
        duration = 10.0;   // perfect: same mood + close tempo + Camelot-compatible
    } else if (moodScore >= 0.5 && dTempo < 0.06 && keyCompat >= 0.7) {
        duration = 8.0;    // adjacent mood + close tempo + key-compatible
    } else if (Aenergy > 0.75 && Benergy > 0.75) {
        duration = 8.0;    // EDM pair: both high-energy, no audio clash
    } else if (moodScore === 0.0) {
        duration = 4.0;    // mood clash (Q1↔Q3 or Q2↔Q4) → shorter than default
    } else {
        duration = 6.0;    // default
    }
    // Short-track safety: ensure we don't crossfade longer than 30% of track A
    if (AdurS > 0) duration = Math.min(duration, AdurS * 0.3);
    duration = Math.max(CROSSFADE_DURATION_MIN, Math.min(CROSSFADE_DURATION_MAX, duration));

    // 3. Cue points (Zehren 2020 / Foote 2000 — fall back to heuristic)
    const fadeOutStart = Number.isFinite(trackA?.fade_out_cue_s)
        ? trackA.fade_out_cue_s
        : Math.max(0, AdurS - duration - 5);
    let fadeInStart = Number.isFinite(trackB?.fade_in_cue_s)
        ? trackB.fade_in_cue_s
        : (BdurS > 45 ? 10 : 0);

    // 3b. Beat-align for danceable pairs (Phase 3)
    const danceableA = Number.isFinite(trackA?.danceability) && trackA.danceability > 0.7;
    const danceableB = Number.isFinite(trackB?.danceability) && trackB.danceability > 0.7;
    if (danceableA && danceableB && dTempo < 0.08 && trackB?.downbeat_times_json) {
        try {
            const downbeats = typeof trackB.downbeat_times_json === 'string'
                ? JSON.parse(trackB.downbeat_times_json)
                : trackB.downbeat_times_json;
            if (Array.isArray(downbeats) && downbeats.length > 0) {
                const snapTo = downbeats.find(t => t >= fadeInStart);
                if (Number.isFinite(snapTo)) fadeInStart = snapTo;
            }
        } catch (_e) {
            // ignore invalid downbeat data
        }
    }

    // 4. Loudness-matched gains (ITU-R BS.1770 / EBU R128)
    // Correction capped at +CROSSFADE_MAX_GAIN_BOOST_DB so very quiet outliers
    // (e.g. -36 LUFS) don't get a ×13 boost that hits the unity clamp and sounds wrong.
    const hasLUFS = Number.isFinite(trackA?.loudness_lufs) && Number.isFinite(trackB?.loudness_lufs);
    const clamp   = v => Math.min(1.0, Math.max(0, v));
    const _lufsGain = (lufs) => Math.min(dbToLin(CROSSFADE_MAX_GAIN_BOOST_DB),
                                          dbToLin(CROSSFADE_TARGET_LUFS - lufs));
    const gainA = hasLUFS ? clamp(userBaseVolume * _lufsGain(trackA.loudness_lufs)) : userBaseVolume;
    const gainB = hasLUFS ? clamp(userBaseVolume * _lufsGain(trackB.loudness_lufs)) : userBaseVolume;

    // 5. Curve choice (Audacity / KVR consensus)
    // Linear when tracks are highly correlated (same quad + key + tempo) → softer cancellation
    // Equal-power otherwise → constant total perceived loudness for uncorrelated signals
    const correlated = sameQuad && dTempo < 0.03 && keyCompat === 1.0;
    const curve = correlated ? 'linear' : 'equal-power';

    const plan = {
        duration_s: duration,
        fadeOutStartAt_s: fadeOutStart,
        fadeInStartAt_s: fadeInStart,
        gainA, gainB,
        curve,
        debug: { dTempo, dEnergy, sameQuad, keyCompat, hasLUFS, danceablePair: danceableA && danceableB },
    };

    // Optional debug log (gate behind localStorage flag)
    if (typeof localStorage !== 'undefined' && localStorage.getItem('bf_crossfade_debug') === 'true') {
        console.log('[crossfade]', {
            A: trackA?.track_name || '(?)',
            B: trackB?.track_name || '(?)',
            dTempo: dTempo.toFixed(3),
            dEnergy: dEnergy.toFixed(3),
            moodScore,
            keyCompat,
            duration_s: duration.toFixed(2),
            curve,
            gainA: gainA.toFixed(2),
            gainB: gainB.toFixed(2),
            hasLUFS,
            danceablePair: danceableA && danceableB,
            fadeOutCue: trackA?.fade_out_cue_s,
        });
    }

    return plan;
}

// Export for tests (browser global)
if (typeof window !== 'undefined') {
    window._smartCrossfade = { planCrossfade, camelotCompatible, toCamelot, dbToLin, CAMELOT_MAP,
                               _moodScore, _quadOf };
}

