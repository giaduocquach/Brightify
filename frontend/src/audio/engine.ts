// Audio engine — the analysed primary deck (`el`) is a single HTMLAudioElement routed
// through a WebAudio analyser; it always plays the *current* track so the 3D scene +
// arc read its `features`. A second plain element (`elB`) is used only as the fading
// *tail* of the outgoing track during a crossfade, so the analyser graph stays intact
// and the incoming track is always the analysed one. Knows nothing about React.

export interface AudioFeatures {
  rms: number;       // arousal proxy
  centroid: number;  // spectral brightness ≈ valence proxy (0..1)
  bass: number;
  treble: number;
}

type Handlers = {
  onTime?: (t: number, d: number) => void;
  onPlay?: () => void;
  onPause?: () => void;
  onEnded?: () => void;
  onError?: () => void;
};

class AudioEngine {
  readonly el: HTMLAudioElement;       // analysed primary deck (current track)
  private elB: HTMLAudioElement;       // tail deck (outgoing track during a crossfade)
  features: AudioFeatures = { rms: 0, centroid: 0.5, bass: 0, treble: 0 };

  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private source: MediaElementAudioSourceNode | null = null;
  private freq: Uint8Array<ArrayBuffer> | null = null;
  private time: Float32Array<ArrayBuffer> | null = null;
  private h: Handlers = {};
  private rmsEma = 0;
  private centroidEma = 0.5;
  private _volume = 0.85;
  private fadeIdA = 0;
  private fadeIdB = 0;

  constructor() {
    this.el = new Audio();
    this.el.crossOrigin = 'anonymous';
    this.el.preload = 'auto';
    this.elB = new Audio();
    this.elB.crossOrigin = 'anonymous';
    this.elB.preload = 'auto';

    this.el.addEventListener('timeupdate', () =>
      this.h.onTime?.(this.el.currentTime, this.el.duration || 0),
    );
    this.el.addEventListener('durationchange', () =>
      this.h.onTime?.(this.el.currentTime, this.el.duration || 0),
    );
    this.el.addEventListener('play', () => this.h.onPlay?.());
    this.el.addEventListener('pause', () => this.h.onPause?.());
    this.el.addEventListener('ended', () => this.h.onEnded?.());
    this.el.addEventListener('error', () => this.h.onError?.());
  }

  setHandlers(h: Handlers) { this.h = h; }

  private ensureGraph() {
    if (this.ctx) return;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.analyser.smoothingTimeConstant = 0.8;
    this.source = this.ctx.createMediaElementSource(this.el);
    this.source.connect(this.analyser);
    this.analyser.connect(this.ctx.destination);
    this.freq = new Uint8Array(this.analyser.frequencyBinCount); // 256
    this.time = new Float32Array(this.analyser.fftSize);          // 512
    this.loop();
  }

  async load(url: string) {
    this.fadeIdA++;                  // cancel any in-flight primary fade
    this.el.src = url;
    this.el.load();
    this.el.volume = this._volume;
  }

  async play() {
    this.ensureGraph();
    if (this.ctx?.state === 'suspended') await this.ctx.resume();
    try { await this.el.play(); } catch { /* autoplay gesture race — ignored */ }
  }

  pause() { this.el.pause(); }
  toggle() { (this.el.paused ? this.play() : this.pause()); }

  // Live playhead read per-frame for smooth motion (store.time only updates ~4Hz on
  // the 'timeupdate' event, which makes anything driven by it judder).
  progress(): { time: number; duration: number } {
    return { time: this.el.currentTime || 0, duration: this.el.duration || 0 };
  }
  seek(t: number) { if (Number.isFinite(t)) this.el.currentTime = t; }
  setVolume(v: number) {
    this._volume = Math.max(0, Math.min(1, v));
    this.fadeIdA++;                  // a manual volume change overrides a fade
    this.el.volume = this._volume;
  }

