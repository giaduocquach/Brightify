import { useStore, JOURNEY_LENGTHS } from '../state/store';
import { bodyByHex } from '../three/solar/bodies';
import ResultsList from './ResultsList';
import LyricsPanel from './LyricsPanel';

// Pacing presets: more waypoints across the A→B arc = a longer, gentler journey
// (smaller mood shift per step). Maps 1:1 onto JOURNEY_LENGTHS in the store.
const PACING_LABELS: Record<number, string> = { 10: 'Nhanh', 20: 'Vừa', 36: 'Dài & chậm' };

// Shown during a two-planet journey: the A → B route (planet names) and a length
// control above a plain V-A-sequenced playlist (or the lyrics view).
export default function JourneyHUD() {
  const sel = useStore((s) => s.selectedColors);
  const clearColors = useStore((s) => s.clearColors);
  const journeyLength = useStore((s) => s.journeyLength);
  const setJourneyLength = useStore((s) => s.setJourneyLength);
  const loading = useStore((s) => s.loading);
  const showPlaylist = useStore((s) => s.showPlaylist);
  const showLyrics = useStore((s) => s.showLyrics);

  const fromBody = bodyByHex(sel[0]);
  const toBody = bodyByHex(sel[1]);

  return (
    <div className="hud hud--journey" style={{ ['--c-from' as string]: sel[0], ['--c-to' as string]: sel[1] }}>
      <div className="hud-head">
        <span className="hud-eyebrow">Hành trình du hành</span>
        <h2 className="hud-title hud-title--grad">{fromBody?.name} → {toBody?.name}</h2>
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
      {showLyrics ? <LyricsPanel /> : showPlaylist && <ResultsList />}
      <button className="hud-back" onClick={clearColors}><span aria-hidden="true">←</span> Về hệ mặt trời</button>
    </div>
  );
}
