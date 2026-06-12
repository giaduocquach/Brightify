import { useFrame, useThree } from '@react-three/fiber';
import { Vector3 } from 'three';
import { useRef } from 'react';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';

const SMOOTH = 0.0025;
const WORLDUP = new Vector3(0, 1, 0);

// Guided cinematic camera for the focused modes; in the overview it yields to
// OrbitControls (mounted by SolarSystem) so the user can drag-rotate to aim.
//  • explore        → chase-cam hugging the surface behind the running astronaut
//  • journey / fly   → FIRST-PERSON from inside the cockpit, looking out
export default function CameraRig() {
  const camera = useThree((s) => s.camera);
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);

  const look = useRef(new Vector3());
  const desired = useRef(new Vector3());
  const up = useRef(new Vector3(0, 1, 0));
  const fwd = useRef(new Vector3());

  useFrame((_, dt) => {
    // overview: OrbitControls owns the camera
    if (mode === 'system' || mode === 'intro') return;

    const k = 1 - Math.pow(SMOOTH, dt);

    // EXPLORE — hug the surface just behind the runner so the planet fills the view
    // and curves to a horizon (you're ON the world, not orbiting a marble). Camera
    // height/back are proportional to the planet radius.
    if (mode === 'explore' && solarRefs.runnerActive && sel[0] && solarRefs.bodyPos[sel[0]]) {
      const center = solarRefs.bodyPos[sel[0]];
      const size = bodyByHex(sel[0])?.size ?? 0.5;
      up.current.copy(solarRefs.runnerPos).sub(center).normalize();
      if (up.current.lengthSq() < 1e-4) up.current.set(0, 1, 0);
      fwd.current.copy(solarRefs.runnerForward).normalize();
      // look a bit ahead + just above the runner → shows the curved horizon ahead
      look.current.lerp(
        desired.current.copy(solarRefs.runnerPos)
          .addScaledVector(fwd.current, size * 1.4)
          .addScaledVector(up.current, size * 0.5),
        k,
      );
      desired.current.copy(solarRefs.runnerPos)
        .addScaledVector(up.current, size * 0.85)
        .addScaledVector(fwd.current, -size * 2.4);
      camera.up.lerp(up.current, k);
      camera.position.lerp(desired.current, k);
      camera.lookAt(look.current);
      return;
    }

    // JOURNEY / FLY — FIRST-PERSON: sit at the pilot's eye inside the cockpit and
    // look out along the flight direction (the ship's nose + canopy frame the view).
    if ((mode === 'journey' || mode === 'fly') && solarRefs.shipActive) {
      fwd.current.copy(solarRefs.shipForward).normalize();
      desired.current.copy(solarRefs.shipPos)
        .addScaledVector(fwd.current, 0.12); // just inside the canopy
      desired.current.y += 0.22;             // eye height
      look.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, 10);
      camera.up.lerp(WORLDUP, k);
      camera.position.lerp(desired.current, 1 - Math.pow(0.0001, dt)); // tight FP follow
      camera.lookAt(look.current);
    }
  });

  return null;
}