  // Blend the current track out (on the tail deck) while the next track fades in on
  // the analysed primary deck. Falls back to a plain load+play before the graph exists.
  //   • equal-power curves (sin/cos) keep perceived loudness constant — a linear ramp
  //     dips ~3 dB through the middle, which is the audible "hole" in a crossfade;
  //   • the incoming track is preloaded (await canplay) before its fade-in starts, so
  //     a buffering stall can't punch a gap into the audible blend;
  //   • the fade is clamped to the audio actually left on the outgoing track, so its
  //     tail is never cut off part-way through the fade.
  async crossfadeTo(url: string, durationSec: number, tailRemainingSec?: number) {
    if (!this.ctx) { await this.load(url); return this.play(); }
    let dur = Math.max(0.5, durationSec);
    if (tailRemainingSec && tailRemainingSec > 0.5) dur = Math.min(dur, tailRemainingSec);

    // hand the currently-playing audio to the tail deck and fade it out (equal-power)
    try {
      const src = this.el.currentSrc || this.el.src;
      if (src) {
        this.elB.src = src;
        this.elB.currentTime = this.el.currentTime;
        this.elB.volume = this.el.volume;
        await this.elB.play().catch(() => {});
        this.fade(this.elB, false, this.elB.volume, 0, dur, 'out', () => this.elB.pause());
      }
    } catch { /* tail is best-effort */ }

    // bring the next track in on the analysed primary deck — but only once it can play
    // through, so the fade-in never lands on an un-buffered stall.
    this.fadeIdA++;
    this.el.src = url;
    this.el.load();
    this.el.volume = 0;
    await this.waitCanPlay(this.el, 4000);
    await this.play();
    this.fade(this.el, true, 0, this._volume, dur, 'in');
  }

  // Resolve once the element has enough buffered to start playing (or after a timeout,
  // so a slow/blocked load can't hang the crossfade forever).
  private waitCanPlay(el: HTMLAudioElement, timeoutMs: number): Promise<void> {
    return new Promise((resolve) => {
      if (el.readyState >= 3 /* HAVE_FUTURE_DATA */) return resolve();
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        el.removeEventListener('canplay', finish);
        resolve();
      };
      el.addEventListener('canplay', finish, { once: true });
      setTimeout(finish, timeoutMs);
    });
  }

  private fade(
    el: HTMLAudioElement, primary: boolean,
    from: number, to: number, durSec: number,
    curve: 'linear' | 'in' | 'out' = 'linear', onDone?: () => void,
  ) {
    const id = primary ? ++this.fadeIdA : ++this.fadeIdB;
    const start = performance.now();
    const ms = Math.max(1, durSec * 1000);
    const tick = () => {
      if ((primary ? this.fadeIdA : this.fadeIdB) !== id) return; // superseded
      const p = Math.min(1, (performance.now() - start) / ms);
      // equal-power easing keeps the summed loudness ~constant across the blend
      const e = curve === 'in' ? Math.sin(p * Math.PI / 2)
        : curve === 'out' ? 1 - Math.cos(p * Math.PI / 2)
        : p;
      el.volume = Math.max(0, Math.min(1, from + (to - from) * e));
      if (p < 1) requestAnimationFrame(tick); else onDone?.();
    };
    requestAnimationFrame(tick);
  }

  private loop = () => {
    requestAnimationFrame(this.loop);
    if (!this.analyser || !this.freq || !this.time) return;

    this.analyser.getFloatTimeDomainData(this.time);
    let sumSq = 0;
    for (let i = 0; i < this.time.length; i++) sumSq += this.time[i] * this.time[i];
    const rms = Math.sqrt(sumSq / this.time.length);

    this.analyser.getByteFrequencyData(this.freq);
    let num = 0, den = 0, bass = 0, treble = 0;
    const n = this.freq.length;
    for (let k = 0; k < n; k++) {
      const v = this.freq[k];
      num += k * v; den += v;
      if (k < 12) bass += v;
      if (k > n - 40) treble += v;
    }
    const centroid = den > 0 ? num / den / n : 0;
    this.rmsEma = 0.85 * this.rmsEma + 0.15 * rms;
    this.centroidEma = 0.9 * this.centroidEma + 0.1 * centroid;

    this.features.rms = this.rmsEma;
    this.features.centroid = this.centroidEma;
    this.features.bass = bass / (12 * 255);
    this.features.treble = treble / (40 * 255);
  };
}

export const engine = new AudioEngine();
