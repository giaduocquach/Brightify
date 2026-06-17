import { useMemo } from 'react';
import { BufferGeometry, Float32BufferAttribute } from 'three';
import { BODIES } from './bodies';

const SEGMENTS = 128;

// Faint guide circles for each orbit, so the system reads as structured rather
// than a random scatter of points.
export default function OrbitRings() {
  const geometries = useMemo(
    () =>
      // heliocentric, near-circular orbits only — skip the Moon (orbits Earth), the
      // special objects (comet/black hole), and visibly eccentric orbits (Mercury/Mars):
      // their paths wouldn't be these centred circles.
      BODIES.filter((b) => !b.parent && !b.special && (b.eccentricity ?? 0) <= 0.06).map((b) => {
        const pts: number[] = [];
        for (let i = 0; i <= SEGMENTS; i++) {
          const a = (i / SEGMENTS) * Math.PI * 2;
          pts.push(Math.cos(a) * b.orbitRadius, 0, Math.sin(a) * b.orbitRadius);
        }
        const g = new BufferGeometry();
        g.setAttribute('position', new Float32BufferAttribute(pts, 3));
        return g;
      }),
    [],
  );

  return (
    <group>
      {geometries.map((g, i) => (
        <lineLoop key={i} geometry={g}>
          <lineBasicMaterial color="#6b7bb0" transparent opacity={0.1} />
        </lineLoop>
      ))}
    </group>
  );
}
