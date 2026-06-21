import { useEffect } from 'react';
import { useStore } from '../../state/store';

// "Sink-in" focus: once the user is settled into a track (playing, no overlay open) and has been
// idle for a few seconds, the peripheral chrome (nav console, help, mode badge) recedes so the
// cosmos and the music take over — flow over controls. Any input brings it straight back. Mirrors
// the existing `data-flight` recede mechanism (App keys the stylesheet off a body data-flag).
// Gated on reduced-motion: motion-sensitive users keep the chrome steady.
const IDLE_MS = 6000;
const ACTIVITY = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'focusin'] as const;

export function useIdleListening() {
  const isPlaying = useStore((s) => s.isPlaying);
  const searchOpen = useStore((s) => s.searchOpen);
  const guideOpen = useStore((s) => s.guideOpen);
  const reducedMotion = useStore((s) => s.reducedMotion);

  useEffect(() => {
    const clear = () => { document.body.dataset.listening = ''; };
    const active = isPlaying && !searchOpen && !guideOpen && !reducedMotion;
    if (!active) { clear(); return; }

    let timer = 0;
    const arm = () => {
      clear();
      clearTimeout(timer);
      timer = window.setTimeout(() => { document.body.dataset.listening = '1'; }, IDLE_MS);
    };
    arm();
    ACTIVITY.forEach((e) => window.addEventListener(e, arm, { passive: true }));
    return () => {
      clearTimeout(timer);
      ACTIVITY.forEach((e) => window.removeEventListener(e, arm));
      clear();
    };
  }, [isPlaying, searchOpen, guideOpen, reducedMotion]);
}
