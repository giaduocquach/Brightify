import { useStore } from '../state/store';
import { EMOTION_COLORS } from '../data/colors';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';
import WhyColorPanel from './WhyColorPanel';

// Shown while exploring a single planet: which body, its emotion, and the songs of
// that colour (reuses the existing ResultsList + player path).
export default function ExploreHUD() {
  const hex = useStore((s) => s.selectedColors[0]);
  const clearColors = useStore((s) => s.clearColors);
  const bridge = useStore((s) => s.bridge);
  const results = useStore((s) => s.results);
  const showPlaylist = useStore((s) => s.showPlaylist);

  if (!hex) return null;
  const color = EMOTION_COLORS.find((c) => c.hex === hex);
  const body = bodyByHex(hex);

  return (
    <div className="hud" style={{ ['--accent-hex' as string]: hex }}>
      <div className="hud-head">
        <span className="hud-eyebrow">Đang khám phá hành tinh</span>
        <h2 className="hud-title">{body?.name ?? color?.label}</h2>
        <p className="hud-emotion"><span className="hud-dot" /> {color?.label} · {color?.emotion}</p>
        <WhyColorPanel bridge={bridge} songs={results} />
      </div>
      {showPlaylist && <ResultsList />}
      <button className="hud-back" onClick={clearColors}><span aria-hidden="true">←</span> Về hệ mặt trời</button>
    </div>
  );
}
