import { useEffect, useRef } from 'react';
import { arc } from '../audio/arc';
import { useStore } from '../state/store';

interface Props {
  variant?: 'mini' | 'full';
}

const RMS_SCALE = 3.2;

function hueFromCentroid(c: number) {
  return 220 + (35 - 220) * Math.max(0, Math.min(1, c * 2)); // cool → warm
}

// Draws the live emotion trajectory. X = time, Y = energy, colour = brightness.
export default function EmotionArc({ variant = 'mini' }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const current = useStore((s) => s.current);
  const nowPlayingOpen = useStore((s) => s.nowPlayingOpen);

  useEffect(() => {
    const cv = canvas.current, box = wrap.current;
    if (!cv || !box) return;
    const ctx = cv.getContext('2d')!;
    let raf = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = box.clientWidth * dpr;
      cv.height = box.clientHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);

    const draw = () => {
      raf = requestAnimationFrame(draw);
      const W = box.clientWidth, H = box.clientHeight;
      ctx.clearRect(0, 0, W, H);
      const frames = arc.frames;
      const dur = arc.duration || 1;
      if (frames.length < 2) return;

      const padX = 6, padY = 6;
      const dw = W - padX * 2, dh = H - padY * 2;
      // mid guide
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padX, padY + dh * 0.5);
      ctx.lineTo(padX + dw, padY + dh * 0.5);
      ctx.stroke();

      for (let i = 1; i < frames.length; i++) {
        const p = frames[i - 1], c = frames[i];
        const x1 = padX + (p.t / dur) * dw;
        const x2 = padX + (c.t / dur) * dw;
        const y1 = padY + (1 - Math.min(1, p.rms * RMS_SCALE)) * dh;
        const y2 = padY + (1 - Math.min(1, c.rms * RMS_SCALE)) * dh;
        const alpha = 0.45 + (i / frames.length) * 0.55;
        ctx.strokeStyle = `hsla(${hueFromCentroid(c.centroid)}, 72%, 62%, ${alpha})`;
        ctx.lineWidth = variant === 'full' ? 3 : 2.2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      const last = frames[frames.length - 1];
      const px = padX + (last.t / dur) * dw;
      const py = padY + (1 - Math.min(1, last.rms * RMS_SCALE)) * dh;
      const hue = hueFromCentroid(last.centroid);
      ctx.fillStyle = `hsl(${hue}, 80%, 70%)`;
      ctx.beginPath();
      ctx.arc(px, py, variant === 'full' ? 5 : 4, 0, Math.PI * 2);
      ctx.fill();
    };
    draw();

    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [variant]);

  // mini arc hides while the full overlay is open (avoids two visible copies)
  const hiddenMini = variant === 'mini' && (nowPlayingOpen || !current);

  return (
    <div
      ref={wrap}
      className={`emotion-arc emotion-arc--${variant}${hiddenMini ? ' is-hidden' : ''}`}
    >
      <canvas ref={canvas} />
    </div>
  );
}
