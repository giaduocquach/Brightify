import { type RefObject, useMemo } from 'react';
import { Outlines } from '@react-three/drei';
import { AdditiveBlending, type Mesh } from 'three';
import { useStore } from '../../state/store';
import { vaToColor } from '../va';
import { glowTexture } from './glow';
import { toonRamp, OUTLINE } from './toon';
import type { DeviceTier } from './deviceTier';

// A cute cel-shaded TRAVEL POD: a rounded white capsule, a glass canopy bubble, a ring of
// running lights + an equator seam that glow in the now-playing MOOD colour, and twin rear
// engine plumes. Two-colour palette: white body + steel structure + mood glow — matching the
// music-robot. Toon-shaded + a single ink outline on the body.
//
// Presentational: the parent (Spaceship / BoardingSequence) owns the useFrame driving the
// forwarded refs — flames pulse with bass, nav strobes, running lights pulse/chase with rms.
// The mood trim colour is recomputed only when the current song changes (cheap re-render).

const BODY = '#eef1f7';   // white
const STEEL = '#9aa3b8';  // neutral structure
// Widest body radius (model units). The boarding tractor beam keys off this (BoardingSequence).
export const SHIP_RADIUS = 0.78;

const RUN = Array.from({ length: 8 }, (_, i) => (i * Math.PI * 2) / 8);

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
  // Trim/lights glow in the playing song's mood colour (cyan fallback when nothing plays).
  const current = useStore((s) => s.current);
  const trim = useMemo(
    () => (current ? vaToColor(current.valence, current.arousal) : undefined),
    [current],
  );
  const glow = trim ?? '#67e8f9';

  return (
    <group>
      {/* ── rounded white pod body (widest radius = SHIP_RADIUS) ── */}
      <mesh scale={[1.3, 1.15, 1.3]}>
        <sphereGeometry args={[0.6, 40, 32]} />
        <meshToonMaterial color={BODY} gradientMap={ramp} />
        <Outlines {...OUTLINE} />
      </mesh>
      {/* belly skid (steel) */}
      <mesh position={[0, -0.52, 0]}>
        <cylinderGeometry args={[0.32, 0.46, 0.14, 28]} />
        <meshToonMaterial color={STEEL} gradientMap={ramp} />
      </mesh>

      {/* ── glass canopy bubble on the upper front (the pilot dome) ── */}
      <mesh position={[0, 0.2, 0.3]}>
        <sphereGeometry args={[0.32, 28, 24]} />
        <meshStandardMaterial color="#dcecff" transparent opacity={0.5} metalness={0.1} roughness={0.05} depthWrite={false} />
      </mesh>
      {/* canopy rim (mood) */}
      <mesh position={[0, 0.2, 0.3]} scale={[1, 1, 0.6]}>
        <torusGeometry args={[0.31, 0.02, 10, 28]} />
        <meshStandardMaterial color={glow} emissive={glow} emissiveIntensity={1.2} toneMapped={false} />
      </mesh>

      {/* ── glowing equator seam (mood) ── */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[SHIP_RADIUS, 0.022, 12, 56]} />
        <meshStandardMaterial color={glow} emissive={glow} emissiveIntensity={0.9} toneMapped={false} />
      </mesh>

      {/* ── 8 running lights around the equator (pulse/chase with rms via the rimLights ref) ── */}
      {RUN.map((a, i) => (
        <mesh key={i} ref={(el) => { if (rimLights) rimLights.current[i] = el; }}
          position={[Math.cos(a) * SHIP_RADIUS, 0, Math.sin(a) * SHIP_RADIUS]}>
          <sphereGeometry args={[0.04, 10, 10]} />
          <meshStandardMaterial color={glow} emissive={glow} emissiveIntensity={1.8} toneMapped={false} />
        </mesh>
      ))}

      {/* ── white strobe beacon on the canopy crown ── */}
      <mesh ref={navWhite} position={[0, 0.52, 0.18]}>
        <sphereGeometry args={[0.04, 10, 10]} />
        <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.2} toneMapped={false} />
      </mesh>

      {/* ── twin rear engine nacelles + plumes (flames pulse with bass) ── */}
      <mesh position={[0.26, -0.2, 0.5]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.1, 0.12, 0.18, 16]} />
        <meshToonMaterial color={STEEL} gradientMap={ramp} />
      </mesh>
      <mesh position={[-0.26, -0.2, 0.5]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.1, 0.12, 0.18, 16]} />
        <meshToonMaterial color={STEEL} gradientMap={ramp} />
      </mesh>
      <mesh ref={flameL} position={[0.26, -0.2, 0.66]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.09, 0.5, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={flameR} position={[-0.26, -0.2, 0.66]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.09, 0.5, 16]} />
        <meshBasicMaterial color="#9fdcff" transparent opacity={0.85} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {tier === 'high' && (
        <>
          <sprite position={[0.26, -0.2, 0.62]} scale={0.5}>
            <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
          <sprite position={[-0.26, -0.2, 0.62]} scale={0.5}>
            <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.95} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
        </>
      )}
      <pointLight position={[0, 0.1, 0]} intensity={2.4} distance={3} color="#cfe3ff" />
    </group>
  );
}
