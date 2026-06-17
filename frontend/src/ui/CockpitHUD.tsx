import { useStore } from '../state/store';

// "Now passing" readout shown while travelling (journey or free-flight). The third-
// person camera frames the ship; this names the track the ship is currently passing.
export default function CockpitHUD() {
  const current = useStore((s) => s.current);
  if (!current) return null;

  return (
    <div className="cockpit" aria-hidden="true">
      <div className="cockpit-ticker">
        <span className="cockpit-ticker-label">ĐANG BAY QUA</span>
        <span className="cockpit-ticker-song">{current.track_name} — {current.artist}</span>
      </div>
    </div>
  );
}
