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
  const { togglePlay, next, prev, seek, setVolume, openNowPlaying, toggleCrossfade, playSimilar } = useStore.getState();

  if (!current) return null;
  const pct = duration > 0 ? (time / duration) * 100 : 0;

  const onSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    seek(((e.clientX - r.left) / r.width) * duration);
  };

  return (
    <div className="player">
      <button className="player-track" onClick={openNowPlaying} title="Mở màn hình đang phát">
        <span className="player-art" style={{ background: vaToHex(current.valence, current.arousal) }}>
          {current.album_art_url && <img src={current.album_art_url} alt="" />}
        </span>
        <span className="player-meta">
          <span className="player-title">{current.track_name}</span>
          <span className="player-artist">{current.artist}</span>
        </span>
      </button>

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
          <div className="pbar" onClick={onSeek} role="slider" aria-label="Tiến độ"
               aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(time)}>
            <div className="pbar-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="ptime">{fmt(duration)}</span>
        </div>
      </div>

      <div className="player-right">
        <button
          className={`pbtn-pill${crossfadeEnabled ? ' is-on' : ''}`}
          onClick={toggleCrossfade}
          aria-pressed={crossfadeEnabled}
          title="Hoà âm chuyển bài (crossfade) — làm mượt lúc sang bài mới"
        >⇄ Hoà âm <span className="pill-state">{crossfadeEnabled ? 'BẬT' : 'TẮT'}</span></button>
        <button
          className="pbtn-pill"
          onClick={() => playSimilar(current)}
          title="Phát các bài tương tự — bay lượn trong vũ trụ"
        >✦ Tương tự</button>
        <span className="vol-ico" aria-hidden="true">🔊</span>
        <input
          className="vol"
          type="range" min={0} max={1} step={0.01} value={volume}
          onChange={(e) => setVolume(parseFloat(e.target.value))}
          aria-label="Âm lượng"
        />
        <button className="pbtn" onClick={openNowPlaying} aria-label="Phóng to" title="Phóng to">⤢</button>
      </div>
    </div>
  );
}
