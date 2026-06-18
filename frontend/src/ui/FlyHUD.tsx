import { useStore } from '../state/store';
import SongRow from './SongRow';
import LyricsPanel from './LyricsPanel';

// Free-flight ("Tương tự") panel: the live radio queue seeded by the song that was
// playing — now-playing first, then what plays next, growing endlessly as it tops up.
// Mirrors JourneyHUD so it reads consistently with the rest of the app.
export default function FlyHUD() {
  const tracks = useStore((s) => s.queue);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const current = useStore((s) => s.current);
  const playSong = useStore((s) => s.playSong);
  const enterSystem = useStore((s) => s.enterSystem);
  const showPlaylist = useStore((s) => s.showPlaylist);
  const showLyrics = useStore((s) => s.showLyrics);

  const playable = tracks.filter((s) => s.has_audio);

  return (
    <div className="hud hud--journey">
      <div className="hud-head">
        <span className="hud-eyebrow">Bài tương tự <span aria-hidden="true">✦</span></span>
        <h2 className="hud-title">{current ? current.track_name : 'Khám phá'}</h2>
      </div>

      {showLyrics && <LyricsPanel />}
      {!showLyrics && showPlaylist && (
        <div className="results-panel">
          {loading ? (
            <div className="results-loading"><span className="spinner" /> Đang tìm bài tương tự…</div>
          ) : error ? (
            <div className="results-empty">{error}</div>
          ) : !tracks.length ? (
            <div className="results-empty">Không có bài tương tự.</div>
          ) : (
            <>
              {playable.length > 0 && (
                <div className="results-head">
                  <button className="btn-play-all" onClick={() => playSong(playable[0], tracks)}>
                    <span aria-hidden="true">▶</span> Phát từ đầu
                  </button>
                </div>
              )}
              <div className="results-list">
                {tracks.map((s, i) => (
                  <SongRow key={s.track_id || i} song={s} index={i} queue={tracks} />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <button className="hud-back" onClick={enterSystem}><span aria-hidden="true">←</span> Về hệ mặt trời</button>
    </div>
  );
}
