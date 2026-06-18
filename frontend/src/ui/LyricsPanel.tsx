import { useEffect, useState } from 'react';
import { useStore } from '../state/store';
import { api } from '../api/client';

// Lyrics for the now-playing song. Fetched on demand from GET /api/song/{id} (which returns
// plain_lyrics / lyrics_cleaned). A light centred reading panel — the scene shows behind it.
export default function LyricsPanel() {
  const show = useStore((s) => s.showLyrics);
  const toggle = useStore((s) => s.toggleLyrics);
  const current = useStore((s) => s.current);
  const [lyrics, setLyrics] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const trackId = current?.track_id;
  useEffect(() => {
    if (!show || !trackId) return;
    let cancelled = false;
    setLoading(true);
    setLyrics(null);
    api.getSongLyrics(trackId)
      .then((l) => { if (!cancelled) { setLyrics(l); setLoading(false); } })
      .catch(() => { if (!cancelled) { setLyrics(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [show, trackId]);

  if (!show) return null;

  return (
    <div className="lyrics-panel" aria-label="Lời bài hát">
      <div className="lyrics-head">
        <span className="lyrics-meta">
          <span className="lyrics-title">{current?.track_name ?? 'Lời bài hát'}</span>
          {current && <span className="lyrics-artist">{current.artist}</span>}
        </span>
        <button className="lyrics-close" onClick={toggle} aria-label="Đóng lời bài hát"><span aria-hidden="true">✕</span></button>
      </div>
      <div className="lyrics-body">
        {!current ? (
          <p className="lyrics-empty">Chưa phát bài nào.</p>
        ) : loading ? (
          <div className="results-loading"><span className="spinner" /> Đang tải lời…</div>
        ) : lyrics ? (
          <pre className="lyrics-text">{lyrics}</pre>
        ) : (
          <p className="lyrics-empty">Chưa có lời cho bài này.</p>
        )}
      </div>
    </div>
  );
}
