import { BlendFunction, Effect } from 'postprocessing';
import { Uniform, Vector2 } from 'three';
import { LENS_FRAG } from '../shaders';

// Screen-space gravitational lensing post-effect. Uses mainUv (UV bend, a single dependent
// read → NOT convolution → merges with Bloom/SMAA) + mainImage (void + Einstein ring). Driven
// via a <primitive> wrapper (LensingPass in SolarSystem) so we hold the instance directly and
// call `set()` each frame — avoiding wrapEffect's JSON.stringify(props) (which chokes on the
// React-19 ref / Three-object graph).
export class LensingEffectImpl extends Effect {
  constructor() {
    super('LensingEffect', LENS_FRAG, {
      blendFunction: BlendFunction.NORMAL,
      uniforms: new Map<string, Uniform>([
        ['uLensPos', new Uniform(new Vector2(0.5, 0.5))],
        ['uLensRadius', new Uniform(0.12)],
        ['uStrength', new Uniform(0)],
      ]),
    });
  }

  set(x: number, y: number, radius: number, strength: number): void {
    const u = this.uniforms;
    (u.get('uLensPos')!.value as Vector2).set(x, y);
    u.get('uLensRadius')!.value = radius;
    u.get('uStrength')!.value = strength;
  }
}
