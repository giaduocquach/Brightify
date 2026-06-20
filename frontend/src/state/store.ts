import { create } from 'zustand';
import { api, type Song, type SearchResult, type ColorResult } from '../api/client';
import { engine } from '../audio/engine';
import { planCrossfade, type CrossfadeTrack } from '../audio/crossfade';
import { hexToVA } from '../three/va';

const MAX_COLORS = 2; // 1 = static mood, 2 = mood journey (Iso-Principle)
const XFADE_MAX_S = 20; // pre-gate: consider the transition within this window of A's end. Also caps
                        // how early we honour the vocal-end anchor on very long instrumental outros.
const PRELOAD_LEAD_S = 24; // buffer the next deck this far from the end — before the fade window
const XFADE_MIN_TAIL_S = 0.3; // never fire a transition with less than this much audio left
const EXTEND_LOOKAHEAD = 3; // top up the radio queue this many tracks before the end
const MAX_EXCLUDE = 120;    // cap the already-played list sent to the backend (URL/body bound)
const COLOR_TOP_K = 12;     // single-colour static-mood list size
// 2-colour journey pacing: top_k = number of waypoints across the A→B arc. More
// waypoints ⇒ longer AND gentler (smaller V-A shift per step, Saari 2016 ~10-15%/step:
// 10≈11%/step, 20≈5%, 36≈3%). Exposed as Nhanh / Vừa / Dài & chậm in JourneyHUD.
export const JOURNEY_LENGTHS = [10, 20, 36] as const;
const DEFAULT_JOURNEY_LENGTH = 20;

// Map a Song to the crossfade policy's track shape (missing fields → graceful fallback).
function toXf(s: Song): CrossfadeTrack {
  return {
    track_name: s.track_name,
    tempo: s.tempo,
    energy: s.energy,
    key: s.key,
    mode: s.mode,
    loudness_lufs: s.loudness_lufs ?? s.loudness, // prefer true LUFS over raw dB
    danceability: s.danceability,
    mood_quadrant: s.mood_quadrant,
    fade_out_cue_s: s.fade_out_cue_s,
    fade_in_cue_s: s.fade_in_cue_s,
    downbeat_times_json: s.downbeat_times_json,
    duration_s: s.duration_s ?? (s.duration_ms ? s.duration_ms / 1000 : undefined),
    vocal_start_s: s.vocal_start_s,
    vocal_end_s: s.vocal_end_s,
  };
}

// Which queue index we've already armed an auto-crossfade / preload for (fire once per track).
let xfadeArmed = -1;
let preloadArmed = -1;
// Pending boarding→journey transition timer, so rapid re-picks can cancel a stale one.
let boardingTimer: ReturnType<typeof setTimeout> | null = null;
// Bound auto-skip on playback failure so a run of dead streams can't ping-pong forever.
const MAX_AUDIO_ERRORS = 3;
let audioErrorCount = 0;

// First-run onboarding: persist so returning users skip the coach.
const ONBOARD_KEY = 'brightify.onboarded';
function readOnboarded(): boolean {
  try { return localStorage.getItem(ONBOARD_KEY) === '1'; } catch { return false; }
}

// Where the camera/Ui is: the astronaut greeting, the solar overview, exploring
// one planet, or the two-planet journey. Derived from selection but `intro` is an
// explicit gate the user dismisses by entering the system or picking a planet.
export type Mode = 'intro' | 'system' | 'explore' | 'boarding' | 'journey' | 'fly';

function modeForColors(n: number): Exclude<Mode, 'intro' | 'boarding'> {
  return n === 0 ? 'system' : n === 1 ? 'explore' : 'journey';
}

// What the current queue was built from, so it can extend itself endlessly (radio).
// `color` with 2 hexes is a journey — its extension lingers at the destination mood.
type QueueSeed =
  | { kind: 'color'; colors: string[] }
  | { kind: 'song'; songId: string };

interface State {
  // view
  mode: Mode;

  // selection + recommendations
  selectedColors: string[];
  results: Song[];
  journey: ColorResult['journey'];
  bridge: ColorResult['bridge'];   // colour → {emotion_vi, valence, arousal} (the thesis chain, shown in the HUD)
  flyTracks: Song[];          // similar-song nodes shown in free-flight mode
  journeyLength: number;      // 2-colour A→B waypoint count (pacing: longer = slower)
  loading: boolean;
  error: string | null;         // recommendation/fetch error (shown in the results panel)
  playbackError: string | null; // audio failed to play (shown transiently in the player)

