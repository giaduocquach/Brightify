import { Palette, Radio, Search } from 'lucide-react';
import { useStore } from '../../state/store';
import MoodPicker from './MoodPicker';

// The classic skin's home: the two ways to listen, stated plainly so the system reads at a glance.
//   1) Nghe theo màu  → the large mood picker (recommend-by-colour, the headline feature).
//   2) Bài tương tự   → find a seed song (search), then any row / the player starts a similar radio.
export default function ClassicHome() {
  const openSearch = useStore((s) => s.openSearch);

  return (
    <div className="home">
      <header className="home-intro">
        <h1>Gợi ý nhạc Việt theo màu sắc &amp; cảm xúc</h1>
        <p>Hai cách khám phá: chọn màu thể hiện tâm trạng, hoặc nghe những bài tương tự một bài bạn thích.</p>
      </header>

      <section className="home-feature">
        <div className="home-feature-head">
          <Palette size={20} strokeWidth={2} aria-hidden="true" />
          <h2>1 · Nghe theo cảm xúc</h2>
        </div>
        <MoodPicker variant="hero" />
      </section>

      <section className="home-feature home-similar">
        <div className="home-feature-head">
          <Radio size={20} strokeWidth={2} aria-hidden="true" />
          <h2>2 · Bài tương tự</h2>
        </div>
        <p className="home-similar-text">
          Tìm một bài hát bạn thích — hệ thống sẽ gợi ý những bài cùng chất nhạc và cảm xúc, nối thành một đài nghe không dứt.
        </p>
        <button className="home-similar-btn" onClick={openSearch}>
          <Search size={16} strokeWidth={2} aria-hidden="true" /> Tìm bài hát
        </button>
      </section>
    </div>
  );
}
