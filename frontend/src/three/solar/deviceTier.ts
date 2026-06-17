import { useMemo } from 'react';
import { useThree } from '@react-three/fiber';

const IS_MOBILE = typeof window !== 'undefined' && window.innerWidth < 768;

export type DeviceTier = 'low' | 'high';

// Cheap one-shot capability probe deciding whether a device can afford the on-demand 4K
// texture upgrade. `low` → stay on the 2K baseline everywhere (mobile, weak/unknown-but-
// constrained GPUs, ≤4GB RAM); `high` → allow one 4K map for the focused planet. A single
// 4K texture is ~88MB VRAM, safe on any non-mobile GPU reporting MAX_TEXTURE_SIZE ≥ 8192.
export function useDeviceTier(): DeviceTier {
  const gl = useThree((s) => s.gl);
  return useMemo(() => {
    const maxTex = gl.capabilities.maxTextureSize ?? 0;
    const mem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
    if (IS_MOBILE) return 'low';
    if (maxTex < 8192) return 'low';
    if (mem !== undefined && mem <= 4) return 'low';
    return 'high';
  }, [gl]);
}
