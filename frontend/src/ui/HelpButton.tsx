import { HelpCircle } from 'lucide-react';
import { useStore } from '../state/store';

// Persistent "?" affordance — the always-available entry to the usage guide, so the app
// is re-learnable regardless of whether the first-run auto-open ever fired (no login →
// localStorage is best-effort). Hidden during the intro greeting.
export default function HelpButton() {
  const openGuide = useStore((s) => s.openGuide);
  return (
    <button className="help-btn" onClick={openGuide} aria-label="Hướng dẫn sử dụng" title="Hướng dẫn — phím ?">
      <HelpCircle size={18} strokeWidth={2.2} aria-hidden="true" />
    </button>
  );
}
