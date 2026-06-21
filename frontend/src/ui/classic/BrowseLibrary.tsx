import { useEffect, useState } from 'react';
import { api, type Song, type BrowseSort } from '../../api/client';
import { useStore } from '../../state/store';
import SongRow from '../SongRow';
import { vaToHex } from '../../three/va';

const PAGE_SIZE = 30;
const SORTS: { value: BrowseSort; label: string }[] = [
  { value: 'name', label: 'Tên A→Z' },
  { value: 'artist', label: 'Nghệ sĩ' },
  { value: 'energy', label: 'Sôi động nhất' },
  { value: 'valence', label: 'Tích cực nhất' },
  { value: 'danceability', label: 'Dễ nhảy nhất' },
  { value: 'random', label: 'Ngẫu nhiên' },
];

// Merge real audio availability (same pattern as store.recommend) so unplayable rows disable.
async function withAudio(songs: Song[]): Promise<Song[]> {
  const status = await api.batchAudioStatus(songs.map((s) => s.track_id).filter(Boolean));
  return songs.map((s) => ({ ...s, has_audio: !!status[s.track_id] || s.has_audio }));
}

function SongCard({ song, queue }: { song: Song; queue: Song[] }) {
  const playSong = useStore((s) => s.playSong);
  const isCurrent = useStore((s) => s.current?.track_id === song.track_id);
  const disabled = !song.has_audio;
  return (
    <button
      className={`song-card2${isCurrent ? ' is-active' : ''}`}
      onClick={() => !disabled && playSong(song, queue)}
      disabled={disabled}
      title={disabled ? 'Chưa có audio' : `Phát ${song.track_name}`}
    >
      <span className="song-card2-art" style={{ background: vaToHex(song.valence, song.arousal) }}>
        {song.album_art_url && <img src={song.album_art_url} alt="" loading="lazy" />}
      </span>
      <span className="song-card2-title">{song.track_name}</span>
      <span className="song-card2-artist">{song.artist}</span>
    </button>
  );
}

// The classic skin's home: a browsable library (Featured · New releases · All songs paginated),
// served by the existing /api/songs endpoints. This is new surface the 3D skin never exposed.
export default function BrowseLibrary() {
  const [featured, setFeatured] = useState<Song[]>([]);
  const [news, setNews] = useState<Song[]>([]);
  const [all, setAll] = useState<Song[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [sort, setSort] = useState<BrowseSort>('name');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Featured + new releases — load once.
  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getFeatured(12), api.getNewReleases(12)])
      .then(async ([f, n]) => {
        const [fa, na] = await Promise.all([withAudio(f), withAudio(n)]);
        if (!cancelled) { setFeatured(fa); setNews(na); }
      })
      .catch(() => { /* non-fatal — sections just stay empty */ });
    return () => { cancelled = true; };
  }, []);

  // Paginated all-songs — reload on page/sort change.
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    api.browseSongs({ page, limit: PAGE_SIZE, sort })
      .then(async (res) => {
        const songs = await withAudio(res.songs);
        if (!cancelled) { setAll(songs); setTotalPages(res.total_pages); setLoading(false); }
      })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : 'Lỗi tải thư viện'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [page, sort]);

  return (
    <div className="browse">
      <section id="lib-featured" className="browse-section">
        <h2 className="browse-h">Nổi bật</h2>
        {featured.length ? (
          <div className="card-strip">
            {featured.map((s, i) => <SongCard key={s.track_id || i} song={s} queue={featured} />)}
          </div>
        ) : <p className="browse-empty">Đang tải…</p>}
      </section>

      <section id="lib-new" className="browse-section">
        <h2 className="browse-h">Mới phát hành</h2>
        {news.length ? (
          <div className="card-strip">
            {news.map((s, i) => <SongCard key={s.track_id || i} song={s} queue={news} />)}
          </div>
        ) : <p className="browse-empty">Đang tải…</p>}
      </section>

      <section id="lib-all" className="browse-section">
        <div className="browse-all-head">
          <h2 className="browse-h">Tất cả bài hát</h2>
          <label className="browse-sort">
            Sắp xếp
            <select value={sort} onChange={(e) => { setSort(e.target.value as BrowseSort); setPage(1); }}>
              {SORTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
        {error ? (
          <p className="browse-empty">{error}</p>
        ) : loading ? (
          <div className="results-loading"><span className="spinner" /> Đang tải…</div>
        ) : (
          <>
            <div className="results-list">
              {all.map((s, i) => <SongRow key={s.track_id || i} song={s} index={i} queue={all} />)}
            </div>
            <div className="browse-pager">
              <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Trước</button>
              <span>Trang {page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Sau →</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
