import { useFrame, useThree } from '@react-three/fiber';
import { Vector3 } from 'three';
import { useEffect, useRef } from 'react';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex, OUTER_RADIUS } from './bodies';

// Camera Director.
//   • system / intro / explore → follow-orbit: one OrbitControls owns rotate + zoom; we
//     only move the focus (Sun → planet), translating camera+target by the focus delta so
//     the user's angle/zoom survive.
//   • journey / fly → FLIGHT: OrbitControls is disabled. A ~2s reveal flies the camera
//     third-person behind the ship (showing it off), then dives to the pilot's eye for a
//     FIRST-PERSON view out of the glass canopy. Drag to look around (clamped, eases back).

const FRAME_SMOOTH = 0.0025;
const FRAMED_EPS = 0.05;
const WORLDUP = new Vector3(0, 1, 0);
const REVEAL_S = 2.0;            // ship-reveal duration before entering the cockpit
const LOOK_SENS = 0.0016;        // rad per pixel dragged
const LOOK_CLAMP = 0.7;          // ±40° head turn inside the canopy

const smooth = (x: number) => x * x * (3 - 2 * x);
const isFlight = (m: string) => m === 'journey' || m === 'fly';

export default function FocusController() {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null;
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);

  const focus = useRef(new Vector3());
  const prevFocus = useRef(new Vector3());
  const delta = useRef(new Vector3());
  const desired = useRef(new Vector3());
  const camDir = useRef(new Vector3());
  const inited = useRef(false);
  const prevMode = useRef<string>('');
  const framing = useRef(false);

  // flight state
  const flightT = useRef(0);
  const yaw = useRef(0);
  const pitch = useRef(0);
  const dragging = useRef(false);
  const lastX = useRef(0);
  const lastY = useRef(0);
  const flightRef = useRef(false);
  const eye = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const right = useRef(new Vector3());
  const lookDir = useRef(new Vector3());
  const lookAt = useRef(new Vector3());
  const tp = useRef(new Vector3());
  const prevShip = useRef(new Vector3());

  // Look-around drag handlers (active only during the cockpit phase; OrbitControls is off).
  useEffect(() => {
    const el = gl.domElement;
    const down = (e: PointerEvent) => {
      if (!flightRef.current) return;
      dragging.current = true; lastX.current = e.clientX; lastY.current = e.clientY;
    };
    const move = (e: PointerEvent) => {
      if (!flightRef.current || !dragging.current) return;
      yaw.current = Math.max(-LOOK_CLAMP, Math.min(LOOK_CLAMP, yaw.current - (e.clientX - lastX.current) * LOOK_SENS));
      pitch.current = Math.max(-LOOK_CLAMP, Math.min(LOOK_CLAMP, pitch.current - (e.clientY - lastY.current) * LOOK_SENS));
      lastX.current = e.clientX; lastY.current = e.clientY;
    };
    const up = () => { dragging.current = false; };
    el.addEventListener('pointerdown', down);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      el.removeEventListener('pointerdown', down);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [gl]);

  useFrame((_, dt) => {
    const flight = isFlight(mode) && solarRefs.shipActive;
    flightRef.current = flight;

    // ship speed for warp/flame effects
    solarRefs.shipSpeed = dt > 0 ? prevShip.current.distanceTo(solarRefs.shipPos) / dt : 0;
    prevShip.current.copy(solarRefs.shipPos);

    // ── FLIGHT: reveal → first-person cockpit (OrbitControls off) ──
    if (flight) {
      if (controls) controls.enabled = false;
      if (mode !== prevMode.current) { prevMode.current = mode; flightT.current = 0; yaw.current = 0; pitch.current = 0; }
      flightT.current += dt;

      fwd.current.copy(solarRefs.shipForward).normalize();
      if (fwd.current.lengthSq() < 1e-4) fwd.current.set(0, 0, 1);
      eye.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, 0.12).addScaledVector(WORLDUP, 0.18);

      if (flightT.current < REVEAL_S) {
        // third-person reveal pose → ease toward the cockpit eye
        const t = smooth(flightT.current / REVEAL_S);
        tp.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, -3.0).addScaledVector(WORLDUP, 1.3);
        camera.position.lerpVectors(tp.current, eye.current, t);
        lookAt.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, t * 8);
        camera.up.lerp(WORLDUP, 0.1);
        camera.lookAt(lookAt.current);
        solarRefs.cockpitView = false;
      } else {
        // first-person: sit at the eye, look forward + user yaw/pitch (eased back to fwd)
        solarRefs.cockpitView = true;
        if (!dragging.current) {
          const e = Math.min(1, dt * 1.2);
          yaw.current += (0 - yaw.current) * e;
          pitch.current += (0 - pitch.current) * e;
        }
        right.current.copy(fwd.current).cross(WORLDUP).normalize();
        lookDir.current.copy(fwd.current).applyAxisAngle(WORLDUP, yaw.current).applyAxisAngle(right.current, pitch.current);
        camera.position.lerp(eye.current, Math.min(1, dt * 8));
        camera.up.lerp(WORLDUP, Math.min(1, dt * 8));
        lookAt.current.copy(camera.position).addScaledVector(lookDir.current, 10);
        camera.lookAt(lookAt.current);
      }
      prevFocus.current.copy(solarRefs.shipPos);
      return;
    }

    // ── ORBIT modes (system / intro / explore) ──
    solarRefs.cockpitView = false;
    if (!controls) return;
    controls.enabled = true;

    if (mode === 'explore' && sel[0] && solarRefs.bodyPos[sel[0]]) {
      focus.current.copy(solarRefs.bodyPos[sel[0]]);
    } else {
      focus.current.set(0, 0, 0); // Sun
    }

    if (!inited.current) { prevFocus.current.copy(focus.current); inited.current = true; }

    if (mode !== prevMode.current) {
      prevMode.current = mode;
      framing.current = true;
      camDir.current.copy(camera.position).sub(focus.current);
      if (camDir.current.lengthSq() < 1e-4) camDir.current.set(0.2, 0.5, 1);
      camDir.current.normalize();
      if (mode === 'explore') {
        const size = sel[0] ? bodyByHex(sel[0])?.size ?? 0.5 : 0.5;
        controls.minDistance = size * 1.25; controls.maxDistance = size * 14 + 6;
      } else {
        controls.minDistance = 8; controls.maxDistance = OUTER_RADIUS * 2.4;
      }
    }

    if (framing.current) {
      const size = mode === 'explore' && sel[0] ? bodyByHex(sel[0])?.size ?? 0.5 : 1;
      const dist = mode === 'explore' ? size * 3 + 0.7 : 40;
      desired.current.copy(focus.current).addScaledVector(camDir.current, dist);
      const k = 1 - Math.pow(FRAME_SMOOTH, dt);
      camera.position.lerp(desired.current, k);
      controls.target.lerp(focus.current, k);
      if (camera.position.distanceTo(desired.current) < FRAMED_EPS) framing.current = false;
    } else {
      delta.current.copy(focus.current).sub(prevFocus.current);
      camera.position.add(delta.current);
      controls.target.add(delta.current);
    }

    prevFocus.current.copy(focus.current);
    controls.update();
  });

  return null;
}
