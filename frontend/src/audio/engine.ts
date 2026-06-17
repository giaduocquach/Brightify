// Audio engine — two symmetric "decks" (like a DJ's two turntables). Both are permanently
// wired through their own gain + analyser into the destination; a crossfade is a gain
// blend plus an `active`/`inactive` POINTER SWAP. The currently-playing deck is never
// re-instantiated or seeked at transition time, so the outgoing track has no buffer gap —
// the one-beat hitch the old "copy the playing track onto a tail deck" model produced.
//
// Level is carried by each deck's GainNode, NOT by HTMLAudioElement `.volume` (kept at 1).
// Gain ramps run on the AudioContext clock via `setValueCurveAtTime`, which:
//   • completes even when the tab is backgrounded (the audio thread never pauses, unlike
//     requestAnimationFrame — the regression that left the next track silent), and
//   • anchors both fade halves to one clock instant for a synchronised, dip-free blend.
// Knows nothing about React.

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

// Per-track fade shaping passed down from the crossfade policy (`planCrossfade`).
export interface CrossfadeOpts {
  startAt?: number;                     // incoming entry cue (s) — seek the incoming deck here
  gainIn?: number;                      // fade-in target level (LUFS-matched)
  gainOut?: number;                     // fade-out start level
  curve?: 'linear' | 'equal-power';
  holdOutgoing?: boolean;               // late-vocal → don't ramp A down; it plays full to its natural end
  fadeInDur?: number;                   // incoming ramp length (defaults to durationSec)
  rateFactor?: number;                  // tempo nudge for the incoming deck (1.0 = none) — P3
  bassSwap?: boolean;                   // DJ low-shelf bass swap during the overlap — P4
}

// One playback deck: element + its slice of the WebAudio graph.
interface Deck {
  el: HTMLAudioElement;
  source: MediaElementAudioSourceNode | null;
  bass: BiquadFilterNode | null;        // low-shelf for DJ bass-swap during a crossfade (P4)
  gain: GainNode | null;
  analyser: AnalyserNode | null;
  freq: Uint8Array<ArrayBuffer> | null;
  time: Float32Array<ArrayBuffer> | null;
  loadedUrl: string;                    // last url assigned to this deck (preload idempotency)
}

// Number of samples in a gain curve — enough for a smooth ramp without a large per-fade alloc.
const FADE_CURVE_STEPS = 64;
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const BASS_CUT_DB = 10;       // DJ low-shelf cut on the outgoing track during the swap (P4)
const RATE_LIMIT = 0.06;      // max |playbackRate − 1| for the tempo nudge (P3) — beyond this = audible

class AudioEngine {
  features: AudioFeatures = { rms: 0, centroid: 0.5, bass: 0, treble: 0 };

  private deckA: Deck;
  private deckB: Deck;
  private active: Deck;     // the playing / analysed deck
  private inactive: Deck;   // the idle / incoming deck

  private ctx: AudioContext | null = null;
  private h: Handlers = {};
  private rmsEma = 0;
  private centroidEma = 0.5;
  private _volume = 0.85;
  private swapTimer: ReturnType<typeof setTimeout> | null = null;
  private rateTimer: ReturnType<typeof setInterval> | null = null;   // tempo-nudge stepper (P3)
  private rateSettle: ReturnType<typeof setTimeout> | null = null;   // schedules the settle-back to 1.0
  private xfadeEpoch = 0;   // bumped by a manual skip / newer crossfade → an in-flight fade bails
  private xfading = false;  // true from a crossfade's first await until its tail is finalised

  constructor() {
    this.deckA = this.makeDeck();
    this.deckB = this.makeDeck();
    this.active = this.deckA;
    this.inactive = this.deckB;
  }

  // Sole external reader is audio/arc.ts (`.src/.duration/.paused/.currentTime`); a getter
  // pointing at the active deck keeps that working across swaps.
  get el(): HTMLAudioElement { return this.active.el; }

  setHandlers(h: Handlers) { this.h = h; }

