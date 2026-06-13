import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Outlines } from '@react-three/drei';
import { DoubleSide, Group, type Mesh } from 'three';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { starShape } from './shapes';
import { toonRamp, OUTLINE } from './toon';

const GOLD = '#ffcd00';
const METAL = '#3a4360';
const METAL_D = '#1e2640';

// First-person cockpit — kept deliberately OPEN: you look out through a clear canopy and
// see space across ~80% of the view. Only a slim dashboard sits along the very bottom,
// two thin struts hint at the corners, and a faint fresnel "glass" glows at the edges
// (so it reads as a canopy without blocking). The EQ gauges pulse with the music and a
// little gold-star charm sways. Attached to the camera so it always frames the view.
export default function CockpitInterior() {
  const camera = useThree((s) => s.camera);
  const ramp = toonRamp();
  const root = useRef<Group>(null);
  const charm = useRef<Group>(null);
  const bars = useRef<(Mesh | null)[]>([]);
  const drumStar = useMemo(() => starShape(0.04, 0.018), []);
  const barX = useMemo(() => [-0.16, -0.08, 0, 0.08, 0.16], []);

  useFrame((state) => {
    const g = root.current;
    if (!g) return;
    g.visible = solarRefs.cockpitView;
    if (!g.visible) return;

    g.position.copy(camera.position);
    g.quaternion.copy(camera.quaternion);

    const f = engine.features;
    const bands = [f.bass, (f.bass + f.rms) * 0.5, f.rms, (f.rms + f.treble) * 0.5, f.treble];
    bars.current.forEach((b, i) => { if (b) b.scale.y = 0.25 + Math.min(1, bands[i] * 2.4); });

    if (charm.current) {
      const t = state.clock.elapsedTime;
      charm.current.rotation.z = Math.sin(t * 2.2) * 0.18 + Math.min(0.4, solarRefs.shipSpeed * 0.05);
      charm.current.rotation.x = Math.sin(t * 1.7) * 0.1;
    }
  });

  return (
    <group ref={root}>
      {/* ── slim dashboard strip across the very bottom (tilted up to the pilot) ── */}
      <mesh position={[0, -0.46, -0.62]} rotation={[-0.62, 0, 0]}>
        <boxGeometry args={[1.0, 0.2, 0.06]} />
        <meshToonMaterial color={METAL_D} gradientMap={ramp} />
        <Outlines {...OUTLINE} />
      </mesh>
      <mesh position={[0, -0.38, -0.56]} rotation={[-0.62, 0, 0]}>
        <boxGeometry args={[1.0, 0.03, 0.1]} />
        <meshToonMaterial color="#da251d" gradientMap={ramp} emissive="#da251d" emissiveIntensity={0.3} />
      </mesh>
      {/* EQ gauge bars (music-reactive) */}
      {barX.map((x, i) => (
        <mesh key={i} ref={(el) => { bars.current[i] = el; }} position={[x, -0.43, -0.58]}>
          <boxGeometry args={[0.045, 0.1, 0.02]} />
          <meshStandardMaterial color="#7cf0ff" emissive="#7cf0ff" emissiveIntensity={1.6} />
        </mesh>
      ))}
      {/* a couple of glowing buttons + trống đồng motif */}
      {[-0.34, 0.34].map((x, i) => (
        <mesh key={i} position={[x, -0.47, -0.56]} rotation={[-0.62, 0, 0]}>
          <cylinderGeometry args={[0.022, 0.022, 0.018, 12]} />
          <meshStandardMaterial color={i ? '#ff5d6c' : '#5dff9b'} emissive={i ? '#ff5d6c' : '#5dff9b'} emissiveIntensity={1.8} />
        </mesh>
      ))}
      <mesh position={[0, -0.48, -0.6]} rotation={[-0.62, 0, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 0.012, 20]} />
        <meshToonMaterial color="#c98a3a" gradientMap={ramp} emissive="#3a230a" emissiveIntensity={0.4} />
      </mesh>

      {/* ── thin corner struts (just a hint of frame at the edges) ── */}
      <mesh position={[-0.52, -0.05, -0.6]} rotation={[0.15, 0, 0.5]}>
        <capsuleGeometry args={[0.015, 0.6, 6, 8]} />
        <meshToonMaterial color={METAL} gradientMap={ramp} />
      </mesh>
      <mesh position={[0.52, -0.05, -0.6]} rotation={[0.15, 0, -0.5]}>
        <capsuleGeometry args={[0.015, 0.6, 6, 8]} />
        <meshToonMaterial color={METAL} gradientMap={ramp} />
      </mesh>

      {/* ── small gold-star charm hanging in the top corner, swaying ── */}
      <group ref={charm} position={[0.42, 0.38, -0.62]}>
        <mesh position={[0, -0.07, 0]}>
          <cylinderGeometry args={[0.003, 0.003, 0.14, 6]} />
          <meshBasicMaterial color="#caa54a" />
        </mesh>
        <mesh position={[0, -0.15, 0]}>
          <shapeGeometry args={[drumStar]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.9} side={DoubleSide} />
        </mesh>
      </group>
    </group>
  );
}
