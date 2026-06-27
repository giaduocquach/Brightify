import { useStore } from '../../state/store';
import ResultsList from '../ResultsList';
import SongRow from '../SongRow';
import ClassicHome from './ClassicHome';
import Library from './Library';
import MoodPicker from './MoodPicker';
import { EMOTION_COLORS } from '../../data/colors';

function moodName(hex: string): string {
  return EMOTION_COLORS.find((c) => c.hex === hex)?.label ?? 'Màu';
}

// Resolves the main content pane from store state (lyrics is a separate overlay in ClassicApp).
// Priority: radio (fly) → colour recommendation → the active nav tab (home / library).
export default function ClassicMain() {
  const selectedColors = useStore((s) => s.selectedColors);
  const mode = useStore((s) => s.mode);
  const classicTab = useStore((s) => s.classicTab);
  const queue = useStore((s) => s.queue);
  const current = useStore((s) => s.current);
  const clearColors = useStore((s) => s.clearColors);
  const playSong = useStore((s) => s.playSong);

  // 1) Endless radio ("Tương tự") pane — the live queue.
  if (mode === 'fly') {
    const playable = queue.filter((s) => s.has_audio);
    return (
      <main className="classic-main">
        <div className="pane-head">
          <h2>Đài tương tự{current ? `: ${current.track_name}` : ''}</h2>
          <button className="pane-back" onClick={clearColors}>← Trang chủ</button>
        </div>
        <div className="results-panel">
          {playable.length > 0 && (
            <div className="results-head">
              <button className="btn-play-all" onClick={() => playSong(playable[0], queue)}>
                <span aria-hidden="true">▶</span> Phát từ đầu
              </button>
            </div>
          )}
          <div className="results-list">
            {queue.map((s, i) => <SongRow key={s.track_id || i} song={s} index={i} queue={queue} />)}
          </div>
        </div>
      </main>
    );
  }

  // 2) Colour/mood recommendation pane. The compact swatch strip lets the mood be re-picked here.
  if (selectedColors.length > 0) {
    const title = selectedColors.length === 2
      ? `Hành trình: ${moodName(selectedColors[0])} → ${moodName(selectedColors[1])}`
      : `Tâm trạng: ${moodName(selectedColors[0])}`;
    return (
      <main className="classic-main">
        <div className="pane-head">
          <h2>{title}</h2>
          <button className="pane-back" onClick={clearColors}>← Trang chủ</button>
        </div>
        <MoodPicker variant="strip" />
        <ResultsList />
      </main>
    );
  }

  // 3) Default: the active nav tab.
  return (
    <main className="classic-main">
      {classicTab === 'library' ? <Library /> : <ClassicHome />}
    </main>
  );
}
