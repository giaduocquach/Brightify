import { useStore } from '../state/store';
import { vaToHex } from '../three/va';

// Visualises the Iso-Principle journey: a gradient A→B track with a marker that eases along it
// by the current song's V-A projected onto the A→B line — so the gradual mood transition is
// VISIBLE ("started Đam mê, arriving Vui vẻ"). Falls back to queue position before playback.
export default function JourneyArc() {
  const bridge = useStore((s) => s.bridge);
  const current = useStore((s) => s.current);
  const queue = useStore((s) => s.queue);
  const index = useStore((s) => s.index);

  if (!bridge || bridge.length < 2) return null;
  const [A, B] = bridge;

  let p = queue.length > 1 && index >= 0 ? index / (queue.length - 1) : 0;
  if (current) {
    const dv = B.valence - A.valence;
    const da = B.arousal - A.arousal;
    const len2 = dv * dv + da * da;
    if (len2 > 1e-6) {
      const t = ((current.valence - A.valence) * dv + (current.arousal - A.arousal) * da) / len2;
      p = Math.max(0, Math.min(1, t));
    }
  }

  return (
    <div className="journey-arc">
      <span className="ja-end" style={{ color: A.hex }} title={`V ${A.valence.toFixed(2)} · A ${A.arousal.toFixed(2)}`}>
        {A.emotion_vi}
      </span>
      <div className="ja-track" style={{ ['--c-from' as string]: A.hex, ['--c-to' as string]: B.hex }}>
        <div className="ja-grad" aria-hidden="true" />
        <div
          className="ja-marker"
          style={{ left: `${p * 100}%`, background: current ? vaToHex(current.valence, current.arousal) : '#fff' }}
          aria-hidden="true"
        />
      </div>
      <span className="ja-end" style={{ color: B.hex }} title={`V ${B.valence.toFixed(2)} · A ${B.arousal.toFixed(2)}`}>
        {B.emotion_vi}
      </span>
    </div>
  );
}
