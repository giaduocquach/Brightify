import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

/**
 * Live OS-level "reduce motion" preference. Client-only SPA, so we read matchMedia
 * immediately (no SSR flash) and subscribe to changes. The *effective* reduced-motion
 * flag (this OR the in-app manual toggle) is computed by the caller (App) and pushed to
 * both `solarRefs.reducedMotion` (read by useFrame, zero re-render) and the zustand store
 * (for render-time props like drei <Stars speed>).
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(
    () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches,
  );
  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}
