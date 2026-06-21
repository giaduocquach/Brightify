import { useEffect, useState } from 'react';
import { Radio } from 'lucide-react';
import { useStore } from '../state/store';

// Contextual, non-blocking coach. Teaches the things a 3D scene can't make discoverable,
// one tip per moment, then gets out of the way (auto-fades, never blocks input):
//   • system (first run only) — planets are tappable + camera drags/zooms
//   • explore — the non-obvious next steps: pick a 2nd planet to journey, or use the radio
// The "?" button + GuideOverlay carry the full guide; these are just timely nudges.
const FADE_MS = 9000;

export default function OnboardingHint() {
  const mode = useStore((s) => s.mode);
  const onboardingDone = useStore((s) => s.onboardingDone);

  // Per-session: each tip auto-fades and won't reappear once dismissed this session.
  const [systemFaded, setSystemFaded] = useState(false);
  const [exploreFaded, setExploreFaded] = useState(false);

  const showSystem = mode === 'system' && !onboardingDone && !systemFaded;
  const showExplore = mode === 'explore' && !exploreFaded;

  useEffect(() => {
    if (showSystem) {
      const id = setTimeout(() => setSystemFaded(true), FADE_MS);
      return () => clearTimeout(id);
    }
  }, [showSystem]);

  useEffect(() => {
    if (showExplore) {
      const id = setTimeout(() => setExploreFaded(true), FADE_MS);
      return () => clearTimeout(id);
    }
  }, [showExplore]);

  if (showSystem) {
    return (
      <div className="onboard-hint" role="note">
        <span className="onboard-row"><span aria-hidden="true">🪐</span> Chạm một hành tinh để nghe nhạc theo cảm xúc</span>
        <span className="onboard-row onboard-sub">Kéo để xoay · cuộn để phóng to · chọn 2 hành tinh để du hành</span>
      </div>
    );
  }

  if (showExplore) {
    return (
      <div className="onboard-hint" role="note">
        <span className="onboard-row"><span aria-hidden="true">🚀</span> Chọn hành tinh thứ 2 để du hành giữa 2 cảm xúc</span>
        <span className="onboard-row onboard-sub">…hoặc bấm <Radio className="guide-ico" size={14} aria-hidden="true" /> trên thanh phát để nghe những bài cùng cảm xúc</span>
      </div>
    );
  }

  return null;
}
