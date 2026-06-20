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
  const searchQuery = useStore((s) => s.searchQuery);
  const searchResults = useStore((s) => s.searchResults);
  const searchLoading = useStore((s) => s.searchLoading);
  const semanticAvailable = useStore((s) => s.semanticAvailable);
  const { closeSearch, runSearch, playSong } = useStore.getState();

  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // Remember what had focus when we opened so we can hand it back on close (WCAG 2.4.3).
  const restoreFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (searchOpen) {
      restoreFocus.current = document.activeElement as HTMLElement | null;
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
      return () => restoreFocus.current?.focus();
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
    artist: 'Nghệ sĩ',
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
            role="combobox"
            aria-expanded={searchResults.length > 0}
            aria-controls="search-listbox"
            aria-autocomplete="list"
            aria-activedescendant={searchResults[active] ? `search-opt-${active}` : undefined}
            onChange={handleInput}
            autoComplete="off"
            spellCheck={false}
          />
          {searchLoading && <div className="search-spinner" aria-hidden="true" />}
        </div>

        {/* Empty / no-results states */}
        {!searchQuery.trim() && (
          <div className="search-empty">
            Tìm theo <strong>tên bài</strong>, <strong>nghệ sĩ</strong>,{' '}
            <strong>lời nhạc</strong> hoặc <strong>cảm xúc</strong> — có dấu hay không dấu đều được.
          </div>
        )}
        {searchQuery.trim() && !searchLoading && searchResults.length === 0 && (
          <div className="search-empty">Không tìm thấy bài nào cho “{searchQuery.trim()}”.</div>
        )}

        {/* Results */}
        <ul
          ref={listRef}
          id="search-listbox"
          className="search-results"
          role="listbox"
          aria-label="Kết quả tìm kiếm"
        >
          {searchResults.map((song, i) => (
            <li
              key={song.track_id}
              id={`search-opt-${i}`}
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
