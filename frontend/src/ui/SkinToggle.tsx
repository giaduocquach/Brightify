import { Orbit, ListMusic } from 'lucide-react';
import { useStore } from '../state/store';

// Top-right switch between the immersive 3D skin and the plain classic player.
// Visible in BOTH skins; the icon + label show the skin you'll switch TO.
export default function SkinToggle() {
  const uiSkin = useStore((s) => s.uiSkin);
  const setSkin = useStore((s) => s.setSkin);
  const toClassic = uiSkin === 'immersive';

  return (
    <button
      className="skin-toggle"
      onClick={() => setSkin(toClassic ? 'classic' : 'immersive')}
      aria-pressed={!toClassic}
      aria-label={toClassic ? 'Chuyển sang giao diện đơn giản' : 'Chuyển sang vũ trụ 3D'}
      title={toClassic ? 'Giao diện đơn giản' : 'Vũ trụ 3D'}
    >
      {toClassic
        ? <ListMusic size={16} strokeWidth={2} aria-hidden="true" />
        : <Orbit size={16} strokeWidth={2} aria-hidden="true" />}
      <span className="skin-toggle-label">{toClassic ? 'Đơn giản' : 'Vũ trụ 3D'}</span>
    </button>
  );
}
