import { useEffect } from 'react';
import SolarSystem from './three/solar/SolarSystem';
import { useReducedMotion } from './three/useReducedMotion';
import { solarRefs } from './three/solar/refs';
import A11yColors from './ui/A11yColors';
import Intro from './ui/Intro';
import ExploreHUD from './ui/ExploreHUD';
import JourneyHUD from './ui/JourneyHUD';
import CockpitHUD from './ui/CockpitHUD';
import NavPanel from './ui/NavPanel';
import FlyHUD from './ui/FlyHUD';
import PlayerBar from './ui/PlayerBar';
import SearchOverlay from './ui/SearchOverlay';
import ModeBadge from './ui/ModeBadge';
import OnboardingHint from './ui/OnboardingHint';
import { engine } from './audio/engine';
import { useStore } from './state/store';

export default function App() {
  const mode = useStore((s) => s.mode);
  const osReduce = useReducedMotion();

  // In first-person flight, let the canopy be the focus: side panels recede (and return
  // on hover) via a body flag the stylesheet keys off.
  useEffect(() => {
    document.body.dataset.flight = mode === 'journey' || mode === 'fly' ? '1' : '';
  }, [mode]);

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
      <SolarSystem />
      <A11yColors />
      {mode === 'intro' && <Intro />}
      {mode !== 'intro' && <NavPanel />}
      {mode !== 'intro' && <ModeBadge />}
      <OnboardingHint />
      {mode === 'explore' && <ExploreHUD />}
      {mode === 'journey' && <JourneyHUD />}
      {mode === 'fly' && <FlyHUD />}
      {(mode === 'journey' || mode === 'fly') && <CockpitHUD />}
      {mode === 'boarding' && (
        <div className="cockpit" aria-hidden="true">
          <div className="cockpit-ticker">
            <span className="cockpit-ticker-label">CHUẨN BỊ DU HÀNH</span>
            <span className="cockpit-ticker-song">Đang lên phi thuyền…</span>
          </div>
        </div>
      )}
      <PlayerBar />
      <SearchOverlay />
    </>
  );
}
