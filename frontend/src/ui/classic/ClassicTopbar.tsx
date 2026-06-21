import { Search } from 'lucide-react';
import { useStore } from '../../state/store';
import HelpButton from '../HelpButton';

// Classic top bar: brand + a search affordance (opens the shared SearchOverlay) + help.
// The skin toggle is rendered globally by App (fixed top-right), so it isn't duplicated here.
export default function ClassicTopbar() {
  const openSearch = useStore((s) => s.openSearch);

  return (
    <header className="classic-topbar">
      <span className="classic-brand">Brightify</span>
      <button className="classic-search" onClick={openSearch} aria-label="Tìm kiếm bài hát · phím / hoặc ⌘K">
        <Search size={16} strokeWidth={2} aria-hidden="true" />
        <span className="classic-search-text">Tìm bài hát, nghệ sĩ…</span>
        <kbd className="classic-search-kbd" aria-hidden="true">/</kbd>
      </button>
      {/* HelpButton is position:fixed (top-right) — it floats out of the bar by design. */}
      <HelpButton />
    </header>
  );
}
