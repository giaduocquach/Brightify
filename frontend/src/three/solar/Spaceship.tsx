import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, Group, type Mesh, MeshStandardMaterial, Vector3 } from 'three';
import { Outlines } from '@react-three/drei';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { journeyPoint } from './journeyPath';
import { bodyByHex } from './bodies';
import { toonRamp, OUTLINE } from './toon';

const TRAVEL_S = 30;       // seconds to fly A → B — continuous, audio-independent
const ORBIT_SPEED = 0.18;  // rad/s of the gentle loop once we arrive at the destination

// A cel-shaded UFO flying saucer: flat disc body, blue glass dome, 8 gold rim lights
// that pulse with the music, twin thruster cones underneath. Banks into turns.
// Mostly seen during the ~2s reveal before the camera dives into the cockpit.
export default function Spaceship() {
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const ramp = toonRamp();
  const ship = useRef<Group>(null);
  const body = useRef<Group>(null);
  const flameL = useRef<Mesh>(null);
  const flameR = useRef<Mesh>(null);
  const navWhite = useRef<Mesh>(null);
  const rimLights = useRef<(Mesh | null)[]>([]);
  const tex = glowTexture();
  const next = useRef(new Vector3());
  const lookAt = useRef(new Vector3());
  const prevFwd = useRef(new Vector3(0, 0, 1));
  const rollV = useRef(0);
  const elapsed = useRef(0);          // seconds since this journey began
  const arrived = useRef(false);       // true once we reach B → switch to orbiting it
  const orbitAngle = useRef(0);
  const orbTarget = useRef(new Vector3());
  const rimAngles = useMemo(() => Array.from({ length: 8 }, (_, i) => i * Math.PI * 2 / 8), []);

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
    // bank into turns: signed yaw change of the forward vector → roll the body (level under reduced-motion)
    const turn = prevFwd.current.x * solarRefs.shipForward.z - prevFwd.current.z * solarRefs.shipForward.x;
    rollV.current += (Math.max(-0.6, Math.min(0.6, turn * 40)) - rollV.current) * Math.min(1, dt * 3);
    prevFwd.current.copy(solarRefs.shipForward);
    if (body.current) body.current.rotation.z = solarRefs.reducedMotion ? 0 : rollV.current;

    // engine flames pulse with the bass; white dome light strobes; rim lights pulse with rms
    const pulse = 0.7 + engine.features.bass * 1.6;
    if (flameL.current) flameL.current.scale.set(1, pulse, 1);
    if (flameR.current) flameR.current.scale.set(1, pulse, 1);
    if (navWhite.current) {
      // steady glow under reduced-motion (blinking is a motion trigger), else the nav strobe
      const strobe = solarRefs.reducedMotion ? 1.4 : ((state.clock.elapsedTime % 1.2) < 0.1 ? 3 : 0.2);
      (navWhite.current.material as { emissiveIntensity?: number }).emissiveIntensity = strobe;
    }
    const rimPulse = 0.8 + engine.features.rms * 2.2;
    rimLights.current.forEach((m) => {
      if (m) (m.material as MeshStandardMaterial).emissiveIntensity = rimPulse;
    });
  });

  return (
    <group ref={ship} scale={0.8}>
      <group ref={body}>
        {/* ── main disc — slightly tapered for saucer silhouette ── */}
        <mesh>
          <cylinderGeometry args={[0.85, 0.75, 0.18, 48]} />
          <meshToonMaterial color="#dde3ef" gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>

        {/* ── dome (upper half-sphere) — translucent blue glass ── */}
        <mesh position={[0, 0.09, 0]}>
          <sphereGeometry args={[0.52, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.5]} />
          <meshStandardMaterial color="#bfe3ff" transparent opacity={0.65} metalness={0.1} roughness={0.05} depthWrite={false} />
        </mesh>

        {/* ── 8 gold rim lights equidistant around disc edge ── */}
        {rimAngles.map((a, i) => (
          <mesh key={i} ref={(el) => { rimLights.current[i] = el; }}
            position={[Math.cos(a) * 0.80, 0, Math.sin(a) * 0.80]}>
            <sphereGeometry args={[0.045, 10, 10]} />
            <meshStandardMaterial color="#ffcd00" emissive="#ffcd00" emissiveIntensity={1.8} />
          </mesh>
        ))}

        {/* ── underside cone indent at bottom center ── */}
        <mesh position={[0, -0.13, 0]} rotation={[Math.PI, 0, 0]}>
          <coneGeometry args={[0.22, 0.12, 24]} />
          <meshToonMaterial color="#c3ccde" gradientMap={ramp} />
        </mesh>

        {/* nav lights: red port (+X) / green starboard (-X) / white strobe on dome */}
        <mesh position={[0.92, 0, 0]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#ff2d2d" emissive="#ff2d2d" emissiveIntensity={2.4} />
        </mesh>
        <mesh position={[-0.92, 0, 0]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#39ff7a" emissive="#39ff7a" emissiveIntensity={0.9} />
        </mesh>
        <mesh ref={navWhite} position={[0, 0.65, 0]}>
          <sphereGeometry args={[0.045, 10, 10]} />
          <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.2} />
        </mesh>

        {/* ── twin thruster cones under the disc — pulse with bass ── */}
        <mesh ref={flameL} position={[0.32, -0.22, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.12, 0.5, 16]} />
          <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <mesh ref={flameR} position={[-0.32, -0.22, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.12, 0.5, 16]} />
          <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <sprite position={[0.32, -0.16, 0]} scale={0.55}>
          <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
        </sprite>
        <sprite position={[-0.32, -0.16, 0]} scale={0.55}>
          <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
        </sprite>
        <pointLight position={[0, 0.1, 0]} intensity={2.6} distance={3} color="#bfe3ff" />
      </group>
    </group>
  );
}
