import { useEffect, useState } from 'react';
import { useStore } from '../state/store';

// First-run gesture coach. Teaches the one thing that isn't discoverable in a 3D scene —
// that planets are tappable and the camera drags/zooms — then gets out of the way: it
// auto-fades after a few seconds and is dismissed permanently on the first colour pick.
export default function OnboardingHint() {
  const mode = useStore((s) => s.mode);
  const onboardingDone = useStore((s) => s.onboardingDone);
  const [faded, setFaded] = useState(false);

  useEffect(() => {
    if (mode !== 'system' || onboardingDone) return;
    const id = setTimeout(() => setFaded(true), 9000);
    return () => clearTimeout(id);
  }, [mode, onboardingDone]);

  if (mode !== 'system' || onboardingDone || faded) return null;
  return (
    <div className="onboard-hint" role="note">
      <span className="onboard-row"><span aria-hidden="true">🪐</span> Chạm một hành tinh để nghe nhạc theo cảm xúc</span>
      <span className="onboard-row onboard-sub">Kéo để xoay · cuộn để phóng to · chọn 2 hành tinh để du hành</span>
    </div>
  );
}
