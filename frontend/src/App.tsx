import { useEffect } from 'react';
import SolarSystem from './three/solar/SolarSystem';
import A11yColors from './ui/A11yColors';
import Intro from './ui/Intro';
import ExploreHUD from './ui/ExploreHUD';
import JourneyHUD from './ui/JourneyHUD';
import CockpitHUD from './ui/CockpitHUD';
import NavPanel from './ui/NavPanel';
import PlayerBar from './ui/PlayerBar';
import NowPlaying from './ui/NowPlaying';
import { engine } from './audio/engine';
import { arc } from './audio/arc';
import { useStore } from './state/store';

export default function App() {
  const mode = useStore((s) => s.mode);

  useEffect(() => {
    const store = useStore.getState();
    engine.setVolume(store.volume);
    engine.setHandlers({
      onTime: (t, d) => useStore.getState()._setTime(t, d),
      onPlay: () => useStore.getState()._setPlaying(true),
      onPause: () => useStore.getState()._setPlaying(false),
      onEnded: () => useStore.getState().next(),
      onError: () => useStore.getState()._setPlaying(false),
    });
    arc.start(); // still feeds the now-playing modal's arc (the play-bar mini line is removed)
  }, []);

  return (
    <>
      <SolarSystem />
      <A11yColors />
      {mode === 'intro' && <Intro />}
      {mode !== 'intro' && <NavPanel />}
      {mode === 'explore' && <ExploreHUD />}
      {mode === 'journey' && <JourneyHUD />}
      {(mode === 'journey' || mode === 'fly') && <CockpitHUD />}
      <PlayerBar />
      <NowPlaying />
    </>
  );
}
