// Mutable shared positions for the solar scene — written by bodies/ship every
// frame, read by the camera rig and journey props. Same "mutable ref, never
// React state" philosophy as engine.features: zero re-render churn.
import { Vector3, type Mesh } from 'three';

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
  /** True while the astronaut is running on a planet surface. */
  runnerActive: false,
};

export const ZERO = new Vector3(0, 0, 0);
