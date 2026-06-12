import { useStore } from '../state/store';
import type { Song } from '../api/client';
import { vaToHex } from '../three/va';

function Row({ song, index }: { song: Song; index: number }) {
  const current = useStore((s) => s.current?.track_id === song.track_id);
  const playSong = useStore((s) => s.playSong);
  const results = useStore((s) => s.results);
  const disabled = !song.has_audio;
  // Mood colour from the song's V-A (why it was recommended) — NOT its album-art
  // palette, which is unrelated to emotion and looked random next to the picked colour.
  const moodHex = vaToHex(song.valence, song.arousal);

  return (
    <button
      className={`result-row${current ? ' is-playing' : ''}`}
      onClick={() => !disabled && playSong(song, results)}
      disabled={disabled}
      title={disabled ? 'Chưa có audio' : `Phát ${song.track_name}`}
    >
      <span className="result-num">{current ? '♪' : index + 1}</span>
      <span className="result-art" style={{ background: moodHex }}>
        {song.album_art_url && (
          <img src={song.album_art_url} alt="" loading="lazy" />
        )}
      </span>
      <span className="result-meta">
        <span className="result-title">{song.track_name}</span>
        <span className="result-artist">{song.artist}</span>
        {song.why?.reason && <span className="result-why">{song.why.reason}</span>}
      </span>
      <span className="result-dot" style={{ background: moodHex }} aria-hidden="true" />
    </button>
  );
}

export default function ResultsList() {
  const results = useStore((s) => s.results);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const journey = useStore((s) => s.journey);
  const selected = useStore((s) => s.selectedColors);
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
      {journey?.from && journey?.to && (
        <div
          className="journey-banner"
          style={{ ['--c-from' as string]: journey.from.hex, ['--c-to' as string]: journey.to.hex }}
        >
          <span className="journey-grad" aria-hidden="true" />
          Hành trình: <strong>{journey.from.mood}</strong> → <strong>{journey.to.mood}</strong>
        </div>
      )}
      <div className="results-head">
        <span className="results-count">{results.length} bài cho {selected.length} màu</span>
        {playable.length > 0 && (
          <button className="btn-play-all" onClick={() => playSong(playable[0], playable)}>
            ▶ Phát tất cả
          </button>
        )}
      </div>
      <div className="results-list">
        {results.map((s, i) => (
          <Row key={s.track_id || i} song={s} index={i} />
        ))}
      </div>
    </div>
  );
}
