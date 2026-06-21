import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, BufferAttribute, DoubleSide, Group, Mesh, MeshStandardMaterial, Quaternion, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';
import { glowTexture } from './glow';
import { useDeviceTier } from './deviceTier';
import ShipModel, { SHIP_RADIUS } from './ShipModel';

const N_PARTICLES = 64;
const UP = new Vector3(0, 1, 0);
const RAD = new Vector3();
const SAUCER = new Vector3();
const Q = new Quaternion();

// Boarding: a UFO saucer descends and hovers directly above the (frozen) astronaut along
// the planet's local "up" (radial), fires a teal tractor beam, and streams particles up
// the column. `boardingLift` (eased 0→1) + `boardingTarget` are written to solarRefs so
// Astronaut.tsx draws the runner up into the saucer. Sizes are proportional to the
// astronaut, so the craft reads as a believable vehicle rather than dwarfing the planet.
export default function BoardingSequence() {
  const sel = useStore((s) => s.selectedColors);
  const tier = useDeviceTier();
  const tex = glowTexture();

  const saucerRef = useRef<Group>(null);
  const saucerSpin = useRef<Group>(null);
  const beamRef = useRef<Group>(null);
  const beamMat = useRef<Mesh>(null);
  const posAttr = useRef<BufferAttribute>(null);
  const elapsed = useRef(0);
  const rimLights = useRef<(Mesh | null)[]>([]);

  const size = bodyByHex(sel[0])?.size ?? 0.5;
  // Astronaut world height ≈ size*0.18; a UFO ~5-6× that reads as a craft (with a floor so
  // it stays visible above tiny bodies). Beam spans from the surface up to the saucer.
  const saucerScale = Math.max(0.4, size * 0.6);
  const beamH = Math.max(1.0, size * 2.5);
  const beamBaseR = saucerScale * SHIP_RADIUS * 0.9; // beam mouth matches the pod's widest radius

  const particleData = useMemo(() => new Float32Array(N_PARTICLES * 3), []);

  // Reset on mount (= boarding start). runnerPos is frozen by SurfaceRun during boarding.
  useEffect(() => {
    elapsed.current = 0;
    solarRefs.boardingLift = 0;
    for (let i = 0; i < N_PARTICLES; i++) {
      const a = i * 2.39996;
      const r = ((i * 37) % 10) / 10 * beamBaseR * 0.7;
      particleData[i * 3] = Math.cos(a) * r;
      particleData[i * 3 + 1] = (i / N_PARTICLES) * beamH; // spread along the column
      particleData[i * 3 + 2] = Math.sin(a) * r;
    }
    if (posAttr.current) posAttr.current.needsUpdate = true;
  }, [particleData, beamBaseR, beamH]);

  useFrame((_, dt) => {
    const center = solarRefs.bodyPos[sel[0]];
    if (!center) return;
    elapsed.current += dt;
    const t = elapsed.current;

    const base = solarRefs.runnerPos; // frozen surface point under the beam
    RAD.copy(base).sub(center);
    if (RAD.lengthSq() < 1e-6) RAD.set(0, 1, 0);
    RAD.normalize();
    Q.setFromUnitVectors(UP, RAD); // orient local +Y onto the planet's radial "up"

    SAUCER.copy(base).addScaledVector(RAD, beamH);

    // eased lift (smoothstep), starting after a short beat
    const raw = Math.max(0, Math.min(1, (t - 0.3) / 2.4));
    solarRefs.boardingLift = raw * raw * (3 - 2 * raw);
    // astronaut is drawn up to just under the saucer's underside
    solarRefs.boardingTarget.copy(base).addScaledVector(RAD, beamH - 0.2);

    if (saucerRef.current) {
      saucerRef.current.position.copy(SAUCER).addScaledVector(RAD, Math.sin(t * 1.8) * 0.08);
      saucerRef.current.quaternion.copy(Q);
    }
    if (saucerSpin.current) saucerSpin.current.rotation.y += dt * 0.5;

    if (beamRef.current) {
      beamRef.current.position.copy(base);
      beamRef.current.quaternion.copy(Q);
    }
    if (beamMat.current) {
      (beamMat.current.material as { opacity: number }).opacity = Math.min(0.34, (t / 0.5) * 0.34);
    }

    const rimPulse = 0.8 + (Math.sin(t * 6) * 0.5 + 0.5) * 1.4;
    rimLights.current.forEach((m) => {
      if (m) (m.material as MeshStandardMaterial).emissiveIntensity = rimPulse;
    });

    // particles rise up the beam's local +Y (beamRef is oriented to the radial)
    const speed = beamH * 0.5;
    for (let i = 0; i < N_PARTICLES; i++) {
      particleData[i * 3 + 1] += dt * speed;
      if (particleData[i * 3 + 1] > beamH - 0.05) particleData[i * 3 + 1] = 0;
    }
    if (posAttr.current) posAttr.current.needsUpdate = true;
  });

  return (
    <>
      {/* the same exploration craft (ShipModel) — oriented to the radial, spins about its own axis */}
      <group ref={saucerRef} scale={saucerScale}>
        <group ref={saucerSpin}>
          <ShipModel tier={tier} rimLights={rimLights} />
        </group>
        <pointLight position={[0, -0.4, 0]} intensity={1.6} distance={beamH + 3} color="#00eeff" />
      </group>

      {/* Tractor beam + particles — oriented along the radial, local +Y points up the column */}
      <group ref={beamRef}>
        <mesh ref={beamMat} position={[0, beamH / 2, 0]}>
          <coneGeometry args={[beamBaseR, beamH, 32, 1, true]} />
          <meshBasicMaterial color="#00eeff" transparent opacity={0} side={DoubleSide} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <points>
          <bufferGeometry>
            <bufferAttribute ref={posAttr} attach="attributes-position" args={[particleData, 3]} />
          </bufferGeometry>
          <pointsMaterial map={tex} color="#9af7ff" size={size * 0.12 + 0.06} transparent opacity={0.9}
            blending={AdditiveBlending} depthWrite={false} sizeAttenuation />
        </points>
      </group>
    </>
  );
}
