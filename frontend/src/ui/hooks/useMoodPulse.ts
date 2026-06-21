import { useEffect } from 'react';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from '../../three/solar/refs';

// Publishes a smoothed 0→1 `--beat` to the document root from the live audio energy, so the 2D
// chrome can breathe with the music (CSS uses it on already-glowing elements only — player glow,
// art halo). rAF + a CSS-var write → zero React re-render (same pattern as BeatStrip). Hard-gated:
// frozen at 0 when paused or under reduced-motion.
export function useMoodPulse() {
  const isPlaying = useStore((s) => s.isPlaying);
  useEffect(() => {
    const root = document.documentElement;
    if (!isPlaying) { root.style.setProperty('--beat', '0'); return; }
    let raf = 0;
    let level = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const target = solarRefs.reducedMotion ? 0 : Math.min(1, engine.features.rms * 2.2);
      level += (target - level) * 0.18; // smooth toward target (matches BeatStrip feel)
      root.style.setProperty('--beat', level.toFixed(3));
    };
    tick();
    return () => { cancelAnimationFrame(raf); root.style.setProperty('--beat', '0'); };
  }, [isPlaying]);
}
