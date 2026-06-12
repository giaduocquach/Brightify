import { Vector3 } from 'three';

// A gently bowed flight path between two (moving) bodies: a quadratic Bézier whose
// control point is lifted radially outward + up, so the ship arcs through open space
// rather than skimming a straight chord. Shared by the ship and the nebula trail so
// both stay perfectly aligned.

const mid = new Vector3();
const ctrl = new Vector3();
const out = new Vector3();
const t0 = new Vector3();
const t1 = new Vector3();

export function journeyPoint(a: Vector3, b: Vector3, p: number, target: Vector3): Vector3 {
  mid.copy(a).add(b).multiplyScalar(0.5);
  out.copy(mid);
  if (out.lengthSq() < 1e-4) out.set(0, 1, 0);
  out.normalize();
  const bow = a.distanceTo(b) * 0.22;
  ctrl.copy(mid).addScaledVector(out, bow);
  ctrl.y += bow;

  const u = 1 - p;
  // (1-p)^2 A + 2(1-p)p C + p^2 B
  t0.copy(a).multiplyScalar(u * u);
  t1.copy(ctrl).multiplyScalar(2 * u * p);
  target.copy(t0).add(t1).addScaledVector(b, p * p);
  return target;
}
