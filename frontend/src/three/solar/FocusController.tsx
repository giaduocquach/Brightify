import { useFrame, useThree } from '@react-three/fiber';
import { Vector3 } from 'three';
import { useEffect, useRef } from 'react';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { vibeRefs } from '../vibe/vibeRefs';
import { bodyByHex, locomotionFor, OUTER_RADIUS, type LocomotionType } from './bodies';

// Camera Director.
//   • system / intro / explore → follow-orbit: one OrbitControls owns rotate + zoom; we
//     only move the focus (Sun → planet), translating camera+target by the focus delta so
//     the user's angle/zoom survive.
//   • journey / fly → FLIGHT: OrbitControls is disabled. A ~2s reveal flies the camera
//     third-person behind the ship (showing it off), then dives to the pilot's eye for a
//     FIRST-PERSON view out of the glass canopy. Drag to look around (clamped, eases back).

const CRUISE_S = 1.5;            // base "fly-in" duration to a planet (scaled by travel distance)
const WORLDUP = new Vector3(0, 1, 0);
const REVEAL_S = 2.0;            // ship-reveal duration before entering the cockpit
const LOOK_SENS = 0.0016;        // rad per pixel dragged
const LOOK_CLAMP = 0.7;          // ±40° head turn inside the canopy

const smooth = (x: number) => x * x * (3 - 2 * x);
const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));
const isFlight = (m: string) => m === 'journey' || m === 'fly';

