// Accumulates the playing song's emotion trajectory: downsampled samples of
// {time, rms (energy), centroid (brightness)}. One sampler feeds every arc view.
import { engine } from './engine';

export interface ArcFrame { t: number; rms: number; centroid: number }

class ArcBuffer {
  frames: ArcFrame[] = [];
  duration = 0;
  private lastSrc = '';
  private lastT = -1;
  private raf = 0;

  start() {
    if (this.raf) return;
    this.loop();
  }

  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    const el = engine.el;
    if (el.src !== this.lastSrc) {
      this.lastSrc = el.src;
      this.frames = [];
      this.lastT = -1;
    }
    this.duration = el.duration || 0;
    if (el.paused || !el.duration) return;
    const t = el.currentTime;
    if (t - this.lastT >= 0.4 || t < this.lastT) {
      this.lastT = t;
      this.frames.push({ t, rms: engine.features.rms, centroid: engine.features.centroid });
      if (this.frames.length > 800) this.frames.shift();
    }
  };
}

export const arc = new ArcBuffer();