  // A deck with its six media listeners attached. Each listener fires the handler ONLY when
  // its deck is the active one, so the outgoing tail can't emit a spurious pause/ended
  // (auto-advance) while it fades out or when it's stopped after a swap.
  private makeDeck(): Deck {
    const el = new Audio();
    el.crossOrigin = 'anonymous';
    el.preload = 'auto';
    const deck: Deck = { el, source: null, bass: null, gain: null, analyser: null, freq: null, time: null, loadedUrl: '' };
    const whenActive = (fn: () => void) => () => { if (this.active === deck) fn(); };
    el.addEventListener('timeupdate', whenActive(() => this.h.onTime?.(el.currentTime, el.duration || 0)));
    el.addEventListener('durationchange', whenActive(() => this.h.onTime?.(el.currentTime, el.duration || 0)));
    el.addEventListener('play', whenActive(() => this.h.onPlay?.()));
    el.addEventListener('pause', whenActive(() => this.h.onPause?.()));
    el.addEventListener('ended', whenActive(() => this.h.onEnded?.()));
    el.addEventListener('error', whenActive(() => this.h.onError?.()));
    return deck;
  }

  // Build a deck's graph slice:  source → bass(low-shelf) → gain → analyser → destination. The
  // analyser stays AFTER the gain so engine.features (the 3D viz) is unaffected by the EQ swap.
  // `createMediaElementSource` is one-time per element, so this runs exactly once per deck.
  private wireDeck(deck: Deck, gainValue: number) {
    const ctx = this.ctx!;
    deck.gain = ctx.createGain();
    deck.gain.gain.value = gainValue;
    deck.bass = ctx.createBiquadFilter();
    deck.bass.type = 'lowshelf';
    deck.bass.frequency.value = 150;                     // shelf below ~150 Hz (kick/bass)
    deck.bass.gain.value = 0;                            // transparent until a bass-swap ramps it
    deck.analyser = ctx.createAnalyser();
    deck.analyser.fftSize = 512;
    deck.analyser.smoothingTimeConstant = 0.8;
    deck.source = ctx.createMediaElementSource(deck.el);
    deck.source.connect(deck.bass).connect(deck.gain).connect(deck.analyser).connect(ctx.destination);
    deck.el.volume = 1;                                  // level lives on the gain node
    deck.freq = new Uint8Array(deck.analyser.frequencyBinCount); // 256
    deck.time = new Float32Array(deck.analyser.fftSize);          // 512
  }

  private ensureGraph() {
    if (this.ctx) return;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    this.wireDeck(this.active, this._volume);
    this.wireDeck(this.inactive, 0);
    this.loop();
  }

  async load(url: string) {
    this.xfadeEpoch++;       // abort any in-flight crossfade coroutine (manual skip wins)
    this.xfading = false;
    this.cancelSwap();
    const a = this.active;
    a.el.src = url;
    a.el.load();
    a.loadedUrl = url;
    if (this.ctx && a.gain) {
      this.setGainNow(a.gain, this._volume);   // graph live → level on gain; cancels any ramp
      a.el.volume = 1;
    } else {
      a.el.volume = this._volume;              // pre-graph: element volume is the only control
    }
    this.stopInactive();                       // drop any half-faded tail from a prior crossfade
  }

  async play() {
    this.ensureGraph();
    if (this.ctx?.state === 'suspended') await this.ctx.resume();
    try { await this.active.el.play(); } catch { /* autoplay gesture race — ignored */ }
  }

  pause() { this.active.el.pause(); }
  toggle() { (this.active.el.paused ? this.play() : this.pause()); }

  // Live playhead read per-frame for smooth motion (store.time only updates ~4Hz on the
  // 'timeupdate' event, which makes anything driven by it judder).
  progress(): { time: number; duration: number } {
    return { time: this.active.el.currentTime || 0, duration: this.active.el.duration || 0 };
  }
  seek(t: number) { if (Number.isFinite(t)) this.active.el.currentTime = t; }

  setVolume(v: number) {
    this._volume = clamp01(v);
    const a = this.active;
    if (this.ctx && a.gain) {
      if (this.xfading) {
        // mid-blend: glide the incoming deck to the new level over a short ramp — a hard set
        // would cancel the fade-in curve and pop the track to full volume.
        const now = this.ctx.currentTime;
        a.gain.gain.cancelScheduledValues(now);
        a.gain.gain.setValueAtTime(a.gain.gain.value, now);
        a.gain.gain.linearRampToValueAtTime(this._volume, now + 0.15);
      } else {
        this.setGainNow(a.gain, this._volume);   // overrides an in-flight fade
      }
      a.el.volume = 1;
    } else {
      a.el.volume = this._volume;
    }
  }

