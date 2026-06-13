import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, DoubleSide, Group, type Mesh, Vector3 } from 'three';
import { Outlines, Sparkles } from '@react-three/drei';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { journeyPoint } from './journeyPath';
import { starShape } from './shapes';
import { toonRamp, OUTLINE } from './toon';

const GOLD = '#ffcd00';

// A cel-shaded, rounded craft (open cockpit under a glass canopy, stubby wings, twin
// engines) in Vietnamese dress: a red/gold hull stripe + a "mặt trống đồng" (bronze-drum)
// emblem on the bow. Lively in flight: engine flames pulse with the bass, nav lights
// blink (red port / green starboard / white strobe), and the hull banks into its turns.
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
  const tex = glowTexture();
  const next = useRef(new Vector3());
  const lookAt = useRef(new Vector3());
  const prevFwd = useRef(new Vector3(0, 0, 1));
  const rollV = useRef(0);
  const drumStar = useMemo(() => starShape(0.12, 0.05), []);
  const drumRings = useMemo(() => [0.1, 0.15, 0.2], []);

  useEffect(() => {
    solarRefs.shipActive = true;
    return () => { solarRefs.shipActive = false; };
  }, []);

  useFrame((state, dt) => {
    if (mode === 'journey') {
      const a = solarRefs.bodyPos[sel[0]];
      const b = solarRefs.bodyPos[sel[1]];
      if (a && b) {
        const st = useStore.getState();
        const { time, duration } = engine.progress(); // live playhead → smooth motion
        const n = st.queue.length || 1;
        const frac = duration > 0 ? time / duration : 0;
        const idx = Math.max(0, st.index);
        // remap into (0.1 … 0.9): endpoints A/B are planet CENTRES, so a true 0/1 would
        // bury the first-person camera inside the planet. Stay lifted off both, along the
        // upward-bowed arc, so we depart from above the surface and arrive above it.
        const p = 0.1 + 0.8 * Math.min(1, (idx + frac) / n);
        journeyPoint(a, b, p, solarRefs.shipPos);
        journeyPoint(a, b, Math.min(0.92, p + 0.02), next.current);
        solarRefs.shipForward.copy(next.current).sub(solarRefs.shipPos).normalize();
        if (solarRefs.shipForward.lengthSq() < 1e-4) solarRefs.shipForward.set(0, 0, 1);
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
    // bank into turns: signed yaw change of the forward vector → roll the body
    const turn = prevFwd.current.x * solarRefs.shipForward.z - prevFwd.current.z * solarRefs.shipForward.x;
    rollV.current += (Math.max(-0.6, Math.min(0.6, turn * 40)) - rollV.current) * Math.min(1, dt * 3);
    prevFwd.current.copy(solarRefs.shipForward);
    if (body.current) body.current.rotation.z = rollV.current;

    // engine flames pulse with the bass; white tail light strobes
    const pulse = 0.7 + engine.features.bass * 1.6;
    if (flameL.current) flameL.current.scale.set(1, pulse, 1);
    if (flameR.current) flameR.current.scale.set(1, pulse, 1);
    if (navWhite.current) {
      const strobe = (state.clock.elapsedTime % 1.2) < 0.1 ? 3 : 0.2;
      (navWhite.current.material as { emissiveIntensity?: number }).emissiveIntensity = strobe;
    }
  });

  return (
    <group ref={ship} scale={1.25}>
      <group ref={body}>
        {/* round bubble hull (the pilot sits in this; open on top) */}
        <mesh position={[0, -0.14, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <capsuleGeometry args={[0.55, 0.26, 12, 24]} />
          <meshToonMaterial color="#dde3ef" gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* short rounded nose (front, -Z) */}
        <mesh position={[0, -0.1, -0.62]} rotation={[-Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.3, 0.34, 28]} />
          <meshToonMaterial color="#c3ccde" gradientMap={ramp} />
        </mesh>
        <mesh position={[0, -0.1, -0.78]}>
          <sphereGeometry args={[0.13, 16, 16]} />
          <meshToonMaterial color="#c3ccde" gradientMap={ramp} />
        </mesh>
        {/* VN red/gold stripe around the hull */}
        <mesh position={[0, -0.14, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.56, 0.055, 10, 28]} />
          <meshToonMaterial color="#da251d" gradientMap={ramp} emissive="#da251d" emissiveIntensity={0.25} />
        </mesh>

        {/* ── "mặt trống đồng" emblem on the bow: bronze plate + gold rings + star ── */}
        <group position={[0, 0.06, -0.42]} rotation={[-1.15, 0, 0]}>
          <mesh>
            <cylinderGeometry args={[0.24, 0.24, 0.03, 32]} />
            <meshToonMaterial color="#c98a3a" gradientMap={ramp} emissive="#3a230a" emissiveIntensity={0.4} />
          </mesh>
          {drumRings.map((r, i) => (
            <mesh key={i} position={[0, 0.02, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[r, 0.008, 8, 40]} />
              <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.5} />
            </mesh>
          ))}
          <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <shapeGeometry args={[drumStar]} />
            <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.9} side={DoubleSide} />
          </mesh>
        </group>

        {/* big round glass bubble canopy over the pilot */}
        <mesh position={[0, 0.16, -0.02]}>
          <sphereGeometry args={[0.56, 24, 18, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
          <meshStandardMaterial color="#bfe3ff" transparent opacity={0.18} metalness={0.1} roughness={0.05} depthWrite={false} />
        </mesh>
        {/* small stubby rounded wings */}
        <mesh position={[0.52, -0.16, 0.16]} rotation={[0, -0.4, Math.PI / 2]}>
          <capsuleGeometry args={[0.055, 0.28, 6, 12]} />
          <meshToonMaterial color="#aab9da" gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        <mesh position={[-0.52, -0.16, 0.16]} rotation={[0, 0.4, Math.PI / 2]}>
          <capsuleGeometry args={[0.055, 0.28, 6, 12]} />
          <meshToonMaterial color="#aab9da" gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* tail fin */}
        <mesh position={[0, 0.18, 0.5]} rotation={[0.4, 0, 0]}>
          <boxGeometry args={[0.05, 0.3, 0.26]} />
          <meshToonMaterial color={GOLD} gradientMap={ramp} emissive={GOLD} emissiveIntensity={0.2} />
        </mesh>

        {/* nav lights: red port / green starboard / white tail strobe */}
        <mesh position={[0.78, -0.16, 0.2]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#ff2d2d" emissive="#ff2d2d" emissiveIntensity={2.4} />
        </mesh>
        <mesh position={[-0.78, -0.16, 0.2]}>
          <sphereGeometry args={[0.05, 10, 10]} />
          <meshStandardMaterial color="#39ff7a" emissive="#39ff7a" emissiveIntensity={2.4} />
        </mesh>
        <mesh ref={navWhite} position={[0, 0.34, 0.58]}>
          <sphereGeometry args={[0.045, 10, 10]} />
          <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.2} />
        </mesh>

        {/* twin engine flames (back, +Z) — pulse with bass */}
        <mesh ref={flameL} position={[0.18, -0.14, 0.78]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.12, 0.5, 16]} />
          <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <mesh ref={flameR} position={[-0.18, -0.14, 0.78]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.12, 0.5, 16]} />
          <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <sprite position={[0.18, -0.14, 0.62]} scale={0.55}>
          <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
        </sprite>
        <sprite position={[-0.18, -0.14, 0.62]} scale={0.55}>
          <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
        </sprite>
        <pointLight position={[0, 0.1, 0]} intensity={2.6} distance={3} color="#bfe3ff" />
      </group>

      {/* engine spark wake */}
      <Sparkles count={20} scale={[0.5, 0.5, 1.2]} position={[0, -0.14, 1.0]}
        size={2.4} speed={1.2} color="#9fdcff" opacity={0.7} />
    </group>
  );
}
