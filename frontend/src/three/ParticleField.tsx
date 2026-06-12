import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, type Points, type PointsMaterial } from 'three';
import { engine } from '../audio/engine';

const COUNT = typeof window !== 'undefined' && window.innerWidth < 768 ? 220 : 600;

// Audio-reactive particle shell around the mood core (now-playing only).
export default function ParticleField({ visible }: { visible: boolean }) {
  const points = useRef<Points>(null);

  const positions = useMemo(() => {
    const arr = new Float32Array(COUNT * 3);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < COUNT; i++) {
      const y = 1 - (i / (COUNT - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const phi = golden * i;
      const radius = 2.0 + ((i * 7) % 11) / 11 * 0.8;
      arr[i * 3] = Math.cos(phi) * r * radius;
      arr[i * 3 + 1] = y * radius;
      arr[i * 3 + 2] = Math.sin(phi) * r * radius;
    }
    return arr;
  }, []);

  useFrame((_, dt) => {
    if (!visible || !points.current) return;
    points.current.rotation.y += dt * 0.04;
    const s = 1 + engine.features.bass * 0.35;
    points.current.scale.setScalar(s);
    const mat = points.current.material as PointsMaterial;
    mat.size = 0.04 + engine.features.treble * 0.06;
  });

  return (
    <points ref={points} visible={visible}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#cbb6ff"
        size={0.05}
        sizeAttenuation
        transparent
        opacity={0.7}
        blending={AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
}