  // True while a crossfade is in flight (first await → tail finalised). The store uses this
  // to avoid arming a second blend / preload over a live transition.
  isCrossfading(): boolean { return this.xfading; }

  // Buffer the NEXT track on the inactive deck ahead of the cut (optionally seeking to its
  // entry cue) so the fade-in lands on already-buffered audio — no stall at the transition.
  // Idempotent: re-preloading the same url is a no-op.
  preload(url: string, startAt = 0) {
    if (!url) return;
    const d = this.inactive;
    if (d.loadedUrl === url) return;
    d.el.src = url;
    d.el.load();
    d.loadedUrl = url;
    if (this.ctx) d.el.volume = 1;
    if (startAt > 0) void this.seekWhenReady(d.el, startAt);
  }

  // Crossfade into `url` on the inactive deck while the active deck fades out — then swap.
  // The active (outgoing) deck is never touched beyond its gain ramp, so it never re-buffers.
  async crossfadeTo(url: string, durationSec: number, tailRemainingSec?: number, opts?: CrossfadeOpts) {
    if (!this.ctx) { await this.load(url); return this.play(); }
    let dur = Math.max(0.5, durationSec);
    if (tailRemainingSec && tailRemainingSec > 0.5) dur = Math.min(dur, tailRemainingSec);

    this.cancelSwap();
    const epoch = ++this.xfadeEpoch;   // a manual skip / newer crossfade bumps this → we bail
    this.xfading = true;
    const incoming = this.inactive;
    const outgoing = this.active;
    const gainIn = clamp01(opts?.gainIn ?? this._volume);
    const curve = opts?.curve ?? 'equal-power';
    const startAt = opts?.startAt ?? 0;
    const hold = !!opts?.holdOutgoing;                       // ring/cut: leave A at full
    const fadeInDur = Math.max(0.05, opts?.fadeInDur ?? dur);

    // ready the incoming deck (skip the load if it was preloaded), silent until the ramp.
    // Re-check the epoch after every await: if we were superseded mid-await, abort before
    // touching the deck pointers so we never swap against a stale incoming/outgoing.
    const needLoad = incoming.loadedUrl !== url;
    if (needLoad) { incoming.el.src = url; incoming.el.load(); incoming.loadedUrl = url; }
    incoming.el.volume = 1;
    if (incoming.gain) this.setGainNow(incoming.gain, 0);
    if (startAt > 0) await this.seekWhenReady(incoming.el, startAt);   // DJ drop entry
    if (epoch !== this.xfadeEpoch) return;
    await this.waitCanPlay(incoming.el, 4000);                         // instant when preloaded
    if (epoch !== this.xfadeEpoch) return;
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    await incoming.el.play().catch(() => {});
    if (epoch !== this.xfadeEpoch) return;

    // swap NOW — the incoming track drives state/events from here, matching the store which
    // has already optimistically advanced index/current to it.
    this.active = incoming;
    this.inactive = outgoing;

    // both ramps anchored to one clock instant → synchronised, dip-free blend on the audio thread
    const t0 = this.ctx.currentTime;
    if (incoming.gain) this.ramp(incoming.gain.gain, 0, gainIn, t0, fadeInDur, 'in', curve);
    // late-vocal (hold): DON'T ramp A down — it plays at full to its natural end while B rises
    // underneath and carries past it. Otherwise fade A out over its instrumental tail.
    if (!hold && outgoing.gain) this.ramp(outgoing.gain.gain, outgoing.gain.gain.value, 0, t0, dur, 'out', curve);

    // P4 — DJ bass-swap: cut the outgoing low end as it leaves, bring the incoming low end up from
    // a cut, so two basslines never muddy each other. bass.gain is an AudioParam → reuse ramp().
    if (opts?.bassSwap && outgoing.bass && incoming.bass) {
      this.ramp(outgoing.bass.gain, 0, -BASS_CUT_DB, t0, Math.max(0.5, dur * 0.6), 'out', 'linear');
      this.ramp(incoming.bass.gain, -BASS_CUT_DB, 0, t0, Math.max(0.5, fadeInDur * 0.6), 'in', 'linear');
    }

    // P3 — tempo nudge: ease B toward A's tempo so beats lock during the mix, then settle B back to
    // its natural 1.0 over ~2s once the overlap is done (B is instrumental then → drift inaudible).
    const rf = opts?.rateFactor ?? 1;
    if (Math.abs(rf - 1) > 0.005) {
      this.easeRate(incoming, rf, Math.min(fadeInDur, 3), epoch);
      if (this.rateSettle) clearTimeout(this.rateSettle);
      this.rateSettle = setTimeout(() => {
        if (epoch === this.xfadeEpoch) this.easeRate(this.active, 1.0, 2.0, epoch);
      }, Math.max(0, fadeInDur * 1000));
    }

    // when holding, let A reach its real end (from the original tailRemaining) before pausing;
    // otherwise pause right after the fade-out completes.
    const finalizeMs = hold && tailRemainingSec && tailRemainingSec > 0
      ? Math.max(tailRemainingSec * 1000 + 120, dur * 1000 + 80)
      : dur * 1000 + 80;
    this.swapTimer = setTimeout(() => this.finalizeSwap(outgoing), finalizeMs);

    // a sub-second incoming track can finish during the play() await (before it was active,
    // so its 'ended' was guarded out) — surface it now or auto-advance would stall.
    if (this.active.el.ended) this.h.onEnded?.();
  }

