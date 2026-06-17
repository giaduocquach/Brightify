import { Vector3 } from 'three';
import { SUN_SIZE } from './bodies';

// Flight path between two (moving) planet CENTRES: a quadratic Bézier whose control
// point is lifted straight UP (+Y), so the ship arcs "up and over" the ecliptic where
// the Sun (origin, y≈0) and every planet (all near y≈0) live — clearing them no matter
// where A and B sit, including opposite sides of the Sun. Shared by the ship (position +
// forward look-ahead) so its trajectory stays consistent.

const mid = new Vector3();
const ctrl = new Vector3();
const t0 = new Vector3();
const t1 = new Vector3();

// Apex clearance above the ecliptic. A quadratic Bézier only reaches ~half its control
// height at the curve's peak, so we set ctrl.y to ~2× the target clearance.
const SUN_CLEAR = SUN_SIZE + 4; // ≈6.4: comfortably above the Sun + its glow
const APEX_K = 0.55;            // extra lift per unit of A–B distance (longer trips bow higher)

export function journeyPoint(a: Vector3, b: Vector3, p: number, target: Vector3): Vector3 {
  mid.copy(a).add(b).multiplyScalar(0.5);

  // peak clearance: always above the Sun, higher for longer crossings
  const clearance = SUN_CLEAR + a.distanceTo(b) * APEX_K;
  ctrl.copy(mid);
  ctrl.y = mid.y + clearance * 2; // ~2× — the curve peaks at roughly half of ctrl.y

  const u = 1 - p;
  // (1-p)^2 A + 2(1-p)p C + p^2 B
  t0.copy(a).multiplyScalar(u * u);
  t1.copy(ctrl).multiplyScalar(2 * u * p);
  target.copy(t0).add(t1).addScaledVector(b, p * p);
  return target;
}