// Third-person framing distance per locomotion stance, so each body reads well: surf pulls
// back to see the comet fly, sink frames the whole accretion disk, ringwalk shows the ring.
function framingDistFor(stance: LocomotionType, size: number): number {
  switch (stance) {
    case 'surf': return Math.max(2.2, size * 6 + 2);
    case 'sink': return size * 8 + 3;
    case 'ringwalk': return size * 3 + 1.5;
    case 'float': return size * 1.4 + 1.0;
    default: return size * 1.0 + 0.7; // walk / hop
  }
}

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
  // cruise fly-in: lerp from a captured start pose to the moving target over a distance-scaled
  // duration (far swoops take longer, near reframes are snappier — both end at zero velocity).
  const frameT = useRef(0);
  const frameDur = useRef(CRUISE_S);
  const startPos = useRef(new Vector3());
  const startTarget = useRef(new Vector3());
  // idle "breathing" drift — a tiny camera offset, applied AFTER controls.update() and undone
  // at the start of the next frame so it never accumulates or gets absorbed by OrbitControls.
  const breath = useRef(new Vector3());
  const prevBreath = useRef(new Vector3());

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
  const revealPose = useRef(new Vector3());
  const flightStart = useRef(new Vector3()); // camera pose when flight begins → blend into the reveal
  const prevShip = useRef(new Vector3());

  // Keep the runner stance in sync the instant a body is picked, so the very first explore
  // framing frame reads the correct per-stance distance (no one-frame distance pop).
  useEffect(() => {
    if (sel[0]) { const b = bodyByHex(sel[0]); if (b) solarRefs.runnerStance = locomotionFor(b); }
  }, [sel]);

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
    const rm = solarRefs.reducedMotion; // reduced-motion: snap transitions, drop drift
    const flight = isFlight(mode) && solarRefs.shipActive;
    flightRef.current = flight;

    // Ship mounts one frame after mode flips to journey/fly. Hold the current pose for that frame
    // instead of kicking off an orbit cruise that would immediately be overridden → avoids a snap.
    if (isFlight(mode) && !solarRefs.shipActive) return;

    // ship speed for warp/flame effects
    solarRefs.shipSpeed = dt > 0 ? prevShip.current.distanceTo(solarRefs.shipPos) / dt : 0;
    prevShip.current.copy(solarRefs.shipPos);

    // ── FLIGHT: reveal → first-person cockpit (OrbitControls off) ──
    if (flight) {
      if (controls) controls.enabled = false;
      if (mode !== prevMode.current) {
        prevMode.current = mode; flightT.current = 0; yaw.current = 0; pitch.current = 0;
        flightStart.current.copy(camera.position); // where we were (orbit/boarding) → ease into the reveal
      }
      flightT.current += dt;

      fwd.current.copy(solarRefs.shipForward).normalize();
      if (fwd.current.lengthSq() < 1e-4) fwd.current.set(0, 0, 1);
      eye.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, 0.12).addScaledVector(WORLDUP, 0.18);

      if (!rm && flightT.current < REVEAL_S) {
        // third-person reveal pose → ease toward the cockpit eye (skipped when reduced-motion:
        // the swooping dive is the strongest vestibular trigger → jump straight to the cockpit)
        const t = smooth(flightT.current / REVEAL_S);
        tp.current.copy(solarRefs.shipPos).addScaledVector(fwd.current, -3.0).addScaledVector(WORLDUP, 1.3);
        // intended reveal path (third-person → eye); then pull in from the prior camera pose over
        // the first ~0.5s so entering flight doesn't teleport to the behind-the-ship pose.
        revealPose.current.lerpVectors(tp.current, eye.current, t);
        const entry = smooth(Math.min(1, flightT.current / 0.5));
        camera.position.lerpVectors(flightStart.current, revealPose.current, entry);
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
        // gentle "breathing": a tiny slow drift so the cabin feels alive (NOT a fast warp).
        const tt = _.clock.elapsedTime;
        const bYaw = rm ? 0 : Math.sin(tt * 0.45) * 0.012;
        const bPitch = rm ? 0 : Math.sin(tt * 0.33 + 1.3) * 0.009;
        if (!rm) eye.current.addScaledVector(WORLDUP, Math.sin(tt * 0.6) * 0.012);
        right.current.copy(fwd.current).cross(WORLDUP).normalize();
        lookDir.current.copy(fwd.current)
          .applyAxisAngle(WORLDUP, yaw.current + bYaw)
          .applyAxisAngle(right.current, pitch.current + bPitch);
        // ease the first-person follow in over ~0.5s after the reveal so it doesn't snap-grab
        const fpEase = rm ? 1 : smooth(clamp((flightT.current - REVEAL_S) / 0.5, 0, 1));
        camera.position.lerp(eye.current, Math.min(1, dt * 8 * fpEase));
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
    camera.position.sub(prevBreath.current); // remove last frame's drift before controls reads it

    const exploring = (mode === 'explore' || mode === 'boarding') && !!sel[0];
    if (exploring && solarRefs.runnerStance === 'sink' && solarRefs.bodyPos[sel[0]]) {
      focus.current.copy(solarRefs.bodyPos[sel[0]]); // hold on the hole while the astronaut spirals in
    } else if (exploring && solarRefs.runnerActive && solarRefs.runnerPos.lengthSq() > 1e-4) {
      focus.current.copy(solarRefs.runnerPos); // third-person: follow the roaming astronaut
    } else if (exploring && solarRefs.bodyPos[sel[0]]) {
      focus.current.copy(solarRefs.bodyPos[sel[0]]); // fallback until the runner spawns
    } else {
      focus.current.set(0, 0, 0); // Sun
    }

    if (!inited.current) { prevFocus.current.copy(focus.current); inited.current = true; }

    if (mode !== prevMode.current) {
      prevMode.current = mode;
      framing.current = true;
      // Coming back from flight the camera.up may be tilted — level it so the reframe is upright.
      camera.up.set(0, 1, 0);
      // Capture the start pose: cruise lerps from here to the (moving) target.
      frameT.current = 0;
      startPos.current.copy(camera.position);
      startTarget.current.copy(controls.target);
      camDir.current.copy(camera.position).sub(focus.current);
      if (camDir.current.lengthSq() < 1e-4) camDir.current.set(0.2, 0.5, 1);
      camDir.current.normalize();
      // Scale the cruise duration by how far we have to travel (far swoops longer, near snappier).
      const isExplore0 = mode === 'explore' || mode === 'boarding';
      const size0 = isExplore0 && sel[0] ? bodyByHex(sel[0])?.size ?? 0.5 : 1;
      const dist0 = mode === 'boarding' ? size0 * 3 + 2
        : mode === 'explore' ? framingDistFor(solarRefs.runnerStance, size0)
        : 40;
      desired.current.copy(focus.current).addScaledVector(camDir.current, dist0);
      frameDur.current = CRUISE_S * clamp(startPos.current.distanceTo(desired.current) / 30, 0.6, 2.2);
      if (mode === 'explore' || mode === 'boarding') {
        // Keep wide constraints during the fly-in so controls.update() doesn't clamp the
        // camera to maxDistance from the (still-near-Sun) target before it reaches the planet.
        // Tight per-planet constraints are applied once framing completes (camera has arrived).
        controls.minDistance = 2; controls.maxDistance = OUTER_RADIUS * 2.4;
      } else {
        controls.minDistance = 8; controls.maxDistance = OUTER_RADIUS * 2.4;
      }
    }

    if (framing.current) {
      const isExplore = mode === 'explore' || mode === 'boarding';
      const size = isExplore && sel[0] ? bodyByHex(sel[0])?.size ?? 0.5 : 1;
      // Per-stance framing so each body reads well: boarding frames the whole abduction;
      // explore distance depends on the locomotion (surf pulls back to see the comet fly, etc.).
      const dist = mode === 'boarding' ? size * 3 + 2
        : mode === 'explore' ? framingDistFor(solarRefs.runnerStance, size)
        : 40;
      desired.current.copy(focus.current).addScaledVector(camDir.current, dist);
      // Distance-scaled smoothstep cruise (frameDur set at capture). Completes only when the
      // timer elapses → the handoff to delta-follow happens at the zero-velocity end of the curve.
      // Reduced-motion: e=1 snaps the reframe in one step (no gliding fly-in).
      frameT.current += dt;
      const e = rm ? 1 : smooth(Math.min(1, frameT.current / frameDur.current));
      camera.position.lerpVectors(startPos.current, desired.current, e);
      controls.target.lerpVectors(startTarget.current, focus.current, e);
      if (frameT.current >= frameDur.current) {
        framing.current = false;
        if (mode === 'explore' && sel[0]) {
          const s = bodyByHex(sel[0])?.size ?? 0.5;
          const d = framingDistFor(solarRefs.runnerStance, s);
          controls.minDistance = Math.min(s * 0.4 + 0.2, d * 0.5); controls.maxDistance = Math.max(s * 8 + 4, d * 3);
        }
      }
    } else {
      delta.current.copy(focus.current).sub(prevFocus.current);
      camera.position.add(delta.current);
      controls.target.add(delta.current);
    }

    prevFocus.current.copy(focus.current);
    controls.update();

    // gentle idle drift (skipped during the cruise fly-in, and under reduced-motion) → "living camera"
    if (!framing.current && !rm) {
      const t = _.clock.elapsedTime;
      breath.current.set(Math.sin(t * 0.12) * 0.15, Math.sin(t * 0.17 + 1.0) * 0.10, Math.cos(t * 0.09) * 0.15);
      // intense (Q2) songs add a subtle beat-driven shake (rides the same add/undo path as breath)
      const shake = vibeRefs.current.q2 * vibeRefs.current.beat * 0.22;
      if (shake > 0.001) {
        breath.current.x += Math.sin(t * 47) * shake;
        breath.current.y += Math.sin(t * 41 + 1.3) * shake;
      }
    } else {
      breath.current.set(0, 0, 0);
    }
    camera.position.add(breath.current);
    prevBreath.current.copy(breath.current);
  });

  return null;
}