  // Ease a deck's playbackRate from its current value to `to` over durSec (smoothstep). playbackRate
  // is NOT an AudioParam, so we step it on a timer; preservesPitch avoids the "chipmunk" shift.
  // Epoch-guarded so a manual skip / newer transition abandons it; the deck is reset to 1.0 by
  // cancelSwap on those paths.
  private easeRate(deck: Deck, to: number, durSec: number, epoch: number) {
    if (this.rateTimer) { clearInterval(this.rateTimer); this.rateTimer = null; }
    const el = deck.el as HTMLAudioElement & { preservesPitch?: boolean; webkitPreservesPitch?: boolean; mozPreservesPitch?: boolean };
    el.preservesPitch = true; el.webkitPreservesPitch = true; el.mozPreservesPitch = true;
    const from = el.playbackRate || 1;
    const target = Math.max(1 - RATE_LIMIT, Math.min(1 + RATE_LIMIT, to));
    const steps = Math.max(1, Math.round((durSec * 1000) / 50));
    let i = 0;
    this.rateTimer = setInterval(() => {
      if (epoch !== this.xfadeEpoch) { if (this.rateTimer) clearInterval(this.rateTimer); this.rateTimer = null; return; }
      i += 1;
      const p = Math.min(1, i / steps);
      const eased = 0.5 - 0.5 * Math.cos(p * Math.PI);   // smoothstep, no transient
      el.playbackRate = from + (target - from) * eased;
      if (p >= 1) { if (this.rateTimer) clearInterval(this.rateTimer); this.rateTimer = null; }
    }, 50);
  }

  // Stop + free the old deck after its fade-out. Its pause is guarded (old !== active) → silent.
  private finalizeSwap(old: Deck) {
    old.el.pause();
    old.el.src = '';
    old.loadedUrl = '';
    if (old.gain) this.setGainNow(old.gain, 0);
    if (old.bass && this.ctx) {                          // reset EQ so a reused deck starts flat
      old.bass.gain.cancelScheduledValues(this.ctx.currentTime);
      old.bass.gain.setValueAtTime(0, this.ctx.currentTime);
    }
    old.el.playbackRate = 1;
    this.swapTimer = null;
    this.xfading = false;
  }

  // Cancel any in-flight transition timers AND reset the tempo/EQ levers to neutral on both decks,
  // so a manual skip / new load never inherits a half-applied nudge or bass cut.
  private cancelSwap() {
    if (this.swapTimer) { clearTimeout(this.swapTimer); this.swapTimer = null; }
    if (this.rateTimer) { clearInterval(this.rateTimer); this.rateTimer = null; }
    if (this.rateSettle) { clearTimeout(this.rateSettle); this.rateSettle = null; }
    for (const d of [this.deckA, this.deckB]) {
      d.el.playbackRate = 1;
      if (d.bass && this.ctx) {
        d.bass.gain.cancelScheduledValues(this.ctx.currentTime);
        d.bass.gain.setValueAtTime(0, this.ctx.currentTime);
      }
    }
  }

