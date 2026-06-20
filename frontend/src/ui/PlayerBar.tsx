import { useStore } from '../state/store';
import { vaToHex } from '../three/va';
import {
  SkipBack, SkipForward, Play, Pause,
  ScrollText, Blend, Radio, Volume2, Volume1, VolumeX, ListMusic, Search,
} from 'lucide-react';
import BeatStrip from './BeatStrip';

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
  const { togglePlay, next, prev, seek, setVolume, toggleCrossfade, playSimilar, togglePlaylist, toggleLyrics, openSearch } = useStore.getState();

  if (!current) return null;
  const pct = duration > 0 ? (time / duration) * 100 : 0;
  // Per-song mood colour drives the dynamic accents (art halo, seek fill, beat strip, toggles).
  const mood = vaToHex(current.valence, current.arousal);
  // Volume icon graduates with the actual level so it reads at a glance.
  const VolIcon = volume <= 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;

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
    <div className="player" style={{ ['--mood' as string]: mood }}>
      {playbackError && <div className="player-error" role="status" aria-live="polite">{playbackError}</div>}
      <div className="player-track">
        <span className="player-art" style={{ background: mood }}>
          {current.album_art_url && <img src={current.album_art_url} alt="" />}
        </span>
        <span className="player-meta">
          <span className="player-title">{current.track_name}</span>
          <span className="player-artist">{current.artist}</span>
        </span>
        <BeatStrip color={mood} playing={isPlaying} />
      </div>

      <div className="player-center">
        <div className="player-buttons">
          <button onClick={prev} aria-label="Bài trước" className="pbtn"><SkipBack size={18} strokeWidth={2} /></button>
          <button onClick={togglePlay} aria-label={isPlaying ? 'Tạm dừng' : 'Phát'} className="pbtn pbtn-play">
            {isPlaying ? <Pause size={20} strokeWidth={2.2} fill="currentColor" /> : <Play size={20} strokeWidth={2.2} fill="currentColor" />}
          </button>
          <button onClick={next} aria-label="Bài tiếp" className="pbtn"><SkipForward size={18} strokeWidth={2} /></button>
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

      {/* Three function groups, separated by dividers:
          listen-experience (crossfade · radio) · view (lyrics · queue) · utility (volume · search). */}
      <div className="player-right">
        <div className="player-group">
          <button
            className={`pbtn pbtn-toggle${crossfadeEnabled ? ' is-on' : ''}`}
            onClick={toggleCrossfade} aria-pressed={crossfadeEnabled}
            aria-label="Hoà âm chuyển bài (crossfade)" title="Hoà âm chuyển bài — làm mượt lúc sang bài mới"
          ><Blend size={18} strokeWidth={2} /></button>
          <button
            className="pbtn pbtn-toggle"
            onClick={() => playSimilar(current)}
            aria-label="Phát đài bài tương tự" title="Đài tương tự — nối dài những bài cùng cảm xúc"
          ><Radio size={18} strokeWidth={2} /></button>
        </div>

        <span className="player-divider" aria-hidden="true" />

        <div className="player-group">
          <button
            className={`pbtn pbtn-toggle${showLyrics ? ' is-on' : ''}`}
            onClick={toggleLyrics} aria-pressed={showLyrics}
            aria-label="Lời bài hát" title="Lời bài hát"
          ><ScrollText size={18} strokeWidth={2} /></button>
          <button
            className={`pbtn pbtn-toggle${showPlaylist ? ' is-on' : ''}`}
            onClick={togglePlaylist} aria-pressed={showPlaylist}
            aria-label="Ẩn/hiện danh sách phát" title="Danh sách phát"
          ><ListMusic size={18} strokeWidth={2} /></button>
        </div>

        <span className="player-divider" aria-hidden="true" />

        <div className="player-group">
          <div className="vol-wrap" title="Âm lượng">
            <span className="pbtn pbtn-toggle vol-ico" aria-hidden="true">
              <VolIcon size={18} strokeWidth={2} />
            </span>
            <input
              className="vol"
              type="range" min={0} max={1} step={0.01} value={volume}
              onChange={(e) => setVolume(parseFloat(e.target.value))}
              aria-label="Âm lượng"
            />
          </div>
          <button
            className="pbtn pbtn-toggle"
            onClick={openSearch}
            aria-label="Tìm kiếm bài hát"
            title="Tìm kiếm — / hoặc ⌘K"
          ><Search size={18} strokeWidth={2} /></button>
        </div>
      </div>
    </div>
  );
}
