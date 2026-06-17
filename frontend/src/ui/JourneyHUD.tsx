import { useStore, JOURNEY_LENGTHS } from '../state/store';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';
import BridgeChip from './BridgeChip';
import JourneyArc from './JourneyArc';
import WhyColorPanel from './WhyColorPanel';

// Pacing presets: more waypoints across the A→B arc = a longer, gentler journey
// (smaller mood shift per step). Maps 1:1 onto JOURNEY_LENGTHS in the store.
const PACING_LABELS: Record<number, string> = { 10: 'Nhanh', 20: 'Vừa', 36: 'Dài & chậm' };

// Shown during a two-planet journey: the A → B route (planet names) above the
// ordered, V-A-sequenced queue. ResultsList renders the mood gradient banner.
export default function JourneyHUD() {
  const sel = useStore((s) => s.selectedColors);
  const clearColors = useStore((s) => s.clearColors);
  const journeyLength = useStore((s) => s.journeyLength);
  const setJourneyLength = useStore((s) => s.setJourneyLength);
  const loading = useStore((s) => s.loading);
  const bridge = useStore((s) => s.bridge);
  const results = useStore((s) => s.results);
  const showPlaylist = useStore((s) => s.showPlaylist);

  const fromBody = bodyByHex(sel[0]);
  const toBody = bodyByHex(sel[1]);

  return (
    <div className="hud hud--journey" style={{ ['--c-from' as string]: sel[0], ['--c-to' as string]: sel[1] }}>
      <div className="hud-head">
        <span className="hud-eyebrow">Hành trình du hành <span aria-hidden="true">🚀</span></span>
        <h2 className="hud-title hud-title--grad">{fromBody?.name} → {toBody?.name}</h2>
        <BridgeChip bridge={bridge} />
        <JourneyArc />
        <WhyColorPanel bridge={bridge} songs={results} />
      </div>
      <div className="journey-pacing" role="group" aria-label="Độ dài hành trình">
        <span className="journey-pacing-label">Hành trình</span>
        {JOURNEY_LENGTHS.map((n) => (
          <button
            key={n}
            className={`pbtn-pill${journeyLength === n ? ' is-on' : ''}`}
            aria-pressed={journeyLength === n}
            disabled={loading}
            onClick={() => journeyLength !== n && setJourneyLength(n)}
            title={`${n} bài — ${PACING_LABELS[n]}`}
          >{PACING_LABELS[n]}</button>
        ))}
      </div>
      {showPlaylist && <ResultsList />}
      <button className="hud-back" onClick={clearColors}><span aria-hidden="true">←</span> Về hệ mặt trời</button>
    </div>
  );
}
