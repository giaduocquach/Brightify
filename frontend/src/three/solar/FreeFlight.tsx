import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Vector3 } from 'three';
import { solarRefs } from './refs';

const R = 12; // wander envelope radius

// Free-flight ("Tương tự"): drives the pod along a smooth Lissajous path through open space
// by writing the shared ship position/forward each frame (read by Spaceship + FocusController).
// Renders nothing itself — the similar songs live in the FlyHUD side panel.
export default function FreeFlight() {
  const a = useRef(new Vector3());
  const b = useRef(new Vector3());
  const frozenT = useRef(0); // reduced-motion freezes the pod (radio keeps playing, view holds)

  useFrame((state) => {
    if (!solarRefs.reducedMotion) frozenT.current = state.clock.elapsedTime;
    const t = solarRefs.reducedMotion ? frozenT.current : state.clock.elapsedTime;
    a.current.set(Math.sin(t * 0.09) * R, Math.sin(t * 0.13) * R * 0.4, Math.cos(t * 0.075) * R);
    const t2 = t + 0.06;
    b.current.set(Math.sin(t2 * 0.09) * R, Math.sin(t2 * 0.13) * R * 0.4, Math.cos(t2 * 0.075) * R);
    solarRefs.shipPos.copy(a.current);
    solarRefs.shipForward.copy(b.current).sub(a.current).normalize();
    if (solarRefs.shipForward.lengthSq() < 1e-4) solarRefs.shipForward.set(0, 0, 1);
  });

  return null;
}
