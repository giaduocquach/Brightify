import { useStore } from '../state/store';
import SongRow from './SongRow';

export default function ResultsList() {
  const results = useStore((s) => s.results);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const playSong = useStore((s) => s.playSong);

  if (loading) {
    return (
      <div className="results-panel">
        <div className="results-loading"><span className="spinner" /> AI đang phân tích màu…</div>
      </div>
    );
  }
  if (error) return <div className="results-panel"><div className="results-empty">{error}</div></div>;
  if (!results.length) return null;

  const playable = results.filter((s) => s.has_audio);

  return (
    <div className="results-panel">
      {playable.length > 0 && (
        <div className="results-head">
          <button className="btn-play-all" onClick={() => playSong(playable[0], playable)}>
            <span aria-hidden="true">▶</span> Phát tất cả
          </button>
        </div>
      )}
      <div className="results-list">
        {results.map((s, i) => (
          <SongRow key={s.track_id || i} song={s} index={i} queue={results} />
        ))}
      </div>
    </div>
  );
}
