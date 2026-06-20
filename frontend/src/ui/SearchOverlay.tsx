import { useEffect, useRef, useState, useCallback } from 'react';
import { Search } from 'lucide-react';
import { useStore } from '../state/store';

function useDebounce(fn: (q: string) => void, delay: number) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  return useCallback(
    (q: string) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => fn(q), delay);
    },
    [fn, delay],
  );
}

export default function SearchOverlay() {
  const searchOpen = useStore((s) => s.searchOpen);
  const searchResults = useStore((s) => s.searchResults);
  const searchLoading = useStore((s) => s.searchLoading);
  const semanticAvailable = useStore((s) => s.semanticAvailable);
  const { closeSearch, runSearch, playSong } = useStore.getState();

  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (searchOpen) {
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [searchOpen]);

  // Reset active index when results change
  useEffect(() => { setActive(0); }, [searchResults]);

  const debouncedSearch = useDebounce(runSearch, 220);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    debouncedSearch(e.target.value);
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = Math.min(active + 1, searchResults.length - 1);
      setActive(next);
      listRef.current?.children[next]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = Math.max(active - 1, 0);
      setActive(prev);
      listRef.current?.children[prev]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      const song = searchResults[active];
      if (song) { playSong(song, searchResults); closeSearch(); }
    } else if (e.key === 'Escape') {
      closeSearch();
    }
  };

  if (!searchOpen) return null;

  const BADGE_LABEL: Record<string, string> = {
    name: 'Tên bài',
    lyrics: 'Lời nhạc',
    vibe: 'Theo nghĩa',
  };

  return (
    <div className="search-backdrop" onClick={closeSearch} role="presentation">
      <div
        className="search-dialog"
        role="dialog"
        aria-label="Tìm kiếm bài hát"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKey}
      >
        {/* Input row */}
        <div className="search-input-row">
          <Search size={16} className="search-icon" aria-hidden="true" />
          <input
            ref={inputRef}
            className="search-input"
            type="search"
            placeholder="Tên bài, nghệ sĩ, lời nhạc hoặc cảm xúc…"
            aria-label="Từ khoá tìm kiếm"
            onChange={handleInput}
            autoComplete="off"
            spellCheck={false}
          />
          {searchLoading && <div className="search-spinner" aria-hidden="true" />}
        </div>

        {/* Results */}
        <ul
          ref={listRef}
          className="search-results"
          role="listbox"
          aria-label="Kết quả tìm kiếm"
        >
          {searchResults.map((song, i) => (
            <li
              key={song.track_id}
              className={`search-result-item${i === active ? ' is-active' : ''}`}
              role="option"
              aria-selected={i === active}
              onClick={() => { playSong(song, searchResults); closeSearch(); }}
              onMouseEnter={() => setActive(i)}
            >
              {song.album_art_url && (
                <img
                  className="search-result-art"
                  src={song.album_art_url}
                  alt=""
                  loading="lazy"
                />
              )}
              <div className="search-result-meta">
                <div className="search-result-title">{song.track_name}</div>
                <div className="search-result-artist">{song.artist}</div>
                {song.lyric_snippet && (
                  <div className="search-result-snippet">"{song.lyric_snippet}"</div>
                )}
              </div>
              <span className={`search-match-badge badge-${song.match_type}`}>
                {BADGE_LABEL[song.match_type] ?? song.match_type}
              </span>
            </li>
          ))}
        </ul>

        {/* Footer */}
        <div className="search-footer">
          <span>
            <span
              className={`search-status-dot ${semanticAvailable ? 'ready' : 'loading'}`}
              aria-hidden="true"
            />
            {semanticAvailable ? 'Tìm theo nghĩa bật' : 'Đang tải tìm theo nghĩa…'}
          </span>
          <span className="search-hint">↑↓ chọn · Enter phát · Esc đóng</span>
        </div>
      </div>
    </div>
  );
}
