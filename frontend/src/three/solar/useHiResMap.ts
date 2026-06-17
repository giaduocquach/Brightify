import { useEffect, useRef, useState } from 'react';
import { useThree } from '@react-three/fiber';
import { SRGBColorSpace, TextureLoader, type Texture } from 'three';
import { HI_RES_MAP } from './texturesHi';

// Loads the 4K day map for `hex` when `active`, returns it once decoded, and disposes it
// (frees ~88MB VRAM) when `active` flips false or the component unmounts. Imperative (not
// Suspense) so the 2K baseline stays visible underneath until the 4K is ready — no flash —
// and so disposal is deterministic. A missing/failed 4K file silently keeps the 2K map.
export function useHiResMap(hex: string, active: boolean): Texture | undefined {
  const maxAniso = useThree((s) => s.gl.capabilities.getMaxAnisotropy());
  const [hi, setHi] = useState<Texture>();
  const cur = useRef<Texture | undefined>(undefined);

  useEffect(() => {
    const url = HI_RES_MAP[hex];
    if (!active || !url) return;
    let cancelled = false;
    new TextureLoader().load(
      url,
      (t) => {
        if (cancelled) { t.dispose(); return; }
        t.colorSpace = SRGBColorSpace;
        t.anisotropy = maxAniso;
        t.needsUpdate = true;
        cur.current = t;
        setHi(t);
      },
      undefined,
      () => { /* 4K missing/failed → keep the resident 2K baseline */ },
    );
    return () => {
      cancelled = true;                 // drop any in-flight result
      if (cur.current) { cur.current.dispose(); cur.current = undefined; }
      setHi(undefined);                 // revert to 2K
    };
  }, [hex, active, maxAniso]);

  return hi;
}