  private stopInactive() {
    const d = this.inactive;
    if (!d.el.paused) d.el.pause();
    d.el.src = '';
    d.loadedUrl = '';
    if (d.gain) this.setGainNow(d.gain, 0);
  }

  // Resolve once the element can play through (or after a timeout, so a slow/blocked load
  // can't hang the crossfade forever).
  private waitCanPlay(el: HTMLAudioElement, timeoutMs: number): Promise<void> {
    return new Promise((resolve) => {
      if (el.readyState >= 3 /* HAVE_FUTURE_DATA */) return resolve();
      let done = false;
      let tid: ReturnType<typeof setTimeout>;
      const finish = () => {
        if (done) return;
        done = true;
        clearTimeout(tid);
        el.removeEventListener('canplay', finish);
        resolve();
      };
      el.addEventListener('canplay', finish, { once: true });
      tid = setTimeout(finish, timeoutMs);
    });
  }

  // Seek to `t` once metadata is known (so duration is valid), but only if the track is long
  // enough to leave a real tail after the cue. Resolves regardless so a crossfade can proceed.
  private seekWhenReady(el: HTMLAudioElement, t: number): Promise<void> {
    return new Promise((resolve) => {
      let tid: ReturnType<typeof setTimeout>;
      const onMeta = () => {
        clearTimeout(tid);
        if (el.duration && el.duration > t + 10) { try { el.currentTime = t; } catch { /* ignore */ } }
        resolve();
      };
      if (el.readyState >= 1 /* HAVE_METADATA */) return onMeta();
      el.addEventListener('loadedmetadata', onMeta, { once: true });
      tid = setTimeout(() => { el.removeEventListener('loadedmetadata', onMeta); resolve(); }, 3000);
    });
  }

  // Set a gain immediately, cancelling any scheduled ramp on that param so a manual volume
  // change / track load wins over an in-flight fade.
  private setGainNow(node: GainNode, value: number) {
    if (!this.ctx) { node.gain.value = value; return; }
    const now = this.ctx.currentTime;
    node.gain.cancelScheduledValues(now);
    node.gain.setValueAtTime(value, now);
  }

  // Schedule a gain ramp on the AudioContext clock.
  //   • equal-power: 'in' = sin(p·π/2), 'out' = cos(p·π/2) → sin²+cos²=1, constant summed power
  //     (a linear ramp dips ~3 dB through the middle — the audible "hole" in a crossfade);
  //   • linear: straight interpolation, used when the two tracks are highly correlated.
  private ramp(
    param: AudioParam, from: number, to: number,
    startTime: number, durSec: number, shape: 'in' | 'out', curve: 'linear' | 'equal-power',
  ) {
    const dur = Math.max(0.05, durSec);
    const arr = new Float32Array(FADE_CURVE_STEPS + 1);
    for (let i = 0; i <= FADE_CURVE_STEPS; i++) {
      const p = i / FADE_CURVE_STEPS;
      const e = curve === 'linear' ? p
        : shape === 'in' ? Math.sin(p * Math.PI / 2)
        : 1 - Math.cos(p * Math.PI / 2);
      arr[i] = clamp01(from + (to - from) * e);
    }
    try {
      param.cancelScheduledValues(startTime);
      param.setValueCurveAtTime(arr, startTime, dur);
    } catch {
      param.value = to; // overlapping-event edge cases — land on the target level
    }
  }

  private loop = () => {
    requestAnimationFrame(this.loop);
    const a = this.active;
    if (!a.analyser || !a.freq || !a.time) return;

    a.analyser.getFloatTimeDomainData(a.time);
    let sumSq = 0;
    for (let i = 0; i < a.time.length; i++) sumSq += a.time[i] * a.time[i];
    const rms = Math.sqrt(sumSq / a.time.length);

    a.analyser.getByteFrequencyData(a.freq);
    let num = 0, den = 0, bass = 0, treble = 0;
    const n = a.freq.length;
    for (let k = 0; k < n; k++) {
      const v = a.freq[k];
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
