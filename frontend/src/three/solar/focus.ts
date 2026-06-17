import type { Mode } from '../../state/store';

// Which body (by hex) is "close" enough to deserve a high-res texture, given the current
// mode + selection. explore/boarding → the one planet you're on; journey → both endpoints;
// everything else (system/intro/fly) → none (all distant → 2K is plenty, saves VRAM).
export function isFocused(mode: Mode, sel: string[], hex: string): boolean {
  if (mode === 'explore' || mode === 'boarding') return sel[0] === hex;
  if (mode === 'journey') return sel[0] === hex || sel[1] === hex;
  return false;
}
