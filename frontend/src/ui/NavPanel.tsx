import { useEffect, useRef } from 'react';
import { Search } from 'lucide-react';
import { BODIES } from '../three/solar/bodies';
import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';

// Persistent corner control panel — pick the next destination planet from any mode.
// Reuses the existing toggleColor (max-2 → explore/journey), so the recommend flow
// is unchanged. Doubles as a labelled, pointer-accessible mirror of the 3D planets.
export default function NavPanel() {
  const sel = useStore((s) => s.selectedColors);
  const toggleColor = useStore((s) => s.toggleColor);
  const setHover = useStore((s) => s.setHover);
  const openSearch = useStore((s) => s.openSearch);

  // When the intro greeting is dismissed this panel mounts; move focus here so keyboard
  // users aren't dropped on <body> (the canvas itself isn't a focus target).
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => { navRef.current?.focus(); }, []);

  return (
    <nav className="navpanel" aria-label="Chọn hành tinh cảm xúc" ref={navRef} tabIndex={-1}>
      <div className="navpanel-head">
        <span className="navpanel-led" aria-hidden="true" />
        <span className="navpanel-title">CHỌN HÀNH TINH</span>
        <button
          className="navpanel-search"
          onClick={openSearch}
          aria-label="Tìm kiếm bài hát"
          title="Tìm kiếm — / hoặc ⌘K"
        ><Search size={15} strokeWidth={2.2} /></button>
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
      {sel.length === 2 && <div className="navpanel-hint">Du hành 2 hành tinh <span aria-hidden="true">🚀</span></div>}
    </nav>
  );
}
