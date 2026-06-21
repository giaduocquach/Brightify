import { useEffect, useRef } from 'react';
import { engine } from '../audio/engine';
import { solarRefs } from '../three/solar/refs';

// A tiny vertical EQ strip at the far left of the player bar. Driven directly by the live
// engine.features (bass / rms / treble) on a rAF loop that mutates the canvas — NO React state,
// so it never re-renders the player (same "no React state" philosophy as the 3D scene). Tinted
// by the now-playing mood colour; settles to a flat floor when paused.
const BARS = 5;
const W = 26;
const H = 40;

export default function BeatStrip({ color, playing }: { color: string; playing: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const colorRef = useRef(color);
  const playingRef = useRef(playing);
  colorRef.current = color;
  playingRef.current = playing;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    const levels = new Array(BARS).fill(0.04);
    const bw = 3;
    const gap = (W - BARS * bw) / (BARS - 1);
    let raf = 0;

    const draw = () => {
      raf = requestAnimationFrame(draw);
      const f = engine.features;
      // low bars track bass, mid bars track overall energy (rms), high bars track treble
      const targets = [
        f.bass,
        f.bass * 0.5 + f.rms * 2.4,
        f.rms * 2.8,
        f.treble * 0.6 + f.rms * 1.6,
        f.treble,
      ];
      ctx.clearRect(0, 0, W, H);
      // Reduced-motion: rest flat (no perpetual EQ animation); smoothing still settles it down.
      const flat = solarRefs.reducedMotion || !playingRef.current;
      for (let i = 0; i < BARS; i++) {
        const tgt = flat ? 0.04 : Math.min(1, Math.max(0.05, targets[i]));
        levels[i] += (tgt - levels[i]) * 0.35; // smoothing toward target
        const h = Math.max(2, levels[i] * H);
        ctx.globalAlpha = 0.5 + levels[i] * 0.5;
        ctx.fillStyle = colorRef.current || '#a78bfa';
        ctx.fillRect(i * (bw + gap), H - h, bw, h);
      }
      ctx.globalAlpha = 1;
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} className="player-beat" aria-hidden="true" />;
}
