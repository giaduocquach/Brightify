import { useStore } from '../state/store';
import type { Song } from '../api/client';
import { vaToHex } from '../three/va';

// Module-scoped: only one drag is ever in flight, so the source index lives here.
let dragFrom = -1;

interface SongRowProps {
  song: Song;
  index: number;
  /** The list this row plays into when clicked (results for colour, the live queue for radio). */
  queue: Song[];
}

// One playlist row: number/now-playing, album art, title, artist. Drag to reorder.
// (Deliberately minimal — no emotion/BPM/mood badges or coloured dot, per design.)
export default function SongRow({ song, index, queue }: SongRowProps) {
  const isCurrent = useStore((s) => s.current?.track_id === song.track_id);
  const playSong = useStore((s) => s.playSong);
  const reorderPlaylist = useStore((s) => s.reorderPlaylist);
  const disabled = !song.has_audio;
  const moodHex = vaToHex(song.valence, song.arousal);

  return (
    <button
      className={`result-row${isCurrent ? ' is-playing' : ''}`}
      onClick={() => !disabled && playSong(song, queue)}
      disabled={disabled}
      title={disabled ? 'Chưa có audio' : `Phát ${song.track_name}`}
      draggable
      onDragStart={(e) => { dragFrom = index; e.dataTransfer.effectAllowed = 'move'; }}
      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
      onDrop={(e) => { e.preventDefault(); if (dragFrom >= 0 && dragFrom !== index) reorderPlaylist(dragFrom, index); dragFrom = -1; }}
      onDragEnd={() => { dragFrom = -1; }}
    >
      <span className="result-grip" aria-hidden="true">⠿</span>
      <span className="result-num">{isCurrent ? '♪' : index + 1}</span>
      <span className="result-art" style={{ background: moodHex }}>
        {song.album_art_url && <img src={song.album_art_url} alt="" loading="lazy" />}
      </span>
      <span className="result-meta">
        <span className="result-title">{song.track_name}</span>
        <span className="result-artist">{song.artist}</span>
      </span>
    </button>
  );
}