  // playback
  queue: Song[];
  index: number;
  current: Song | null;
  isPlaying: boolean;
  time: number;
  duration: number;
  volume: number;
  crossfadeEnabled: boolean;

  // endless radio: the queue tops itself up from `seed` before it runs out, so a
  // session never loops the same ~12-14 songs (avoids repeat-exposure satiation).
  seed: QueueSeed | null;
  extending: boolean;      // a top-up fetch is in flight (guards against duplicate calls)
  seedExhausted: boolean;  // the seed's candidate pool is spent → fall back to looping

  // atmosphere
  targetV: number;
  targetA: number;
  hoverHex: string | null;

  // accessibility — effective OS prefers-reduced-motion; gates the 3D scene's gratuitous motion.
  reducedMotion: boolean;

  // onboarding + panel visibility (toggled from the player bar)
  onboardingDone: boolean;
  showPlaylist: boolean;
  showLyrics: boolean;

  // search overlay
  searchOpen: boolean;
  searchQuery: string;
  searchResults: SearchResult[];
  searchLoading: boolean;
  semanticAvailable: boolean;

  // actions — selection
  enterSystem: () => void;
  toggleColor: (hex: string) => void;
  clearColors: () => void;
  setJourneyLength: (n: number) => void;
  setHover: (hex: string | null) => void;
  markOnboarded: () => void;
  togglePlaylist: () => void;
  toggleLyrics: () => void;
  reorderPlaylist: (from: number, to: number) => void;
  openSearch: () => void;
  closeSearch: () => void;
  runSearch: (q: string) => Promise<void>;

  // actions — playback
  playSong: (song: Song, queue?: Song[]) => void;
  playSimilar: (song: Song) => void;
  extendQueue: () => Promise<void>;
  togglePlay: () => void;
  next: () => void;
  prev: () => void;
  seek: (t: number) => void;
  setVolume: (v: number) => void;
  toggleCrossfade: () => void;

  // internal (wired to engine events in App)
  _setTime: (t: number, d: number) => void;
  _setPlaying: (p: boolean) => void;
  _endBoarding: () => void;
  _setReducedMotion: (v: boolean) => void;
  _onPlaybackError: () => void;
}

