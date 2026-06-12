import { useStore } from '../state/store';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';

// Shown during a two-planet journey: the A → B route (planet names) above the
// ordered, V-A-sequenced queue. ResultsList renders the mood gradient banner.
export default function JourneyHUD() {
  const sel = useStore((s) => s.selectedColors);
  const clearColors = useStore((s) => s.clearColors);

  const fromBody = bodyByHex(sel[0]);
  const toBody = bodyByHex(sel[1]);

  return (
    <div className="hud hud--journey" style={{ ['--c-from' as string]: sel[0], ['--c-to' as string]: sel[1] }}>
      <div className="hud-head">
        <span className="hud-eyebrow">Hành trình du hành 🚀</span>
        <h2 className="hud-title hud-title--grad">{fromBody?.name} → {toBody?.name}</h2>
      </div>
      <ResultsList />
      <button className="hud-back" onClick={clearColors}>← Về hệ mặt trời</button>
    </div>
  );
}
