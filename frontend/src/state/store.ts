import { create } from 'zustand';
import { api, type Song, type ColorResult } from '../api/client';
import { engine } from '../audio/engine';
import { planCrossfade, type CrossfadeTrack } from '../audio/crossfade';
import { hexToVA } from '../three/va';

const MAX_COLORS = 2; // 1 = static mood, 2 = mood journey (Iso-Principle)
const XFADE_LEAD_S = 5; // begin blending this many seconds before a track ends

// Map a Song to the crossfade policy's track shape (missing fields → graceful fallback).
function toXf(s: Song): CrossfadeTrack {
  return {
    track_name: s.track_name,
    tempo: s.tempo,
    energy: s.energy,
    key: s.key,
    mode: s.mode,
    loudness_lufs: s.loudness,
    danceability: s.danceability,
    duration_s: s.duration_ms ? s.duration_ms / 1000 : undefined,
  };
}

// Which queue index we've already armed an auto-crossfade for (fire once per track).
let xfadeArmed = -1;

// Where the camera/Ui is: the astronaut greeting, the solar overview, exploring
// one planet, or the two-planet journey. Derived from selection but `intro` is an
// explicit gate the user dismisses by entering the system or picking a planet.
export type Mode = 'intro' | 'system' | 'explore' | 'journey' | 'fly';

function modeForColors(n: number): Exclude<Mode, 'intro'> {
  return n === 0 ? 'system' : n === 1 ? 'explore' : 'journey';
}

interface State {
  // view
  mode: Mode;

  // selection + recommendations
  selectedColors: string[];
  results: Song[];
  journey: ColorResult['journey'];
  flyTracks: Song[];          // similar-song nodes shown in free-flight mode
  loading: boolean;
  error: string | null;

  // playback
  queue: Song[];
  index: number;
  current: Song | null;
  isPlaying: boolean;
  time: number;
  duration: number;
  volume: number;
  crossfadeEnabled: boolean;

  // atmosphere
  targetV: number;
  targetA: number;
  hoverHex: string | null;

  // ui
  nowPlayingOpen: boolean;

  // actions — selection
  enterSystem: () => void;
  toggleColor: (hex: string) => void;
  clearColors: () => void;
  setHover: (hex: string | null) => void;

  // actions — playback
  playSong: (song: Song, queue?: Song[]) => void;
  playSimilar: (song: Song) => void;
  togglePlay: () => void;
  next: () => void;
  prev: () => void;
  seek: (t: number) => void;
  setVolume: (v: number) => void;
  toggleCrossfade: () => void;
  openNowPlaying: () => void;
  closeNowPlaying: () => void;

  // internal (wired to engine events in App)
  _setTime: (t: number, d: number) => void;
  _setPlaying: (p: boolean) => void;
}

