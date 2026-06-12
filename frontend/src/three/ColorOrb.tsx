import { useRef, useState } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { AdditiveBlending, BackSide, Vector3, type Group } from 'three';
import type { EmotionColor } from '../data/colors';
import { useStore } from '../state/store';

interface Props {
  color: EmotionColor;
  position: [number, number, number];
  phase: number;
}

// A single emotion orb. r3f handles raycasting/pointer events on the mesh, so
// onClick reliably fires (the bug in the old manual-raycaster build).
export default function ColorOrb({ color, position, phase }: Props) {
  const group = useRef<Group>(null);
  const wantScale = useRef(new Vector3(1, 1, 1));
  const [hovered, setHovered] = useState(false);
  const selected = useStore((s) => s.selectedColors.includes(color.hex));

  useFrame((state) => {
    const g = group.current;
    if (!g) return;
    const t = state.clock.elapsedTime;
    g.position.set(
      position[0],
      position[1] + Math.sin(t * 0.6 + phase) * 0.12,
      position[2] + Math.cos(t * 0.5 + phase) * 0.12,
    );
    const want = hovered ? 1.4 : selected ? 1.18 : 1;
    g.scale.lerp(wantScale.current.set(want, want, want), 0.15);
  });

  const onOver = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setHovered(true);
    useStore.getState().setHover(color.hex);
    document.body.style.cursor = 'pointer';
  };
  const onOut = () => {
    setHovered(false);
    useStore.getState().setHover(null);
    document.body.style.cursor = '';
  };
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    useStore.getState().toggleColor(color.hex);
  };

  return (
    <group ref={group} position={position}>
      {/* glow halo */}
      <mesh scale={1.5}>
        <sphereGeometry args={[0.34, 24, 24]} />
        <meshBasicMaterial
          color={color.hex}
          transparent
          opacity={hovered ? 0.4 : 0.2}
          blending={AdditiveBlending}
          side={BackSide}
          depthWrite={false}
        />
      </mesh>
      {/* solid orb */}
      <mesh onPointerOver={onOver} onPointerOut={onOut} onClick={onClick}>
        <sphereGeometry args={[0.34, 32, 32]} />
        <meshStandardMaterial
          color={color.hex}
          emissive={color.hex}
          emissiveIntensity={selected ? 0.9 : 0.55}
          roughness={0.35}
          metalness={0}
        />
        {selected && (
          <mesh scale={1.08}>
            <sphereGeometry args={[0.34, 32, 32]} />
            <meshBasicMaterial color="#ffffff" wireframe transparent opacity={0.25} />
          </mesh>
        )}
      </mesh>
      {/* label */}
      <Html center position={[0, -0.62, 0]} distanceFactor={9} pointerEvents="none" prepend>
        <div className={`orb3d-label${hovered ? ' is-hover' : ''}`} aria-hidden="true">
          <span className="orb3d-name">{color.label}</span>
          <span className="orb3d-emotion">{color.emotion}</span>
        </div>
      </Html>
    </group>
  );
}
