import { useStore } from '../state/store';
import { bodyByHex } from '../three/solar/bodies';

// Persistent, low-key orientation badge — names the current mode so journey vs fly (which look
// identical in third-person) are never ambiguous, and the user always knows where they are.
const LABELS: Record<string, string> = {
  system: 'Hệ Mặt Trời',
  explore: 'Khám phá',
  boarding: 'Đang lên phi thuyền',
  journey: 'Du hành',
  fly: 'Radio tương tự',
};

export default function ModeBadge() {
  const mode = useStore((s) => s.mode);
  const sel0 = useStore((s) => s.selectedColors[0]);
  if (mode === 'intro') return null;
  const planet = mode === 'explore' && sel0 ? bodyByHex(sel0)?.name : null;
  return (
    <div className="mode-badge" aria-live="polite">
      <span className="mode-badge-dot" aria-hidden="true" />
      {LABELS[mode] ?? ''}{planet ? ` · ${planet}` : ''}
    </div>
  );
}
