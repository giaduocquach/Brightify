import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Euler, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex, locomotionFor } from './bodies';

const RING_EULER = new Euler(Math.PI / 2 - 0.35, 0, 0); // matches the Saturn ring mesh tilt

// Smooth wandering direction on the unit sphere (sum of out-of-phase sines → organic,
// non-repeating, deterministic — no Math.random). Used for walk/hop/float.
function wanderDir(t: number, out: Vector3): Vector3 {
  const theta = t * 0.16 + Math.sin(t * 0.073) * 1.6 + Math.sin(t * 0.031) * 0.8;
  const phi = Math.sin(t * 0.051) * 0.95 + Math.sin(t * 0.117) * 0.4;
  const cp = Math.cos(phi);
  return out.set(cp * Math.cos(theta), Math.sin(phi), cp * Math.sin(theta));
}

// Build an orthonormal basis (u, v in-plane; n = normal) for a plane given by an Euler tilt,
// matching how the corresponding mesh (ring / disk) is rotated.
function planeBasis(e: Euler) {
  return {
    u: new Vector3(1, 0, 0).applyEuler(e),
    v: new Vector3(0, 1, 0).applyEuler(e),
    n: new Vector3(0, 0, 1).applyEuler(e),
  };
}

// Explore stage: each frame writes the shared runner refs (position/forward/up/stance),
// DISPATCHED by the body's locomotion type, so the astronaut moves differently on each body:
//   walk (rocky + asteroid) · hop (Moon, low-gravity) · float (gas/ice giants) ·
//   ringwalk (Saturn rings). Renders nothing.
export default function SurfaceRun() {
  const hex = useStore((s) => s.selectedColors[0]);
  const body = hex ? bodyByHex(hex) : undefined;

  const dir = useRef(new Vector3());
  const dirNext = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const center = useRef(new Vector3());
  const a = useRef(new Vector3());
  const b = useRef(new Vector3());
  const ring = useMemo(() => planeBasis(RING_EULER), []);
  const frozenT = useRef(0); // reduced-motion freezes the wander/orbit path

  useEffect(() => {
    solarRefs.runnerActive = true;
    return () => { solarRefs.runnerActive = false; };
  }, []);

  // tangent of the wander path (for walk/hop/float) → runnerForward
  const wanderTangent = (t: number, scale: number) => {
    wanderDir(t * scale, dir.current).normalize();
    wanderDir(t * scale + 0.05, dirNext.current).normalize();
    fwd.current.copy(dirNext.current).sub(dir.current);
    fwd.current.addScaledVector(dir.current, -fwd.current.dot(dir.current)); // project to tangent
    if (fwd.current.lengthSq() < 1e-6) fwd.current.set(0, 0, 1);
    solarRefs.runnerForward.copy(fwd.current).normalize();
    solarRefs.runnerUp.copy(dir.current);
  };

  useFrame((state) => {
    if (!body || !hex) return;
    if (useStore.getState().mode === 'boarding') return; // freeze under the tractor beam
    const c = solarRefs.bodyPos[hex];
    if (!c) return;
    center.current.copy(c);
    if (!solarRefs.reducedMotion) frozenT.current = state.clock.elapsedTime;
    const t = solarRefs.reducedMotion ? frozenT.current : state.clock.elapsedTime;
    const size = body.size;
    const stance = locomotionFor(body);
    solarRefs.runnerStance = stance;
    solarRefs.runnerSink = 0;

    switch (stance) {
      case 'hop': {
        wanderTangent(t, 0.45); // slower wander
        const air = Math.pow(Math.abs(Math.sin(t * 2.0)), 0.6); // low-gravity hang-time (longer)
        solarRefs.runnerPos.copy(center.current).addScaledVector(dir.current, size * (1.03 + air * 0.6));
        break;
      }
      case 'float': {
        wanderTangent(t, 0.22); // drift slowly above the cloud tops
        const bob = Math.sin(t * 0.8) * 0.03;
        solarRefs.runnerPos.copy(center.current).addScaledVector(dir.current, size * (1.18 + bob));
        break;
      }
      case 'ringwalk': {
        const ang = t * 0.16;
        const radius = size * (1.45 + 0.35 * (0.5 + 0.5 * Math.sin(t * 0.2))); // drift within the ring band
        a.current.copy(ring.u).multiplyScalar(Math.cos(ang) * radius);
        b.current.copy(ring.v).multiplyScalar(Math.sin(ang) * radius);
        solarRefs.runnerPos.copy(center.current).add(a.current).add(b.current);
        a.current.copy(ring.u).multiplyScalar(-Math.sin(ang));
        b.current.copy(ring.v).multiplyScalar(Math.cos(ang));
        solarRefs.runnerForward.copy(a.current).add(b.current).normalize();
        solarRefs.runnerUp.copy(ring.n);
        break;
      }
      default: { // walk (rocky planets + the dark asteroid)
        wanderTangent(t, 1.0);
        solarRefs.runnerPos.copy(center.current).addScaledVector(dir.current, size * 1.03);
      }
    }
  });

  return null;
}
