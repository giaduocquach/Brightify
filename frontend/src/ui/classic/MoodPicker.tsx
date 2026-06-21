import { EMOTION_COLORS } from '../../data/colors';
import { useStore } from '../../state/store';

// Visible 12-colour mood picker — the 2D counterpart of the 3D planets. Clicking a swatch
// drives the SAME colour→recommendation path as the immersive skin (toggleColor), minus the
// camera (opts.noTransitions). 1 colour = static mood, 2 = mood journey.
export default function MoodPicker() {
  const selected = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);

  return (
    <div className="mood-picker">
      <div className="mood-picker-head">
        <h3>Chọn cảm xúc</h3>
        <p className="mood-picker-hint">1 màu = nghe theo tâm trạng · 2 màu = hành trình cảm xúc</p>
      </div>
      <div className="mood-grid">
        {EMOTION_COLORS.map((c) => {
          const on = selected.includes(c.hex);
          return (
            <button
              key={c.hex}
              className={`mood-swatch${on ? ' is-on' : ''}`}
              aria-pressed={on}
              onClick={() => toggleColor(c.hex, { noTransitions: true })}
              title={`${c.label} — ${c.emotion}`}
            >
              <span className="mood-chip" style={{ background: c.hex }} aria-hidden="true" />
              <span className="mood-label">
                <span className="mood-name">{c.label}</span>
                <span className="mood-emotion">{c.emotion}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