export const useStore = create<State>((set, get) => ({
  mode: 'intro',

  selectedColors: [],
  results: [],
  journey: null,
  bridge: null,
  flyTracks: [],
  journeyLength: DEFAULT_JOURNEY_LENGTH,
  loading: false,
  error: null,
  playbackError: null,

  queue: [],
  index: -1,
  current: null,
  isPlaying: false,
  time: 0,
  duration: 0,
  volume: 0.85,
  crossfadeEnabled: true,

  seed: null,
  extending: false,
  seedExhausted: false,

  targetV: 0.5,
  targetA: 0.5,
  hoverHex: null,

  reducedMotion: false,

  onboardingDone: readOnboarded(),
  showPlaylist: true,
  showLyrics: false,

  searchOpen: false,
  searchQuery: '',
  searchResults: [],
  searchLoading: false,
  semanticAvailable: false,

  enterSystem: () => set({ mode: 'system' }),

  toggleColor: (hex) => {
    // Cancel any pending boarding→journey transition from a previous pick so a stale
    // timer can't land us in the wrong mode after the selection changed.
    if (boardingTimer) { clearTimeout(boardingTimer); boardingTimer = null; }
    const sel = get().selectedColors;
    const prevMode = get().mode;
    let next: string[];
    if (sel.includes(hex)) next = sel.filter((c) => c !== hex);
    else if (sel.length < MAX_COLORS) next = [...sel, hex];
    else next = [sel[1], hex]; // replace oldest, keep a 2-colour journey
    const va = hexToVA(hex);
    // Adding the 2nd colour from explore plays the boarding (tractor-beam) sequence first.
    const isBoarding = next.length === 2 && prevMode === 'explore';
    const newMode: Mode = isBoarding ? 'boarding' : modeForColors(next.length);
    // Picking a colour also leaves the intro greeting behind + completes onboarding.
    if (!get().onboardingDone) get().markOnboarded();
    set({ selectedColors: next, mode: newMode, targetV: va.v, targetA: va.a });
    if (next.length) void recommend(set, get, next);
    else set({ results: [], journey: null });
    // Boarding: auto-transition to journey after the tractor beam animation completes.
    if (isBoarding) {
      boardingTimer = setTimeout(() => {
        boardingTimer = null;
        if (useStore.getState().mode === 'boarding') useStore.getState()._endBoarding();
      }, 3200);
    }
  },

  // "Về hệ mặt trời": return to the overview but keep the music playing (it's a player).
  // Drop the radio seed + recommendation context so a stale fly/colour seed can't keep
  // topping up the queue behind a new selection. Playback (queue/index/current) is untouched.
  clearColors: () =>
    set({
      selectedColors: [], results: [], journey: null, bridge: null, flyTracks: [],
      seed: null, seedExhausted: false, mode: 'system',
    }),

  // Re-pace an active 2-colour journey: a different waypoint count rebuilds the A→B
  // arc with a new (longer/gentler or shorter) set of songs, so playback restarts at
  // the new first step. No-op for 0/1 colour (single-colour list is fixed at COLOR_TOP_K).
  setJourneyLength: (n) => {
    set({ journeyLength: n });
    const cols = get().selectedColors;
    if (cols.length === 2) void recommend(set, get, cols);
  },

  setHover: (hex) => set({ hoverHex: hex }),

  markOnboarded: () => {
    try { localStorage.setItem(ONBOARD_KEY, '1'); } catch { /* ignore */ }
    set({ onboardingDone: true });
  },
  // Playlist + lyrics share one panel slot (in the HUD) → mutually exclusive: opening one closes
  // the other; closing leaves the other untouched.
  togglePlaylist: () => set((s) => { const on = !s.showPlaylist; return { showPlaylist: on, showLyrics: on ? false : s.showLyrics }; }),
  toggleLyrics: () => set((s) => { const on = !s.showLyrics; return { showLyrics: on, showPlaylist: on ? false : s.showPlaylist }; }),

  openSearch: () => set({ searchOpen: true }),
  closeSearch: () => set({ searchOpen: false, searchQuery: '', searchResults: [] }),
  runSearch: async (q: string) => {
    if (!q.trim()) { set({ searchResults: [], searchLoading: false }); return; }
    set({ searchLoading: true, searchQuery: q });
    try {
      const { results, semanticAvailable } = await api.search(q);
      set({ searchResults: results, searchLoading: false, semanticAvailable });
    } catch {
      set({ searchLoading: false });
    }
  },

  // Drag-to-reorder the visible playlist. Colour list (results) defines play order → mirror
  // into the queue so playback follows the new order; fly list IS the queue. Keep `current`.
  reorderPlaylist: (from, to) => {
    const st = get();
    const inFly = st.mode === 'fly';
    const list = inFly ? st.queue : st.results;
    if (from < 0 || to < 0 || from >= list.length || to >= list.length || from === to) return;
    const arr = [...list];
    const [moved] = arr.splice(from, 1);
    arr.splice(to, 0, moved);
    const curId = st.current?.track_id;
    const idx = curId ? arr.findIndex((s) => s.track_id === curId) : st.index;
    xfadeArmed = -1; preloadArmed = -1; // index shifted → re-arm the look-ahead crossfade/preload
    if (inFly) set({ queue: arr, index: idx >= 0 ? idx : st.index });
    else set({ results: arr, queue: arr, index: idx });
  },

  playSong: (song, queue) => {
    const q = queue ?? get().results;
    const idx = Math.max(0, q.findIndex((s) => s.track_id === song.track_id));
    xfadeArmed = -1;   // fresh track → re-arm auto-crossfade
    preloadArmed = -1; // and re-arm the look-ahead preload
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
      // Natural continuation: keep the current song playing, but rewire the queue so it
      // flows into the similar list when this song ends — the seed song leads the queue.
      // (Previously results only went into flyTracks, so auto-advance kept the OLD queue.)
      const playable = tracks.filter((s) => s.has_audio && s.track_id !== song.track_id);
      xfadeArmed = -1;   // queue changed → re-arm look-ahead against the new next track
      preloadArmed = -1; // (also discards any preload buffered for the old queue)
      set({
        flyTracks: tracks,
        queue: [song, ...playable],
        index: 0,
        seed: { kind: 'song', songId: song.track_id },
        seedExhausted: false,
        mode: 'fly',
        selectedColors: [],
        journey: null,
        loading: false,
      });
      // No engine.load/play: `song` is the already-playing current track, now at index 0.
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : 'Lỗi' });
    }
  },

  // Endless radio: append fresh, non-repeating songs from the current seed before the
  // queue runs out, so long sessions never loop the same handful of tracks (the
  // inverted-U satiation curve: liking falls toward baseline with repeat exposure).
  extendQueue: async () => {
    const st = get();
    if (st.extending || st.seedExhausted || !st.seed) return;
    set({ extending: true });
    try {
      const queueIds = st.queue.map((s) => s.track_id).filter(Boolean);
      const exclude = queueIds.slice(-MAX_EXCLUDE); // cap what we send; URL/body bound
      let fresh: Song[];
      if (st.seed.kind === 'song') {
        fresh = await api.getSimilar(st.seed.songId, 14, exclude);
      } else {
        // 2-colour journey → linger at the destination mood (colour B) rather than
        // re-walking the A→B arc; 1 colour → more of the same static mood.
        const cols = st.seed.colors.length === 2 ? [st.seed.colors[1]] : st.seed.colors;
        const data = await api.recommendByColor(cols, 12, 0.15, 0.5, exclude);
        fresh = data.results;
      }
      const status = await api.batchAudioStatus(fresh.map((s) => s.track_id).filter(Boolean));
      const have = new Set(queueIds); // dedup against the WHOLE queue, not just the slice
      const add = fresh
        .map((s) => ({ ...s, has_audio: !!status[s.track_id] || s.has_audio }))
        .filter((s) => s.has_audio && s.track_id && !have.has(s.track_id));
      if (add.length) set({ queue: [...get().queue, ...add], extending: false });
      else set({ seedExhausted: true, extending: false }); // pool spent → allow looping
    } catch {
      set({ extending: false }); // transient failure → a later tick retries
    }
  },

  togglePlay: () => engine.toggle(),

  next: () => {
    const { queue, index, seed, seedExhausted } = get();
    if (!queue.length) return;
    // Top up the radio if we're near the end (extend was likely already triggered by
    // the look-ahead in _setTime; this covers manual skips toward the tail).
    if (seed && !seedExhausted && index >= queue.length - EXTEND_LOOKAHEAD) void get().extendQueue();
    // Advance to the next PLAYABLE track (wrapping once), so an unplayable row in the
    // colour list can't strand playback or trigger an error→skip ping-pong.
    const n = queue.length;
    for (let step = 1; step <= n; step++) {
      const j = (index + step) % n;
      if (queue[j]?.has_audio) { get().playSong(queue[j], queue); return; }
    }
    set({ playbackError: 'Không có bản phát nào trong danh sách.' }); // nothing playable
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

  _setTime: (t, d) => {
    const st = get();
    // Endless radio: top up the queue a few tracks before the end so playback flows on
    // without ever hard-looping the same list. Guards keep this idempotent per tick.
    if (st.seed && !st.seedExhausted && !st.extending
        && st.index >= 0 && st.index >= st.queue.length - EXTEND_LOOKAHEAD) {
      void get().extendQueue();
    }
    const canBlend = st.crossfadeEnabled && st.isPlaying && d > 0 && st.queue.length > 1;
    // No modulo wrap: blend only into a real next track. At the genuine end (pool spent)
    // there is nothing to preload/crossfade — onEnded → next() handles the loop fallback.
    const ni = canBlend && st.index + 1 < st.queue.length ? st.index + 1 : -1;
    const nxt = ni >= 0 ? st.queue[ni] : undefined;

    // Look-ahead preload: buffer the next deck (seeked to its entry cue) well before the fade
    // window so the blend lands on already-buffered audio — no stall at the cut. Once per index.
    if (canBlend && nxt && preloadArmed !== st.index && d - t <= PRELOAD_LEAD_S
        && !engine.isCrossfading()) {
      preloadArmed = st.index; // arm even when next has no audio, so we don't re-check every tick
      if (nxt.has_audio) {
        const plan = planCrossfade(toXf(st.queue[st.index]), toXf(nxt), st.volume);
        const startAt = Number.isFinite(plan.fadeInStartAt_s) ? plan.fadeInStartAt_s : 0;
        engine.preload(api.streamUrl(nxt.track_id), startAt);
      }
    }

    // Auto-transition into the next track: ONE adaptive overlap, anchored to where A's vocals end
    // (plan.fadeOutStartAt_s). EARLY vocal-end → fade over the instrumental tail; LATE (sings to the
    // end) → holdOutgoing keeps A to its natural end while B fades in underneath and carries past it.
    // Fire at the anchored cue (DJ riding the fader out); fall back to a duration countdown.
    if (canBlend && nxt?.has_audio && d - t <= XFADE_MAX_S && xfadeArmed !== st.index
        && !engine.isCrossfading()) {
      const plan = planCrossfade(toXf(st.queue[st.index]), toXf(nxt), st.volume);
      const remaining = d - t;
      const cue = plan.fadeOutStartAt_s;
      const cueUsable = Number.isFinite(cue) && cue > 1.0 && cue < d - XFADE_MIN_TAIL_S;
      const fire = remaining > XFADE_MIN_TAIL_S && (cueUsable ? t >= cue : remaining <= plan.duration_s);
      if (fire) {
        xfadeArmed = st.index;
        void engine.crossfadeTo(api.streamUrl(nxt.track_id), plan.duration_s, remaining, {
          startAt: Number.isFinite(plan.fadeInStartAt_s) ? plan.fadeInStartAt_s : 0,
          gainIn: plan.gainB,
          gainOut: plan.gainA,
          curve: plan.curve,
          holdOutgoing: plan.holdOutgoing,
          fadeInDur: plan.fadeInDur_s,
          rateFactor: plan.rateFactor,
          bassSwap: plan.bassSwap,
        });
        set({ index: ni, current: nxt, targetV: nxt.valence, targetA: nxt.arousal });
        return;
      }
    }
    set({ time: t, duration: d });
  },
  _setPlaying: (p) => {
    if (p) audioErrorCount = 0; // a track actually started → reset the failure run
    set(p ? { isPlaying: true, playbackError: null } : { isPlaying: false });
  },
  _endBoarding: () => set({ mode: 'journey' }),
  _setReducedMotion: (v) => set({ reducedMotion: v }),

  // Fail loud (CLAUDE.md Rule 12): a track failed to load/play. Surface a message and
  // auto-skip to the next playable track, but bound the run so dead streams can't loop.
  _onPlaybackError: () => {
    audioErrorCount += 1;
    set({ isPlaying: false, playbackError: 'Không phát được bài này — đang thử bài khác.' });
    const playable = get().queue.filter((s) => s.has_audio).length;
    if (audioErrorCount <= MAX_AUDIO_ERRORS && playable > 1) {
      get().next();
    } else {
      set({ playbackError: 'Không phát được — thử chọn màu hoặc bài khác.' });
    }
  },
}));

