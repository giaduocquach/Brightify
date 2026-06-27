import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api, type Song, type BrowseSort } from '../../api/client';
import SongRow from '../SongRow';

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

// The classic skin's catalogue: the real, paginated /api/songs list (no fabricated "featured" /
// "new releases"). Sortable + searchable; each row can start a similar-song radio.
export default function Library() {
  const [all, setAll] = useState<Song[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [sort, setSort] = useState<BrowseSort>('name');
  const [query, setQuery] = useState('');       // committed search term (drives the fetch)
  const [draft, setDraft] = useState('');        // input value before submit
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    api.browseSongs({ page, limit: PAGE_SIZE, sort, search: query || undefined })
      .then(async (res) => {
        const songs = await withAudio(res.songs);
        if (!cancelled) { setAll(songs); setTotalPages(res.total_pages); setLoading(false); }
      })
      .catch((e) => { if (!cancelled) { setError(e instanceof Error ? e.message : 'Lỗi tải thư viện'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [page, sort, query]);

  const submitSearch = (e: React.FormEvent) => { e.preventDefault(); setPage(1); setQuery(draft.trim()); };

  return (
    <div className="library">
      <div className="library-head">
        <h2 className="browse-h">Thư viện bài hát</h2>
        <div className="library-tools">
          <form className="library-search" onSubmit={submitSearch} role="search">
            <Search size={16} strokeWidth={2} aria-hidden="true" />
            <input
              type="search"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Lọc theo tên bài / nghệ sĩ…"
              aria-label="Tìm trong thư viện"
            />
          </form>
          <label className="browse-sort">
            Sắp xếp
            <select value={sort} onChange={(e) => { setSort(e.target.value as BrowseSort); setPage(1); }}>
              {SORTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <p className="browse-empty">{error}</p>
      ) : loading ? (
        <div className="results-loading"><span className="spinner" /> Đang tải…</div>
      ) : all.length === 0 ? (
        <p className="browse-empty">Không tìm thấy bài nào{query ? ` cho “${query}”` : ''}.</p>
      ) : (
        <>
          <div className="results-list">
            {all.map((s, i) => <SongRow key={s.track_id || i} song={s} index={i} queue={all} showSimilar />)}
          </div>
          <div className="browse-pager">
            <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Trước</button>
            <span>Trang {page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Sau →</button>
          </div>
        </>
      )}
    </div>
  );
}
