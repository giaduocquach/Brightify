import { useStore } from '../state/store';
import { EMOTION_COLORS } from '../data/colors';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';
import LyricsPanel from './LyricsPanel';

// Shown while exploring a single planet: just which body, then a plain playlist of
// its songs (or the lyrics view). No emotion labels / explainers — keep it simple.
export default function ExploreHUD() {
  const hex = useStore((s) => s.selectedColors[0]);
  const clearColors = useStore((s) => s.clearColors);
  const showPlaylist = useStore((s) => s.showPlaylist);
  const showLyrics = useStore((s) => s.showLyrics);

  if (!hex) return null;
  const body = bodyByHex(hex);
  const color = EMOTION_COLORS.find((c) => c.hex === hex);

  return (
    <div className="hud">
      <div className="hud-head">
        <span className="hud-eyebrow">Đang khám phá hành tinh</span>
        <h2 className="hud-title">{body?.name ?? color?.label}</h2>
      </div>
      {showLyrics ? <LyricsPanel /> : showPlaylist && <ResultsList />}
      <button className="hud-back" onClick={clearColors}><span aria-hidden="true">←</span> Về hệ mặt trời</button>
    </div>
  );
}
