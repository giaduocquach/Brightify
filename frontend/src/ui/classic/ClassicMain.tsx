import { useStore } from '../../state/store';
import ResultsList from '../ResultsList';
import SongRow from '../SongRow';
import BrowseLibrary from './BrowseLibrary';
import { EMOTION_COLORS } from '../../data/colors';

function moodName(hex: string): string {
  return EMOTION_COLORS.find((c) => c.hex === hex)?.label ?? 'Màu';
}

// Resolves the main content pane from store state (lyrics is a separate overlay in ClassicApp):
//   colour selected → recommendation list · radio (fly) → live queue · otherwise → library.
export default function ClassicMain() {
  const selectedColors = useStore((s) => s.selectedColors);
  const mode = useStore((s) => s.mode);
  const queue = useStore((s) => s.queue);
  const current = useStore((s) => s.current);
  const clearColors = useStore((s) => s.clearColors);
  const playSong = useStore((s) => s.playSong);

  // 1) Colour/mood recommendation pane
  if (selectedColors.length > 0) {
    const title = selectedColors.length === 2
      ? `Hành trình: ${moodName(selectedColors[0])} → ${moodName(selectedColors[1])}`
      : `Tâm trạng: ${moodName(selectedColors[0])}`;
    return (
      <main className="classic-main">
        <div className="pane-head">
          <h2>{title}</h2>
          <button className="pane-back" onClick={clearColors}>← Thư viện</button>
        </div>
        <ResultsList />
      </main>
    );
  }

  // 2) Endless radio ("Tương tự") pane — the live queue
  if (mode === 'fly') {
    const playable = queue.filter((s) => s.has_audio);
    return (
      <main className="classic-main">
        <div className="pane-head">
          <h2>Đài tương tự{current ? `: ${current.track_name}` : ''}</h2>
          <button className="pane-back" onClick={clearColors}>← Thư viện</button>
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

  // 3) Default: browsable library
  return (
    <main className="classic-main">
      <BrowseLibrary />
    </main>
  );
}
