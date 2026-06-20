import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { AdditiveBlending, BackSide, Color, Group, type Mesh, ShaderMaterial } from 'three';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { ATMO_VERT, ATMO_FRAG } from '../shaders';

const METAL_D = '#1e2640';

// First-person cockpit — kept deliberately OPEN: you look out through an (almost invisible)
// canopy and see space across ~80% of the view. Only a slim PBR dashboard sits along the very
// bottom and the EQ gauges pulse with the music. Attached to the camera so it frames the view.
export default function CockpitInterior() {
  const camera = useThree((s) => s.camera);
  const root = useRef<Group>(null);
  const bars = useRef<(Mesh | null)[]>([]);
  const barX = useMemo(() => [-0.16, -0.08, 0, 0.08, 0.16], []);
  // faint glass: a fresnel rim that only glows at the very edges → "looking through a
  // canopy" without obscuring the centre.
  const glassMat = useMemo(() => new ShaderMaterial({
    vertexShader: ATMO_VERT,
    fragmentShader: ATMO_FRAG,
    uniforms: {
      uColor: { value: new Color('#bfe6ff') },
      uIntensity: { value: 0.015 }, // near-invisible canopy → reads as open glass (immersive)
      uPower: { value: 5.5 },
    },
    transparent: true,
    side: BackSide,
    depthWrite: false,
    blending: AdditiveBlending,
  }), []);

  useFrame(() => {
    const g = root.current;
    if (!g) return;
    g.visible = solarRefs.cockpitView;
    if (!g.visible) return;

    g.position.copy(camera.position);
    g.quaternion.copy(camera.quaternion);

    const f = engine.features;
    const bands = [f.bass, (f.bass + f.rms) * 0.5, f.rms, (f.rms + f.treble) * 0.5, f.treble];
    bars.current.forEach((b, i) => { if (b) b.scale.y = 0.25 + Math.min(1, bands[i] * 2.4); });
  });

  return (
    <group ref={root}>
      {/* faint glass canopy — fresnel rim only, centre stays clear */}
      <mesh material={glassMat}>
        <sphereGeometry args={[0.85, 24, 16]} />
      </mesh>

      {/* ── slim PBR dashboard strip across the very bottom (tilted up to the pilot) ── */}
      <mesh position={[0, -0.46, -0.62]} rotation={[-0.62, 0, 0]}>
        <boxGeometry args={[1.0, 0.2, 0.06]} />
        <meshStandardMaterial color={METAL_D} roughness={0.5} metalness={0.45} envMapIntensity={0.4} />
      </mesh>
      <mesh position={[0, -0.38, -0.56]} rotation={[-0.62, 0, 0]}>
        <boxGeometry args={[1.0, 0.03, 0.1]} />
        <meshStandardMaterial color="#da251d" emissive="#da251d" emissiveIntensity={0.3} roughness={0.5} />
      </mesh>
      {/* EQ gauge bars (music-reactive) */}
      {barX.map((x, i) => (
        <mesh key={i} ref={(el) => { bars.current[i] = el; }} position={[x, -0.43, -0.58]}>
          <boxGeometry args={[0.045, 0.1, 0.02]} />
          <meshStandardMaterial color="#7cf0ff" emissive="#7cf0ff" emissiveIntensity={1.6} toneMapped={false} />
        </mesh>
      ))}
      {/* a couple of glowing buttons + trống đồng motif (subtle bronze) */}
      {[-0.34, 0.34].map((x, i) => (
        <mesh key={i} position={[x, -0.47, -0.56]} rotation={[-0.62, 0, 0]}>
          <cylinderGeometry args={[0.022, 0.022, 0.018, 12]} />
          <meshStandardMaterial color={i ? '#ff5d6c' : '#5dff9b'} emissive={i ? '#ff5d6c' : '#5dff9b'} emissiveIntensity={1.0} toneMapped={false} />
        </mesh>
      ))}
      <mesh position={[0, -0.48, -0.6]} rotation={[-0.62, 0, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 0.012, 20]} />
        <meshStandardMaterial color="#c98a3a" emissive="#3a230a" emissiveIntensity={0.4} metalness={0.7} roughness={0.35} />
      </mesh>
    </group>
  );
}
