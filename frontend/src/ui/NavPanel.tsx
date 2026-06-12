import { BODIES } from '../three/solar/bodies';
import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';

// Persistent corner control panel — pick the next destination planet from any mode.
// Reuses the existing toggleColor (max-2 → explore/journey), so the recommend flow
// is unchanged. Doubles as a labelled, pointer-accessible mirror of the 3D planets.
export default function NavPanel() {
  const sel = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);
  const clearColors = useStore((s) => s.clearColors);
  const setHover = useStore((s) => s.setHover);

  return (
    <nav className="navpanel" aria-label="Chọn điểm đến">
      <div className="navpanel-head">
        <span className="navpanel-led" aria-hidden="true" />
        <span className="navpanel-title">NAV · ĐIỂM ĐẾN</span>
        <button className="navpanel-home" onClick={clearColors} title="Về hệ mặt trời" aria-label="Về hệ mặt trời">⌂</button>
      </div>
      <div className="navpanel-grid">
        {BODIES.map((b) => {
          const c = EMOTION_COLORS.find((x) => x.hex === b.hex);
          const active = sel.includes(b.hex);
          return (
            <button
              key={b.hex}
              className={`nav-dot${active ? ' is-active' : ''}`}
              style={{ ['--c' as string]: b.hex }}
              aria-pressed={active}
              onClick={() => toggleColor(b.hex)}
              onMouseEnter={() => setHover(b.hex)}
              onMouseLeave={() => setHover(null)}
              title={`${b.name} · ${c?.emotion ?? ''}`}
            >
              <span className="nav-swatch" />
              <span className="nav-name">{b.name}</span>
            </button>
          );
        })}
      </div>
      {sel.length === 2 && <div className="navpanel-hint">Du hành 2 hành tinh 🚀</div>}
    </nav>
  );
}
