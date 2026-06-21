import { Radio, Play, SkipBack, SkipForward, Search } from 'lucide-react';
import { BODIES } from '../three/solar/bodies';
import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';
import { useFocusTrap } from './hooks/useFocusTrap';

// Usage guide — teaches *how to use* the app (planets are the picker, 1 vs 2 planets,
// the radio button, controls). Deliberately no emotion/algorithm reasoning. Always
// reachable from the "?" button; auto-opens once on first visit. A11y/focus handling
// mirrors SearchOverlay: role=dialog + aria-modal, Esc to close, focus restored on close.
export default function GuideOverlay() {
  const guideOpen = useStore((s) => s.guideOpen);
  const closeGuide = useStore((s) => s.closeGuide);

  // Trap Tab + restore focus on close (WCAG 2.1.2 / 2.4.3); initial focus → the card itself.
  const dialogRef = useFocusTrap<HTMLDivElement>(guideOpen);

  if (!guideOpen) return null;

  return (
    <div className="guide-backdrop" onClick={closeGuide} role="presentation">
      <div
        className="guide-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        tabIndex={-1}
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') closeGuide(); }}
      >
        <div className="guide-head">
          <h2 id="guide-title" className="guide-title">Cách dùng Brightify</h2>
          <button className="guide-close" onClick={closeGuide} aria-label="Đóng hướng dẫn">✕</button>
        </div>

        <div className="guide-body">
          <section className="guide-step">
            <h3 className="guide-step-title"><span aria-hidden="true">🪐</span> Mỗi hành tinh là một cảm xúc</h3>
            <p className="guide-step-text">
              12 hành tinh, mỗi cái mang một màu = một cảm xúc. <strong>Chạm một hành tinh</strong> để
              nghe những bài hát hợp tâm trạng đó.
            </p>
            <ul className="guide-legend" aria-label="Bảng hành tinh và cảm xúc">
              {BODIES.map((b) => {
                const c = EMOTION_COLORS.find((x) => x.hex === b.hex);
                return (
                  <li className="guide-legend-item" key={b.hex}>
                    <span className="guide-swatch" style={{ background: b.hex }} aria-hidden="true" />
                    <span className="guide-legend-text">
                      <span className="guide-legend-name">{b.name}</span>
                      <span className="guide-legend-emotion">{c?.emotion ?? ''}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title"><span aria-hidden="true">🚀</span> Chọn 2 hành tinh để du hành</h3>
            <p className="guide-step-text">
              Chọn thêm hành tinh thứ hai → một <strong>chuyến du hành</strong> chuyển dần từ cảm xúc này
              sang cảm xúc kia. Chỉnh nhanh hay chậm ở bảng <em>Du hành</em>.
            </p>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title"><Radio size={16} aria-hidden="true" /> Nút radio — nghe bài tương tự</h3>
            <p className="guide-step-text">
              Đang nghe một bài? Bấm nút radio <Radio className="guide-ico" size={15} aria-hidden="true" /> ở
              thanh phát để nối dài những bài cùng cảm xúc — phát mãi không hết.
            </p>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title"><span aria-hidden="true">🎧</span> Điều khiển &amp; tìm kiếm</h3>
            <p className="guide-step-text">
              Kéo để xoay · cuộn để phóng to. Thanh phát:{' '}
              <Play className="guide-ico" size={15} aria-hidden="true" /> phát/dừng,{' '}
              <SkipBack className="guide-ico" size={15} aria-hidden="true" />{' '}
              <SkipForward className="guide-ico" size={15} aria-hidden="true" /> chuyển bài, kéo thanh
              tiến độ để tua. Bấm <Search className="guide-ico" size={15} aria-hidden="true" /> hoặc phím{' '}
              <kbd>/</kbd> để tìm theo tên bài, nghệ sĩ, lời nhạc hoặc cảm xúc.
            </p>
          </section>
        </div>

        <div className="guide-footer">
          Mở lại hướng dẫn này bất cứ lúc nào ở nút <strong>?</strong> góc màn hình.
        </div>
      </div>
    </div>
  );
}
