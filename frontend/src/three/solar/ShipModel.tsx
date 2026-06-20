import { type RefObject } from 'react';
import { AdditiveBlending, DoubleSide, type Mesh } from 'three';
import { glowTexture } from './glow';
import { starShape } from './shapes';
import type { DeviceTier } from './deviceTier';

// Sleek, functional exploration craft (replaces the old UFO saucer). Procedural PBR hull so it
// reflects the scene env map and matches the photoreal planets. The nose points toward LOCAL -Z
// (the parent does `ship.lookAt(pos + forward)`, which aims -Z down the travel direction).
//
// Presentational only: the parent (Spaceship / BoardingSequence) owns the useFrame that animates
// the forwarded refs — flames pulse with bass, nav strobes, rim/running lights pulse with rms.
// Refs are optional so the boarding saucer (which only drives rim lights) can reuse the model.

const HULL = '#c7ccd6';
const HULL_D = '#8a909c';
const DARK = '#2b3344';
const GOLD = '#ffcd00';

interface ShipModelProps {
  tier: DeviceTier;
  flameL?: RefObject<Mesh | null>;
  flameR?: RefObject<Mesh | null>;
  navWhite?: RefObject<Mesh | null>;
  rimLights?: RefObject<(Mesh | null)[]>;
}

export default function ShipModel({ tier, flameL, flameR, navWhite, rimLights }: ShipModelProps) {
  const tex = glowTexture();
  const high = tier === 'high';
  const emblem = starShape(0.03, 0.013);
  // running-light positions along the top spine (z from nose to tail)
  const runN = high ? 8 : 5;
  const runZ = Array.from({ length: runN }, (_, i) => -0.45 + (i / (runN - 1)) * 0.9);

  return (
    <group>
      {/* ── fuselage: elongated capsule along Z, nose at -Z ── */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <capsuleGeometry args={[0.26, 0.85, 12, 24]} />
        <meshStandardMaterial color={HULL} metalness={0.85} roughness={0.35} envMapIntensity={0.5} />
      </mesh>
      {/* belly fairing / keel for a less tube-like silhouette */}
      <mesh position={[0, -0.16, 0.05]} rotation={[Math.PI / 2, 0, 0]}>
        <capsuleGeometry args={[0.14, 0.6, 8, 18]} />
        <meshStandardMaterial color={HULL_D} metalness={0.7} roughness={0.45} envMapIntensity={0.45} />
      </mesh>
      {/* nose sensor tip */}
      <mesh position={[0, 0, -0.72]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.1, 0.22, 20]} />
        <meshStandardMaterial color={HULL_D} metalness={0.6} roughness={0.4} />
      </mesh>

      {/* ── cockpit canopy (tinted glass) near the nose, on top ── */}
      <mesh position={[0, 0.14, -0.34]} rotation={[Math.PI / 2 - 0.35, 0, 0]}>
        <sphereGeometry args={[0.2, 24, 16, 0, Math.PI * 2, 0, 1.1]} />
        <meshStandardMaterial color="#bfe3ff" transparent opacity={0.55} metalness={0.2} roughness={0.08}
          envMapIntensity={1.0} depthWrite={false} side={DoubleSide} />
      </mesh>

      {/* ── twin engine nacelles on ±X (toward the tail) ── */}
      {[0.34, -0.34].map((x, i) => (
        <group key={i} position={[x, -0.02, 0.18]}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.11, 0.12, 0.62, 20]} />
            <meshStandardMaterial color={HULL_D} metalness={0.9} roughness={0.3} envMapIntensity={0.5} />
          </mesh>
          {/* engine bell at the rear */}
          <mesh position={[0, 0, 0.33]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.13, 0.09, 0.1, 20]} />
            <meshStandardMaterial color={DARK} metalness={0.8} roughness={0.4} />
          </mesh>
          {/* pylon joining nacelle to fuselage */}
          <mesh position={[x > 0 ? -0.08 : 0.08, 0.02, 0]}>
            <boxGeometry args={[0.12, 0.04, 0.34]} />
            <meshStandardMaterial color={HULL_D} metalness={0.8} roughness={0.4} />
          </mesh>
        </group>
      ))}

      {/* exhaust plumes (height along Y → scale.y pulses the length; rotated to face +Z = aft) */}
      <mesh ref={flameL} position={[0.34, -0.02, 0.58]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.1, 0.42, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={flameR} position={[-0.34, -0.02, 0.58]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.1, 0.42, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <sprite position={[0.34, -0.02, 0.52]} scale={0.4}>
        <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.9} blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite position={[-0.34, -0.02, 0.52]} scale={0.4}>
        <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.9} blending={AdditiveBlending} depthWrite={false} />
      </sprite>

      {/* ── swept tail fin (silhouette) ── */}
      <mesh position={[0, 0.16, 0.5]} rotation={[0.5, 0, 0]}>
        <boxGeometry args={[0.04, 0.26, 0.22]} />
        <meshStandardMaterial color={HULL_D} metalness={0.8} roughness={0.4} />
      </mesh>

      {/* ── nav lights: red port (+X) / green starboard (-X) / white spine strobe ── */}
      <mesh position={[0.5, -0.02, 0.2]}>
        <sphereGeometry args={[0.04, 10, 10]} />
        <meshStandardMaterial color="#ff2d2d" emissive="#ff2d2d" emissiveIntensity={2.4} toneMapped={false} />
      </mesh>
      <mesh position={[-0.5, -0.02, 0.2]}>
        <sphereGeometry args={[0.04, 10, 10]} />
        <meshStandardMaterial color="#39ff7a" emissive="#39ff7a" emissiveIntensity={0.9} toneMapped={false} />
      </mesh>
      <mesh ref={navWhite} position={[0, 0.24, 0.0]}>
        <sphereGeometry args={[0.038, 10, 10]} />
        <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.2} toneMapped={false} />
      </mesh>

      {/* ── spine running lights (pulse with rms; chase added in the add-life pass) ── */}
      {runZ.map((z, i) => (
        <mesh key={i} ref={(el) => { if (rimLights) rimLights.current[i] = el; }} position={[0, 0.18, z]}>
          <sphereGeometry args={[0.028, 8, 8]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={1.6} toneMapped={false} />
        </mesh>
      ))}

      {/* ── subtle Đông Sơn flank emblem (gold rings + tiny star), facing +X ── */}
      <group position={[0.265, 0.02, 0.02]} rotation={[0, Math.PI / 2, 0]}>
        <mesh><torusGeometry args={[0.07, 0.008, 8, 28]} /><meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.25} metalness={0.7} roughness={0.4} /></mesh>
        <mesh><torusGeometry args={[0.045, 0.006, 8, 24]} /><meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.2} metalness={0.7} roughness={0.4} /></mesh>
        <mesh><shapeGeometry args={[emblem]} /><meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.3} metalness={0.7} roughness={0.4} side={DoubleSide} /></mesh>
      </group>

      {/* hull panel accents (high tier) */}
      {high && (
        <>
          <mesh position={[0, 0.2, -0.05]} rotation={[Math.PI / 2, 0, 0]}>
            <boxGeometry args={[0.18, 0.5, 0.02]} />
            <meshStandardMaterial color={HULL_D} metalness={0.85} roughness={0.3} />
          </mesh>
        </>
      )}

      {/* warm cabin fill so the canopy reads as lit */}
      <pointLight position={[0, 0.1, -0.2]} intensity={1.6} distance={2.6} color="#bfe3ff" />
    </group>
  );
}
