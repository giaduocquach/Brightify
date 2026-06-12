import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';
import ResultsList from './ResultsList';

export default function ColorscapeHome() {
  const selected = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);
  const clearColors = useStore((s) => s.clearColors);
  const setHover = useStore((s) => s.setHover);

  return (
    <div className="home">
      <header className="home-header">
        <h1 className="home-title">Hôm nay bạn cảm thấy màu gì?</h1>
        <p className="home-sub">
          Chạm vào một quả cầu cảm xúc — AI tìm nhạc đúng vibe.
          <span className="home-hint"> Kéo để xoay không gian, lăn chuột để phóng to.</span>
        </p>
      </header>

      {/* Keyboard / screen-reader accessible colour controls (the visual orbs
          live in the 3D canvas). */}
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

      {selected.length > 0 && (
        <div className="home-selected">
          {selected.map((hex) => {
            const c = EMOTION_COLORS.find((x) => x.hex === hex);
            return (
              <button
                key={hex}
                className="selected-chip"
                style={{ ['--chip' as string]: hex }}
                onClick={() => toggleColor(hex)}
                title={`Bỏ ${c?.label ?? hex}`}
              >
                <span className="chip-dot" />
                {c?.label ?? hex}
                <span className="chip-x" aria-hidden="true">×</span>
              </button>
            );
          })}
          <button className="selected-clear" onClick={clearColors}>Xoá hết</button>
        </div>
      )}

      <ResultsList />
    </div>
  );
}