async function recommend(
  set: (p: Partial<State>) => void,
  get: () => State,
  colors: string[],
) {
  set({ loading: true, error: null });
  try {
    // 2 colours = mood journey: top_k = waypoint count (user-paced). 1 colour = fixed list.
    const topK = colors.length === 2 ? get().journeyLength : COLOR_TOP_K;
    const data = await api.recommendByColor(colors, topK);
    const status = await api.batchAudioStatus(
      data.results.map((s) => s.track_id).filter(Boolean),
    );
    const results = data.results.map((s) => ({ ...s, has_audio: !!status[s.track_id] || s.has_audio }));
    const playable = results.filter((s) => s.has_audio);
    // No playable track → say so (don't leave an empty/greyed panel with no explanation).
    const noneMsg = results.length
      ? (playable.length ? null : 'Chưa có bản phát cho màu này — thử màu khác.')
      : 'Không tìm thấy bài phù hợp — thử màu khác.';
    // Seed the endless radio with this colour/journey so the queue extends itself
    // (a 2-colour seed lingers at the destination mood once the A→B arc completes).
    set({ results, journey: data.journey, bridge: data.bridge, error: noneMsg, seed: { kind: 'color', colors }, seedExhausted: false, loading: false });
    // Selecting a planet is a user gesture, so autoplay is allowed: explore the
    // planet (or set off on the journey) by playing the first track right away.
    if (colors.join('|') === get().selectedColors.join('|') && playable.length) {
      get().playSong(playable[0], playable);
    }
  } catch (e) {
    set({ loading: false, error: e instanceof Error ? e.message : 'Lỗi' });
  }
}
