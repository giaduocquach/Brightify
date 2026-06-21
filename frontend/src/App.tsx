import { lazy, Suspense, useEffect } from 'react';
import { useReducedMotion } from './three/useReducedMotion';
import { solarRefs } from './three/solar/refs';
import A11yColors from './ui/A11yColors';
import SearchOverlay from './ui/SearchOverlay';
import GuideOverlay from './ui/GuideOverlay';
import SkinToggle from './ui/SkinToggle';
import ClassicApp from './ui/classic/ClassicApp';
import { useIdleListening } from './ui/hooks/useIdleListening';
import { useMoodPulse } from './ui/hooks/useMoodPulse';
import { engine } from './audio/engine';
import { useStore } from './state/store';
import { vaToHex } from './three/va';

// The immersive 3D skin is lazy-loaded so a classic-first session (especially on mobile)
// never downloads the three.js / @react-three / postprocessing bundle. Vite code-splits this.
const ImmersiveApp = lazy(() => import('./ui/ImmersiveApp'));

export default function App() {
  const mode = useStore((s) => s.mode);
  const current = useStore((s) => s.current);
  const uiSkin = useStore((s) => s.uiSkin);
  const osReduce = useReducedMotion();

  useIdleListening();
  useMoodPulse();

  // Single mood→colour channel: publish the now-playing song's emotion colour to the document
  // root so the whole 2D field (player, mood veil, future chrome) tints coherently. Fires once
  // per song; cleared to the --accent fallback when nothing is playing.
  useEffect(() => {
    const root = document.documentElement;
    if (current) root.style.setProperty('--mood', vaToHex(current.valence, current.arousal));
    else root.style.removeProperty('--mood');
  }, [current]);

  // In first-person flight, let the canopy be the focus: side panels recede (and return
  // on hover) via a body flag the stylesheet keys off. (No-op visually in the classic skin.)
  useEffect(() => {
    document.body.dataset.flight = mode === 'journey' || mode === 'fly' ? '1' : '';
  }, [mode]);

  // Reflect the active skin on <body> so the stylesheet can scope skin-specific chrome.
  useEffect(() => {
    document.body.dataset.skin = uiSkin;
  }, [uiSkin]);

  // Reduced-motion (OS preference). Push to the mutable ref (read by useFrame with zero
  // re-render churn) and the store (for render-time props like drei <Stars speed>).
  useEffect(() => {
    solarRefs.reducedMotion = osReduce;
    useStore.getState()._setReducedMotion(osReduce);
  }, [osReduce]);

  // Global keyboard shortcut: "/" or Cmd/Ctrl+K opens the search overlay
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      const inInput = tag === 'INPUT' || tag === 'TEXTAREA';
      if ((e.key === '/' && !inInput) || ((e.metaKey || e.ctrlKey) && e.key === 'k')) {
        e.preventDefault();
        useStore.getState().openSearch();
      } else if (e.key === '?' && !inInput) {
        e.preventDefault();
        useStore.getState().openGuide();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    const store = useStore.getState();
    engine.setVolume(store.volume);
    engine.setHandlers({
      onTime: (t, d) => useStore.getState()._setTime(t, d),
      onPlay: () => useStore.getState()._setPlaying(true),
      onPause: () => useStore.getState()._setPlaying(false),
      onEnded: () => useStore.getState().next(),
      onError: () => useStore.getState()._onPlaybackError(),
    });
  }, []);

  return (
    <>
      <h1 className="sr-only">Brightify — không gian âm nhạc theo cảm xúc</h1>
      {/* Announce the track once per song change for screen readers (polite, low-frequency). */}
      <div className="sr-only" aria-live="polite">
        {current ? `Đang phát: ${current.track_name} — ${current.artist}` : ''}
      </div>
      {/* Shared across both skins: the SR/keyboard colour path, the skin switch, and the
          global overlays (so they survive a skin change without unmounting). */}
      <A11yColors />
      <SkinToggle />
      {uiSkin === 'immersive' ? (
        <Suspense fallback={<div className="skin-splash" aria-hidden="true"><span className="spinner" /></div>}>
          <ImmersiveApp />
        </Suspense>
      ) : (
        <ClassicApp />
      )}
      <SearchOverlay />
      <GuideOverlay />
    </>
  );
}
