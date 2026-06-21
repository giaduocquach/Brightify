import { Sparkles, Compass, Library } from 'lucide-react';
import { useStore } from '../../state/store';
import MoodPicker from './MoodPicker';

// Left rail: library navigation (scrolls to a section of BrowseLibrary, returning there first
// if a recommendation/radio pane is open) + the visible mood picker.
export default function ClassicSidebar() {
  const clearColors = useStore((s) => s.clearColors);

  // Return to the library (clears any recs/radio pane so BrowseLibrary is shown), then scroll
  // to the requested section once it has mounted.
  const goSection = (id: string) => {
    clearColors();
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  };

  return (
    <nav className="classic-sidebar" aria-label="Điều hướng thư viện">
      <ul className="classic-nav">
        <li>
          <button onClick={() => goSection('lib-featured')}>
            <Sparkles size={18} strokeWidth={2} aria-hidden="true" /> Nổi bật
          </button>
        </li>
        <li>
          <button onClick={() => goSection('lib-new')}>
            <Compass size={18} strokeWidth={2} aria-hidden="true" /> Mới phát hành
          </button>
        </li>
        <li>
          <button onClick={() => goSection('lib-all')}>
            <Library size={18} strokeWidth={2} aria-hidden="true" /> Tất cả bài hát
          </button>
        </li>
      </ul>
      <MoodPicker />
    </nav>
  );
}
