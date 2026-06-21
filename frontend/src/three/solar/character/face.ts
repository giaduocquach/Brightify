// Deterministic facial expression from the now-playing song's valence-arousal mood. Pure math,
// no model calls — the same V-A spine the rest of the app uses. Drives the chibi astronaut's
// eyes/brows/mouth/blush so it visibly FEELS the music:
//   happy (hi-v)        → smile, raised brows, bright squinty eyes
//   calm (hi-v lo-a)    → soft smile, half-lidded
//   sad (lo-v lo-a)     → frown, droopy eyes, inner-brow worry
//   tense (lo-v hi-a)   → flat/lowered mouth, narrowed eyes, lowered angled brows
function clamp(lo: number, hi: number, x: number) {
  return Math.max(lo, Math.min(hi, x));
}

export interface Expression {
  mouthCurve: number; // -1 frown … +1 smile
  mouthOpen: number;  // 0 closed … 1 open (energetic)
  browLift: number;   // -1 lowered (tense) … +1 raised (happy/surprised)
  browTilt: number;   // -1 inner-down (angry) … +1 inner-up (sad worry)
  eyeOpen: number;    // ~0.55 sleepy … ~1.3 wide
  blush: number;      // 0 … ~0.85
}

export function expressionFor(valence: number, arousal: number): Expression {
  const v = clamp(0, 1, valence);
  const a = clamp(0, 1, arousal);
  const sad = v < 0.5;
  const tense = sad && a > 0.55;

  const squint = Math.max(0, (v - 0.55) + (a - 0.55)); // joyful squint when both high
  return {
    mouthCurve: clamp(-1, 1, (v - 0.5) * 2.2),
    mouthOpen: Math.max(0, a - 0.45) * 0.7,
    browLift: clamp(-1, 1, (v - 0.5) * 1.7 - (tense ? (a - 0.55) * 1.6 : 0)),
    browTilt: sad ? (tense ? -(0.5 - v) * 2 : (0.5 - v) * 2) : 0,
    eyeOpen: clamp(0.5, 1.35, 0.6 + a * 0.7 - squint * 0.45),
    blush: clamp(0, 0.85, 0.22 + a * 0.6),
  };
}

export const NEUTRAL: Expression = expressionFor(0.5, 0.5);

// Per-frame ease toward a target expression (dt-aware), so a track change melts into the new
// mood over ~0.5s rather than snapping. Mutates `cur` in place.
export function easeExpression(cur: Expression, target: Expression, k: number) {
  cur.mouthCurve += (target.mouthCurve - cur.mouthCurve) * k;
  cur.mouthOpen += (target.mouthOpen - cur.mouthOpen) * k;
  cur.browLift += (target.browLift - cur.browLift) * k;
  cur.browTilt += (target.browTilt - cur.browTilt) * k;
  cur.eyeOpen += (target.eyeOpen - cur.eyeOpen) * k;
  cur.blush += (target.blush - cur.blush) * k;
}