export const useStore = create<State>((set, get) => ({
  mode: 'intro',

  selectedColors: [],
  results: [],
  journey: null,
  flyTracks: [],
  loading: false,
  error: null,

  queue: [],
  index: -1,
  current: null,
  isPlaying: false,
  time: 0,
  duration: 0,
  volume: 0.85,
  crossfadeEnabled: true,

  targetV: 0.5,
  targetA: 0.5,
  hoverHex: null,

  nowPlayingOpen: false,

  enterSystem: () => set({ mode: 'system' }),

  toggleColor: (hex) => {
    const sel = get().selectedColors;
    let next: string[];
    if (sel.includes(hex)) next = sel.filter((c) => c !== hex);
    else if (sel.length < MAX_COLORS) next = [...sel, hex];
    else next = [sel[1], hex]; // replace oldest, keep a 2-colour journey
    const va = hexToVA(hex);
    // Picking a colour also leaves the intro greeting behind.
    set({ selectedColors: next, mode: modeForColors(next.length), targetV: va.v, targetA: va.a });
    if (next.length) void recommend(set, get, next);
    else set({ results: [], journey: null });
  },

  clearColors: () => set({ selectedColors: [], results: [], journey: null, mode: 'system' }),

  setHover: (hex) => set({ hoverHex: hex }),

  playSong: (song, queue) => {
    const q = queue ?? get().results;
    const idx = Math.max(0, q.findIndex((s) => s.track_id === song.track_id));
    xfadeArmed = -1; // fresh track → re-arm auto-crossfade
    set({
      queue: q.length ? q : [song],
      index: q.length ? idx : 0,
      current: song,
      targetV: song.valence,
      targetA: song.arousal,
    });
    void engine.load(api.streamUrl(song.track_id));
    void engine.play();
  },

  playSimilar: async (song) => {
    set({ loading: true, error: null });
    try {
      const sims = await api.getSimilar(song.track_id, 14);
      const status = await api.batchAudioStatus(sims.map((s) => s.track_id).filter(Boolean));
      const tracks = sims.map((s) => ({ ...s, has_audio: !!status[s.track_id] || s.has_audio }));
      const playable = tracks.filter((s) => s.has_audio);
      // free-flight: a separate queue; the colour `results` are left intact.
      set({ flyTracks: tracks, mode: 'fly', selectedColors: [], journey: null, loading: false });
      if (playable.length) get().playSong(playable[0], playable);
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : 'Lỗi' });
    }
  },

  togglePlay: () => engine.toggle(),

  next: () => {
    const { queue, index } = get();
    if (!queue.length) return;
    const ni = (index + 1) % queue.length;
    get().playSong(queue[ni], queue);
  },

  prev: () => {
    const { queue, index, time } = get();
    if (!queue.length) return;
    if (time > 3) { engine.seek(0); return; }
    const pi = (index - 1 + queue.length) % queue.length;
    get().playSong(queue[pi], queue);
  },

  seek: (t) => { engine.seek(t); set({ time: t }); },

  setVolume: (v) => { engine.setVolume(v); set({ volume: v }); },

  toggleCrossfade: () => set({ crossfadeEnabled: !get().crossfadeEnabled }),

  openNowPlaying: () => set({ nowPlayingOpen: true }),
  closeNowPlaying: () => set({ nowPlayingOpen: false }),

  _setTime: (t, d) => {
    const st = get();
    // Auto-crossfade: a few seconds before the current track ends, blend into the
    // next queued track. Fires once per source index; the queue/order is unchanged.
    if (st.crossfadeEnabled && st.isPlaying && d > 0 && st.queue.length > 1
        && d - t <= XFADE_LEAD_S && xfadeArmed !== st.index) {
      xfadeArmed = st.index;
      const ni = (st.index + 1) % st.queue.length;
      const nxt = st.queue[ni];
      if (nxt?.has_audio) {
        const plan = planCrossfade(toXf(st.queue[st.index]), toXf(nxt), st.volume);
        void engine.crossfadeTo(api.streamUrl(nxt.track_id), plan.duration_s);
        set({ index: ni, current: nxt, targetV: nxt.valence, targetA: nxt.arousal });
        return;
      }
    }
    set({ time: t, duration: d });
  },
  _setPlaying: (p) => set({ isPlaying: p }),
}));

async function recommend(
  set: (p: Partial<State>) => void,
  get: () => State,
  colors: string[],
) {
  set({ loading: true, error: null });
  try {
    const data = await api.recommendByColor(colors, 12);
    const status = await api.batchAudioStatus(
      data.results.map((s) => s.track_id).filter(Boolean),
    );
    const results = data.results.map((s) => ({ ...s, has_audio: !!status[s.track_id] || s.has_audio }));
    set({ results, journey: data.journey, loading: false });
    // Selecting a planet is a user gesture, so autoplay is allowed: explore the
    // planet (or set off on the journey) by playing the first track right away.
    if (colors.join('|') === get().selectedColors.join('|')) {
      const playable = results.filter((s) => s.has_audio);
      if (playable.length) get().playSong(playable[0], playable);
    }
  } catch (e) {
    set({ loading: false, error: e instanceof Error ? e.message : 'Lỗi' });
  }
}
