// Mutable shared positions for the solar scene — written by bodies/ship every
// frame, read by the camera rig and journey props. Same "mutable ref, never
// React state" philosophy as engine.features: zero re-render churn.
import { Vector3, type Mesh } from 'three';
import type { LocomotionType } from './bodies';

export const solarRefs = {
  /** Live world position of each celestial body, keyed by its emotion hex. */
  bodyPos: {} as Record<string, Vector3>,
  /** Live world position of the spaceship during a journey. */
  shipPos: new Vector3(),
  /** Unit forward (travel) direction of the ship — drives the cockpit camera. */
  shipForward: new Vector3(0, 0, 1),
  /** True while a journey is under way (ship + cockpit visible). */
  shipActive: false,
  /** Per-frame ship speed (world units/s) — drives warp streaks + flame stretch. */
  shipSpeed: 0,
  /** True once the flight reveal is done and we're inside the cockpit (first-person). */
  cockpitView: false,
  /** The Sun core mesh, shared so the GodRays pass can use it as the light source. */
  sunMesh: null as Mesh | null,
  /** Live world position of the astronaut while running on a planet (explore). */
  runnerPos: new Vector3(),
  /** Unit forward (travel) direction of the runner — drives the chase camera. */
  runnerForward: new Vector3(0, 0, 1),
  /** Body-appropriate "up" for the runner (radial for walk/hop/float/surf; ring-plane
   *  normal for ringwalk). Astronaut orients its feet to this instead of always radial. */
  runnerUp: new Vector3(0, 1, 0),
  /** How the Astronaut should pose/animate — set by SurfaceRun, read by Astronaut. */
  runnerStance: 'walk' as LocomotionType,
  /** Sink progress 0→1 (black hole): drives curl + shrink + fade. 0 for every other stance. */
  runnerSink: 0 as number,
  /** True while the astronaut is running on a planet surface. */
  runnerActive: false,
  /** Lift progress 0→1 (eased) while the tractor beam draws the astronaut up. */
  boardingLift: 0 as number,
  /** World point just under the hovering saucer the astronaut is drawn up toward. */
  boardingTarget: new Vector3(),
  /** Effective prefers-reduced-motion (OS pref OR manual toggle). Read in useFrame to
   *  freeze drift/spin/wander + snap swoop transitions; audio-reactive pulses stay on. */
  reducedMotion: false,
};

export const ZERO = new Vector3(0, 0, 0);
