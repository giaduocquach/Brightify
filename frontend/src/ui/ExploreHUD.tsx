import { useStore } from '../state/store';
import { EMOTION_COLORS } from '../data/colors';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';

// Shown while exploring a single planet: which body, its emotion, and the songs of
// that colour (reuses the existing ResultsList + player path).
export default function ExploreHUD() {
  const hex = useStore((s) => s.selectedColors[0]);
  const clearColors = useStore((s) => s.clearColors);

  if (!hex) return null;
  const color = EMOTION_COLORS.find((c) => c.hex === hex);
  const body = bodyByHex(hex);

  return (
    <div className="hud" style={{ ['--accent-hex' as string]: hex }}>
      <div className="hud-head">
        <span className="hud-eyebrow">Đang khám phá hành tinh</span>
        <h2 className="hud-title">{body?.name ?? color?.label}</h2>
        <p className="hud-emotion"><span className="hud-dot" /> {color?.label} · {color?.emotion}</p>
      </div>
      <ResultsList />
      <button className="hud-back" onClick={clearColors}>← Về hệ mặt trời</button>
    </div>
  );
}
