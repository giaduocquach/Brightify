import { Palette, Library } from 'lucide-react';
import { useStore } from '../../state/store';

// Left rail: navigation only. Two destinations matching the app's two surfaces —
// "Nghe theo màu" (home: the mood picker) and "Thư viện" (the real catalogue).
// Switching tab clears any open recommendation/radio pane so the chosen view shows.
export default function ClassicSidebar() {
  const classicTab = useStore((s) => s.classicTab);
  const selectedColors = useStore((s) => s.selectedColors);
  const mode = useStore((s) => s.mode);
  const setClassicTab = useStore((s) => s.setClassicTab);
  const clearColors = useStore((s) => s.clearColors);

  // A pane (colour results / radio) is open whenever colours are selected or we're in fly mode;
  // it overrides the tab in ClassicMain, so highlight the tab only when no pane is covering it.
  const paneOpen = selectedColors.length > 0 || mode === 'fly';
  const go = (tab: 'home' | 'library') => { clearColors(); setClassicTab(tab); };

  return (
    <nav className="classic-sidebar" aria-label="Điều hướng">
      <ul className="classic-nav">
        <li>
          <button
            className={!paneOpen && classicTab === 'home' ? 'is-active' : ''}
            aria-current={!paneOpen && classicTab === 'home' ? 'page' : undefined}
            onClick={() => go('home')}
          >
            <Palette size={18} strokeWidth={2} aria-hidden="true" /> Nghe theo màu
          </button>
        </li>
        <li>
          <button
            className={!paneOpen && classicTab === 'library' ? 'is-active' : ''}
            aria-current={!paneOpen && classicTab === 'library' ? 'page' : undefined}
            onClick={() => go('library')}
          >
            <Library size={18} strokeWidth={2} aria-hidden="true" /> Thư viện
          </button>
        </li>
      </ul>
    </nav>
  );
}
