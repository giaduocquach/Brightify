import { useStore } from '../state/store';
import { vaToHex } from '../three/va';

function fmt(s: number) {
  if (!Number.isFinite(s) || s < 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

export default function PlayerBar() {
  const current = useStore((s) => s.current);
  const isPlaying = useStore((s) => s.isPlaying);
  const time = useStore((s) => s.time);
  const duration = useStore((s) => s.duration);
  const volume = useStore((s) => s.volume);
  const crossfadeEnabled = useStore((s) => s.crossfadeEnabled);
  const playbackError = useStore((s) => s.playbackError);
  const showPlaylist = useStore((s) => s.showPlaylist);
  const showLyrics = useStore((s) => s.showLyrics);
  const { togglePlay, next, prev, seek, setVolume, toggleCrossfade, playSimilar, togglePlaylist, toggleLyrics } = useStore.getState();

  if (!current) return null;
  const pct = duration > 0 ? (time / duration) * 100 : 0;

  const onSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    seek(((e.clientX - r.left) / r.width) * duration);
  };

  // Keyboard operability for the slider (WCAG 2.1.1): arrows ±5s, PageUp/Dn ±10s, Home/End.
  const onSeekKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!duration) return;
    let t = time;
    switch (e.key) {
      case 'ArrowLeft': case 'ArrowDown': t = time - 5; break;
      case 'ArrowRight': case 'ArrowUp': t = time + 5; break;
      case 'PageDown': t = time - 10; break;
      case 'PageUp': t = time + 10; break;
      case 'Home': t = 0; break;
      case 'End': t = duration; break;
      default: return;
    }
    e.preventDefault();
    seek(Math.max(0, Math.min(duration, t)));
  };

  return (
    <div className="player">
      {playbackError && <div className="player-error" role="status" aria-live="polite">{playbackError}</div>}
      <div className="player-track">
        <span className="player-art" style={{ background: vaToHex(current.valence, current.arousal) }}>
          {current.album_art_url && <img src={current.album_art_url} alt="" />}
        </span>
        <span className="player-meta">
          <span className="player-title">{current.track_name}</span>
          <span className="player-artist">{current.artist}</span>
        </span>
      </div>

      <div className="player-center">
        <div className="player-buttons">
          <button onClick={prev} aria-label="Bài trước" className="pbtn">⏮</button>
          <button onClick={togglePlay} aria-label={isPlaying ? 'Tạm dừng' : 'Phát'} className="pbtn pbtn-play">
            {isPlaying ? '⏸' : '▶'}
          </button>
          <button onClick={next} aria-label="Bài tiếp" className="pbtn">⏭</button>
        </div>
        <div className="player-progress">
          <span className="ptime">{fmt(time)}</span>
          <div className="pbar" onClick={onSeek} onKeyDown={onSeekKey} tabIndex={0}
               role="slider" aria-label="Tiến độ" aria-valuemin={0}
               aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(time)}
               aria-valuetext={`${fmt(time)} / ${fmt(duration)}`}>
            <div className="pbar-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="ptime">{fmt(duration)}</span>
        </div>
      </div>

      <div className="player-right">
        <button
          className={`pbtn pbtn-toggle${showPlaylist ? ' is-on' : ''}`}
          onClick={togglePlaylist}
          aria-pressed={showPlaylist}
          aria-label="Ẩn/hiện danh sách phát"
          title="Ẩn/hiện danh sách phát"
        ><span aria-hidden="true">☰</span></button>
        <button
          className={`pbtn pbtn-toggle${showLyrics ? ' is-on' : ''}`}
          onClick={toggleLyrics}
          aria-pressed={showLyrics}
          aria-label="Lời bài hát"
          title="Lời bài hát"
        ><span aria-hidden="true">♬</span></button>
        <button
          className={`pbtn-pill${crossfadeEnabled ? ' is-on' : ''}`}
          onClick={toggleCrossfade}
          aria-pressed={crossfadeEnabled}
          title="Hoà âm chuyển bài (crossfade) — làm mượt lúc sang bài mới"
        ><span aria-hidden="true">⇄</span> Hoà âm <span className="pill-state">{crossfadeEnabled ? 'BẬT' : 'TẮT'}</span></button>
        <button
          className="pbtn-pill"
          onClick={() => playSimilar(current)}
          title="Phát các bài tương tự — bay lượn trong vũ trụ"
        ><span aria-hidden="true">✦</span> Tương tự</button>
        <span className="vol-ico" aria-hidden="true">🔊</span>
        <input
          className="vol"
          type="range" min={0} max={1} step={0.01} value={volume}
          onChange={(e) => setVolume(parseFloat(e.target.value))}
          aria-label="Âm lượng"
        />
      </div>
    </div>
  );
}
