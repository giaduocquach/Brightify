import { Effect, BlendFunction } from 'postprocessing';
import { Uniform, Color } from 'three';
import { VIBE_GRADE_FRAG } from '../shaders';

// Screen-space mood grade. Mounted via <primitive object={effect}/> (NOT wrapEffect): under
// React 19, wrapEffect serialises the effect's props/children and hits "circular structure to
// JSON". The instance is created once with useMemo in Scene and its uniforms are driven
// imperatively each frame — the established pattern in this codebase for ref-bearing effects.
export class VibeGradeEffect extends Effect {
  constructor() {
    super('VibeGradeEffect', VIBE_GRADE_FRAG, {
      blendFunction: BlendFunction.NORMAL,
      uniforms: new Map<string, Uniform>([
        ['uTint', new Uniform(new Color(1, 1, 1))],
        ['uSat', new Uniform(1)],
        ['uBeat', new Uniform(0)],
      ]),
    });
  }
}
