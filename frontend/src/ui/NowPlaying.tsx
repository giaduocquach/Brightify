import { useEffect, useRef } from 'react';
import { useStore } from '../state/store';
import EmotionArc from './EmotionArc';
import { vaToHex } from '../three/va';

export default function NowPlaying() {
  const open = useStore((s) => s.nowPlayingOpen);
  const current = useStore((s) => s.current);
  const isPlaying = useStore((s) => s.isPlaying);
  const crossfadeEnabled = useStore((s) => s.crossfadeEnabled);
  const { close, togglePlay, next, prev, toggleCrossfade, playSimilar } = {
    close: useStore.getState().closeNowPlaying,
    togglePlay: useStore.getState().togglePlay,
    next: useStore.getState().next,
    prev: useStore.getState().prev,
    toggleCrossfade: useStore.getState().toggleCrossfade,
    playSimilar: useStore.getState().playSimilar,
  };

  const panel = useRef<HTMLDivElement>(null);
  const prevFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    prevFocus.current = document.activeElement as HTMLElement;
    panel.current?.querySelector<HTMLButtonElement>('.npo-close')?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close(); return; }
      if (e.key !== 'Tab' || !panel.current) return;
      const f = panel.current.querySelectorAll<HTMLElement>('button, [href], input');
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      prevFocus.current?.focus();
    };
  }, [open, close]);

  if (!open || !current) return null;

  return (
    <div className="npo" role="dialog" aria-modal="true" aria-label="Đang phát">
      <div className="npo-vignette" onClick={close} />
      <div className="npo-panel" ref={panel}>
        <div className="npo-art" style={{ background: vaToHex(current.valence, current.arousal) }}>
          {current.album_art_url && <img src={current.album_art_url} alt="" />}
        </div>
        <div className="npo-meta">
          <div className="npo-title">{current.track_name}</div>
          <div className="npo-artist">{current.artist}</div>
        </div>
        <EmotionArc variant="full" />
        <div className="npo-controls">
          <button onClick={prev} className="pbtn" aria-label="Bài trước">⏮</button>
          <button onClick={togglePlay} className="pbtn pbtn-play" aria-label={isPlaying ? 'Tạm dừng' : 'Phát'}>
            {isPlaying ? '⏸' : '▶'}
          </button>
          <button onClick={next} className="pbtn" aria-label="Bài tiếp">⏭</button>
        </div>
        <div className="npo-extra">
          <button
            className={`pbtn-pill${crossfadeEnabled ? ' is-on' : ''}`}
            onClick={toggleCrossfade}
            aria-pressed={crossfadeEnabled}
            title="Hoà âm chuyển bài (crossfade)"
          >⇄ Hoà âm <span className="pill-state">{crossfadeEnabled ? 'BẬT' : 'TẮT'}</span></button>
          <button className="pbtn-pill" onClick={() => playSimilar(current)}
            title="Phát các bài tương tự">✦ Tương tự</button>
        </div>
      </div>
      <button className="npo-close" onClick={close} aria-label="Đóng">×</button>
    </div>
  );
}
