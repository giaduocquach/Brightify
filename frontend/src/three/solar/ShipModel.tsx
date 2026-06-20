import { type RefObject } from 'react';
import { Outlines } from '@react-three/drei';
import { AdditiveBlending, type Mesh } from 'three';
import { glowTexture } from './glow';
import { toonRamp, OUTLINE } from './toon';
import type { DeviceTier } from './deviceTier';

// The cute cel-shaded UFO saucer: flat tapered disc, blue glass dome, a ring of 8 gold rim
// lights, an underside cone, red/green/white nav lights and twin thruster cones. Toon-shaded
// + ink outline so it matches the chibi astronaut.
//
// Presentational only: the parent (Spaceship / BoardingSequence) owns the useFrame that drives
// the forwarded refs — flames pulse with bass, nav strobes, rim lights pulse/chase with rms.
// Refs are optional so the boarding saucer (which only drives rim lights) can reuse the model.

const RIM = Array.from({ length: 8 }, (_, i) => (i * Math.PI * 2) / 8);

interface ShipModelProps {
  tier: DeviceTier;
  flameL?: RefObject<Mesh | null>;
  flameR?: RefObject<Mesh | null>;
  navWhite?: RefObject<Mesh | null>;
  rimLights?: RefObject<(Mesh | null)[]>;
}

export default function ShipModel({ tier, flameL, flameR, navWhite, rimLights }: ShipModelProps) {
  const ramp = toonRamp();
  const tex = glowTexture();

  return (
    <group>
      {/* ── main disc — slightly tapered saucer silhouette ── */}
      <mesh>
        <cylinderGeometry args={[0.85, 0.75, 0.18, 48]} />
        <meshToonMaterial color="#dde3ef" gradientMap={ramp} />
        <Outlines {...OUTLINE} />
      </mesh>

      {/* ── translucent blue glass dome ── */}
      <mesh position={[0, 0.09, 0]}>
        <sphereGeometry args={[0.52, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.5]} />
        <meshStandardMaterial color="#bfe3ff" transparent opacity={0.65} metalness={0.1} roughness={0.05} depthWrite={false} />
      </mesh>

      {/* ── 8 gold rim lights (pulse/chase with rms) ── */}
      {RIM.map((a, i) => (
        <mesh key={i} ref={(el) => { if (rimLights) rimLights.current[i] = el; }}
          position={[Math.cos(a) * 0.80, 0, Math.sin(a) * 0.80]}>
          <sphereGeometry args={[0.045, 10, 10]} />
          <meshStandardMaterial color="#ffcd00" emissive="#ffcd00" emissiveIntensity={1.8} toneMapped={false} />
        </mesh>
      ))}

      {/* ── underside cone indent ── */}
      <mesh position={[0, -0.13, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.22, 0.12, 24]} />
        <meshToonMaterial color="#c3ccde" gradientMap={ramp} />
      </mesh>

      {/* ── nav lights: red port / green starboard / white dome strobe ── */}
      <mesh position={[0.92, 0, 0]}>
        <sphereGeometry args={[0.05, 10, 10]} />
        <meshStandardMaterial color="#ff2d2d" emissive="#ff2d2d" emissiveIntensity={2.4} toneMapped={false} />
      </mesh>
      <mesh position={[-0.92, 0, 0]}>
        <sphereGeometry args={[0.05, 10, 10]} />
        <meshStandardMaterial color="#39ff7a" emissive="#39ff7a" emissiveIntensity={0.9} toneMapped={false} />
      </mesh>
      <mesh ref={navWhite} position={[0, 0.65, 0]}>
        <sphereGeometry args={[0.045, 10, 10]} />
        <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.2} toneMapped={false} />
      </mesh>

      {/* ── twin thruster cones (pulse with bass) ── */}
      <mesh ref={flameL} position={[0.32, -0.22, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.12, 0.5, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={flameR} position={[-0.32, -0.22, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.12, 0.5, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {tier === 'high' && (
        <>
          <sprite position={[0.32, -0.16, 0]} scale={0.55}>
            <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
          <sprite position={[-0.32, -0.16, 0]} scale={0.55}>
            <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
        </>
      )}
      <pointLight position={[0, 0.1, 0]} intensity={2.6} distance={3} color="#bfe3ff" />
    </group>
  );
}
