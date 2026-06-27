import { Radio, Play, SkipBack, SkipForward, Search } from 'lucide-react';
import { BODIES } from '../three/solar/bodies';
import { EMOTION_COLORS } from '../data/colors';
import { useStore } from '../state/store';
import { useFocusTrap } from './hooks/useFocusTrap';

// Usage guide — teaches *how to use* the app. Skin-aware: the classic skin frames the picker as
// colour swatches (bấm ô màu / chọn 2 màu / dùng tìm kiếm); the immersive skin frames it as planets
// (chạm hành tinh / kéo xoay-zoom). Deliberately no algorithm reasoning beyond the colour legend.
// Always reachable from the "?" button; auto-opens once on first visit. A11y mirrors SearchOverlay:
// role=dialog + aria-modal, Esc to close, focus restored on close.
export default function GuideOverlay() {
  const guideOpen = useStore((s) => s.guideOpen);
  const closeGuide = useStore((s) => s.closeGuide);
  const isClassic = useStore((s) => s.uiSkin === 'classic');

  // Trap Tab + restore focus on close (WCAG 2.1.2 / 2.4.3); initial focus → the card itself.
  const dialogRef = useFocusTrap<HTMLDivElement>(guideOpen);

  if (!guideOpen) return null;

  // Legend rows: colours (classic — same order as the picker) or planets (immersive). Both pair a
  // swatch with the colour's mood text from EMOTION_COLORS.
  const legend = isClassic
    ? EMOTION_COLORS.map((c) => ({ hex: c.hex, name: c.label, emotion: c.emotion }))
    : BODIES.map((b) => ({
        hex: b.hex,
        name: b.name,
        emotion: EMOTION_COLORS.find((x) => x.hex === b.hex)?.emotion ?? '',
      }));

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
            <h3 className="guide-step-title">
              <span aria-hidden="true">{isClassic ? '🎨' : '🪐'}</span>{' '}
              {isClassic ? 'Mỗi màu là một cảm xúc' : 'Mỗi hành tinh là một cảm xúc'}
            </h3>
            <p className="guide-step-text">
              {isClassic ? (
                <>12 màu, mỗi màu thể hiện một cảm xúc. <strong>Bấm một ô màu</strong> để nghe những
                bài hát hợp tâm trạng đó.</>
              ) : (
                <>12 hành tinh, mỗi cái mang một màu = một cảm xúc. <strong>Chạm một hành tinh</strong> để
                nghe những bài hát hợp tâm trạng đó.</>
              )}
            </p>
            <ul className="guide-legend" aria-label={isClassic ? 'Bảng màu và cảm xúc' : 'Bảng hành tinh và cảm xúc'}>
              {legend.map((item) => (
                <li className="guide-legend-item" key={item.hex}>
                  <span className="guide-swatch" style={{ background: item.hex }} aria-hidden="true" />
                  <span className="guide-legend-text">
                    <span className="guide-legend-name">{item.name}</span>
                    <span className="guide-legend-emotion">{item.emotion}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title">
              <span aria-hidden="true">{isClassic ? '🧭' : '🚀'}</span>{' '}
              {isClassic ? 'Chọn 2 màu để tạo hành trình' : 'Chọn 2 hành tinh để du hành'}
            </h3>
            <p className="guide-step-text">
              {isClassic ? (
                <>Bấm thêm màu thứ hai → một <strong>hành trình cảm xúc</strong> chuyển dần từ tâm trạng
                này sang tâm trạng kia (A → B).</>
              ) : (
                <>Chọn thêm hành tinh thứ hai → một <strong>chuyến du hành</strong> chuyển dần từ cảm xúc này
                sang cảm xúc kia. Chỉnh nhanh hay chậm ở bảng <em>Du hành</em>.</>
              )}
            </p>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title"><Radio size={16} aria-hidden="true" /> Nghe bài tương tự</h3>
            <p className="guide-step-text">
              {isClassic ? (
                <>Thích một bài? Bấm <strong>Tương tự</strong> ở bài đó trong <em>Thư viện</em> (hoặc nút
                radio <Radio className="guide-ico" size={15} aria-hidden="true" /> ở thanh phát) để nối dài
                những bài cùng cảm xúc — phát mãi không hết.</>
              ) : (
                <>Đang nghe một bài? Bấm nút radio <Radio className="guide-ico" size={15} aria-hidden="true" /> ở
                thanh phát để nối dài những bài cùng cảm xúc — phát mãi không hết.</>
              )}
            </p>
          </section>

          <section className="guide-step">
            <h3 className="guide-step-title"><span aria-hidden="true">🎧</span> Điều khiển &amp; tìm kiếm</h3>
            <p className="guide-step-text">
              {!isClassic && <>Kéo để xoay · cuộn để phóng to. </>}
              Thanh phát:{' '}
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
