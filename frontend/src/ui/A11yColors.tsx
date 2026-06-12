import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';

// Screen-reader / keyboard-accessible mirror of the 3D planets: the visual orbs
// live in the canvas, so these off-screen buttons give non-pointer users (and the
// headless smoke test) the same colour-selection path. Always mounted.
export default function A11yColors() {
  const selected = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);
  const setHover = useStore((s) => s.setHover);

  return (
    <div className="sr-only">
      <h2>Chọn màu cảm xúc</h2>
      {EMOTION_COLORS.map((c) => (
        <button
          key={c.hex}
          aria-pressed={selected.includes(c.hex)}
          onClick={() => toggleColor(c.hex)}
          onFocus={() => setHover(c.hex)}
          onBlur={() => setHover(null)}
        >
          {c.label} — {c.emotion}
        </button>
      ))}
    </div>
  );
}
