import type { ColorResult } from '../api/client';

// The colour → emotion → Valence-Arousal chain the backend computes (query.bridge) but the
// UI never showed. This makes the thesis claim visible: each chosen colour, its emotion word,
// and its V·A coordinate. One quiet line per colour.
export default function BridgeChip({ bridge }: { bridge: ColorResult['bridge'] }) {
  if (!bridge || !bridge.length) return null;
  return (
    <div className="bridge-chips">
      {bridge.map((b) => (
        <span className="bridge-chip" key={b.hex}>
          <span className="bridge-dot" style={{ background: b.hex }} aria-hidden="true" />
          <span className="bridge-emotion">{b.emotion_vi}</span>
          <span className="bridge-va">V {b.valence.toFixed(2)} · A {b.arousal.toFixed(2)}</span>
        </span>
      ))}
    </div>
  );
}
