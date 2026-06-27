import { EMOTION_COLORS } from '../../data/colors';
import { useStore } from '../../state/store';

// The 12-colour mood picker — the 2D counterpart of the 3D planets. Clicking a swatch drives the
// SAME colour→recommendation path as the immersive skin (toggleColor), minus the camera
// (opts.noTransitions). 1 colour = static mood, 2 = mood journey.
//   variant='hero'  → large labelled grid, the home page's headline control ("nhìn-là-hiểu").
//   variant='strip' → slim horizontal row above the results, so the mood can be re-picked in one click.
export default function MoodPicker({ variant = 'hero' }: { variant?: 'hero' | 'strip' }) {
  const selected = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);

  return (
    <div className={`mood-picker mood-picker--${variant}`}>
      {variant === 'hero' && (
        <p className="mood-picker-hint">1 màu = một tâm trạng · 2 màu = hành trình cảm xúc A → B</p>
      )}
      <div className="mood-grid">
        {EMOTION_COLORS.map((c) => {
          const on = selected.includes(c.hex);
          return (
            <button
              key={c.hex}
              className={`mood-swatch${on ? ' is-on' : ''}`}
              aria-pressed={on}
              onClick={() => toggleColor(c.hex, { noTransitions: true })}
              title={`Phát nhạc theo màu ${c.label}`}
            >
              <span className="mood-chip" style={{ background: c.hex }} aria-hidden="true" />
              <span className="mood-name">{c.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
