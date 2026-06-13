import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, type BufferAttribute, Group, Points, Vector3 } from 'three';
import { solarRefs } from './refs';

const N = 160;
const Z_BACK = 4;     // local +Z is behind the ship (it faces -Z)
const Z_FRONT = -12;
const SPAN = Z_BACK - Z_FRONT;

// Streaks that stream past the canopy when the ship moves fast — a points tube laid along
// the flight axis (ship frame, -Z forward) scrolling toward/behind the pilot, brightening
// with speed. Cheap motion cue; only mounted in the cockpit phase (desktop).
export default function WarpStreaks() {
  const root = useRef<Group>(null);
  const pts = useRef<Points>(null);
  const lookAt = useRef(new Vector3());

  const positions = useMemo(() => {
    const arr = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const a = i * 2.39996;
      const r = 0.4 + ((i * 53) % 100) / 100 * 2.2;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = Math.sin(a) * r;
      arr[i * 3 + 2] = Z_FRONT + ((i * 37) % 100) / 100 * SPAN;
    }
    return arr;
  }, []);

  useFrame((_, dt) => {
    const g = root.current;
    if (!g) return;
    const vis = solarRefs.cockpitView && solarRefs.shipSpeed > 0.05;
    g.visible = vis;
    if (!vis || !pts.current) return;

    g.position.copy(solarRefs.shipPos);
    lookAt.current.copy(solarRefs.shipPos).add(solarRefs.shipForward);
    g.lookAt(lookAt.current);

    const attr = pts.current.geometry.getAttribute('position') as BufferAttribute;
    const a = attr.array as Float32Array;
    const step = Math.min(40, 6 + solarRefs.shipSpeed * 8) * dt; // scroll backward
    for (let i = 0; i < N; i++) {
      let z = a[i * 3 + 2] + step;
      if (z > Z_BACK) z -= SPAN;
      a[i * 3 + 2] = z;
    }
    attr.needsUpdate = true;
    const m = pts.current.material as { opacity?: number };
    m.opacity = Math.min(0.7, solarRefs.shipSpeed * 0.6);
  });

  return (
    <group ref={root} visible={false}>
      <points ref={pts}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <pointsMaterial size={0.06} color="#bfe6ff" transparent opacity={0}
          blending={AdditiveBlending} depthWrite={false} sizeAttenuation />
      </points>
    </group>
  );
}
