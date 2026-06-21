import { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Group, type Mesh, MeshStandardMaterial, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { journeyPoint } from './journeyPath';
import { bodyByHex } from './bodies';
import { useDeviceTier } from './deviceTier';
import ShipModel from './ShipModel';

const TRAVEL_S = 22;       // seconds to fly A → B — continuous, audio-independent
const ORBIT_SPEED = 0.12;  // rad/s of the gentle loop once we arrive at the destination

// A sleek PBR exploration craft (see ShipModel): metal hull that reflects the scene env map,
// twin engine plumes that pulse with the bass, nav + spine running lights. Banks into turns.
// Mostly seen during the ~2s reveal before the camera dives into the cockpit.
export default function Spaceship() {
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const tier = useDeviceTier();
  const ship = useRef<Group>(null);
  const body = useRef<Group>(null);
  const flameL = useRef<Mesh>(null);
  const flameR = useRef<Mesh>(null);
  const navWhite = useRef<Mesh>(null);
  const rimLights = useRef<(Mesh | null)[]>([]);
  const next = useRef(new Vector3());
  const lookAt = useRef(new Vector3());
  const prevFwd = useRef(new Vector3(0, 0, 1));
  const rollV = useRef(0);
  const pitchV = useRef(0);
  const elapsed = useRef(0);          // seconds since this journey began
  const arrived = useRef(false);       // true once we reach B → switch to orbiting it
  const orbitAngle = useRef(0);
  const orbTarget = useRef(new Vector3());

  useEffect(() => {
    solarRefs.shipActive = true;
    return () => { solarRefs.shipActive = false; };
  }, []);

  // Restart the flight clock whenever a new journey begins (mode flip or endpoint change),
  // so the ship always departs from A and travels continuously to B.
  useEffect(() => {
    if (mode === 'journey') { elapsed.current = 0; arrived.current = false; }
  }, [mode, sel[0], sel[1]]);

  useFrame((state, dt) => {
    if (mode === 'journey') {
      const a = solarRefs.bodyPos[sel[0]];
      const b = solarRefs.bodyPos[sel[1]];
      if (a && b) {
        elapsed.current += dt;
        const tt = Math.min(1, elapsed.current / TRAVEL_S);
        if (tt < 1) {
          // TRAVEL: ease along the upward-bowed arc, audio-independent so it never stalls.
          // Remap into (0.1 … 0.9): A/B are planet CENTRES, so a true 0/1 would bury the
          // first-person camera inside the planet — stay lifted off both ends.
          const s = tt * tt * (3 - 2 * tt); // smoothstep
          const p = 0.1 + 0.8 * s;
          journeyPoint(a, b, p, solarRefs.shipPos);
          journeyPoint(a, b, Math.min(0.92, p + 0.02), next.current);
          solarRefs.shipForward.copy(next.current).sub(solarRefs.shipPos).normalize();
          if (solarRefs.shipForward.lengthSq() < 1e-4) solarRefs.shipForward.set(0, 0, 1);
        } else {
          // ARRIVED: ease into a gentle circular orbit around the destination planet.
          // Seed the angle from the current bearing so it curves in smoothly (no pop).
          const size = bodyByHex(sel[1])?.size ?? 0.5;
          const r = size * 4 + 2;
          if (!arrived.current) {
            arrived.current = true;
            orbitAngle.current = Math.atan2(solarRefs.shipPos.z - b.z, solarRefs.shipPos.x - b.x);
          }
          orbitAngle.current += dt * ORBIT_SPEED;
          const ang = orbitAngle.current;
          orbTarget.current.set(b.x + Math.cos(ang) * r, b.y + size * 0.6, b.z + Math.sin(ang) * r);
          solarRefs.shipPos.lerp(orbTarget.current, Math.min(1, dt * 1.5));
          solarRefs.shipForward.set(-Math.sin(ang), 0, Math.cos(ang)).normalize(); // orbit tangent
        }
      }
    }
    if (ship.current) {
      ship.current.position.copy(solarRefs.shipPos);
      lookAt.current.copy(solarRefs.shipPos).add(solarRefs.shipForward);
      ship.current.lookAt(lookAt.current); // -Z faces travel
      // In first-person we sit INSIDE the hull → hide the exterior so it doesn't fill the
      // view; it's only shown during the third-person reveal. (useFrame still runs, so the
      // journey path / shipPos keep updating while hidden.)
      ship.current.visible = !solarRefs.cockpitView;
    }
    // bank into turns: signed yaw change of the forward vector → roll the body. Idle bank
    // breathing (added below) keeps it gently rocking when flying straight.
    const turn = prevFwd.current.x * solarRefs.shipForward.z - prevFwd.current.z * solarRefs.shipForward.x;
    const idleBank = solarRefs.reducedMotion ? 0 : Math.sin(state.clock.elapsedTime * 0.3) * 0.05;
    rollV.current += (Math.max(-0.6, Math.min(0.6, turn * 40)) + idleBank - rollV.current) * Math.min(1, dt * 3);
    // lean into a climb/dive: nose tips up as the ship rises along the bowed arc, down as it falls
    const pitchTarget = solarRefs.reducedMotion ? 0 : Math.max(-0.4, Math.min(0.4, -solarRefs.shipForward.y * 0.8));
    pitchV.current += (pitchTarget - pitchV.current) * Math.min(1, dt * 3);
    prevFwd.current.copy(solarRefs.shipForward);
    if (body.current) {
      body.current.rotation.z = solarRefs.reducedMotion ? 0 : rollV.current;
      body.current.rotation.x = pitchV.current;
      // hull micro-vibration (engine idle) — two incommensurate high freqs, sub-perceptible,
      // scaled by audio energy. Off under reduced-motion.
      const tt = state.clock.elapsedTime;
      const vib = solarRefs.reducedMotion ? 0
        : (Math.sin(tt * 31) * 0.004 + Math.sin(tt * 44.7) * 0.0025) * (1 + engine.features.rms);
      body.current.position.y = vib;
    }

    // engine flames pulse with the bass; white dome light strobes; rim lights pulse with rms
    const pulse = 0.7 + engine.features.bass * 1.6;
    const tt = state.clock.elapsedTime;
    const flick = solarRefs.reducedMotion ? 1 : 0.85 + 0.15 * Math.sin(tt * 23);
    if (flameL.current) {
      flameL.current.scale.set(1, pulse, 1);
      (flameL.current.material as { opacity?: number }).opacity = 0.85 * flick;
    }
    if (flameR.current) {
      flameR.current.scale.set(1, pulse, 1);
      (flameR.current.material as { opacity?: number }).opacity = 0.85 * (solarRefs.reducedMotion ? 1 : 0.85 + 0.15 * Math.sin(tt * 23 + 1.7));
    }
    if (navWhite.current) {
      // steady glow under reduced-motion (blinking is a motion trigger), else a smooth (no-pop)
      // strobe pulse instead of the old hard on/off gate.
      const strobe = solarRefs.reducedMotion ? 1.4 : 0.2 + 2.8 * Math.pow(0.5 + 0.5 * Math.sin(tt * 5.2), 8);
      (navWhite.current.material as { emissiveIntensity?: number }).emissiveIntensity = strobe;
    }
    const rimBase = 0.8 + engine.features.rms * 2.2;
    rimLights.current.forEach((m, i) => {
      if (!m) return;
      // travelling "chase" along the spine so there's motion even with no audio
      const chase = solarRefs.reducedMotion ? 0 : 0.6 * Math.max(0, Math.sin(tt * 2 - i * 0.6));
      (m.material as MeshStandardMaterial).emissiveIntensity = rimBase + chase;
    });
  });

  return (
    <group ref={ship} scale={0.8}>
      <group ref={body}>
        <ShipModel tier={tier} flameL={flameL} flameR={flameR} navWhite={navWhite} rimLights={rimLights} />
      </group>
    </group>
  );
}
