import SolarSystem from '../three/solar/SolarSystem';
import Intro from './Intro';
import ExploreHUD from './ExploreHUD';
import JourneyHUD from './JourneyHUD';
import CockpitHUD from './CockpitHUD';
import NavPanel from './NavPanel';
import FlyHUD from './FlyHUD';
import PlayerBar from './PlayerBar';
import ModeBadge from './ModeBadge';
import OnboardingHint from './OnboardingHint';
import HelpButton from './HelpButton';
import MoodVeil from './MoodVeil';
import MoodWord from './MoodWord';
import { useStore } from '../state/store';

// The immersive 3D skin: the solar-system canvas + its mode-gated HUD chrome + the player bar.
// Lazy-loaded from App (React.lazy) so the classic skin never downloads the three.js /
// @react-three / postprocessing bundle. The shared chrome (search, guide, a11y colours, the
// skin toggle, the now-playing announcer) lives in App and wraps both skins.
export default function ImmersiveApp() {
  const mode = useStore((s) => s.mode);

  return (
    <>
      <SolarSystem />
      <MoodVeil />
      {mode !== 'intro' && <MoodWord />}
      {mode === 'intro' && <Intro />}
      {mode !== 'intro' && <NavPanel />}
      {mode !== 'intro' && <ModeBadge />}
      {mode !== 'intro' && <HelpButton />}
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
    </>
  );
}
