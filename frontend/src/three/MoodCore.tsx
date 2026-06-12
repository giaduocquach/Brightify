import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Color, type Mesh } from 'three';
import { CORE_VERT, CORE_FRAG } from './shaders';
import { vaToColor } from './va';
import { useStore } from '../state/store';
import { engine } from '../audio/engine';

// Morphing icosahedron = the playing song's mood. Visible in the now-playing view.
export default function MoodCore({ visible }: { visible: boolean }) {
  const mesh = useRef<Mesh>(null);
  const colA = useRef(new Color('#a78bfa'));
  const colB = useRef(new Color('#67e8f9'));
  const tA = useMemo(() => new Color(), []);
  const tB = useMemo(() => new Color(), []);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uArousal: { value: 0.5 },
      uRms: { value: 0 },
      uColA: { value: new Color('#a78bfa') },
      uColB: { value: new Color('#67e8f9') },
      uAlpha: { value: 0.95 },
    }),
    [],
  );

  useFrame((_, dt) => {
    if (!visible || !mesh.current) return;
    const { targetV, targetA } = useStore.getState();
    vaToColor(targetV, targetA, tA);
    vaToColor(Math.min(1, targetV + 0.12), Math.min(1, targetA + 0.15), tB);
    const k = Math.min(1, dt * 1.6);
    colA.current.lerp(tA, k);
    colB.current.lerp(tB, k);

    const u = uniforms;
    u.uTime.value += dt;
    u.uArousal.value = targetA;
    u.uRms.value += (engine.features.rms - u.uRms.value) * 0.15;
    u.uColA.value.copy(colA.current);
    u.uColB.value.copy(colB.current);

    mesh.current.rotation.y += dt * 0.15;
    mesh.current.rotation.x += dt * 0.05;
  });

  return (
    <mesh ref={mesh} visible={visible}>
      <icosahedronGeometry args={[1.15, 5]} />
      <shaderMaterial
        vertexShader={CORE_VERT}
        fragmentShader={CORE_FRAG}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}
