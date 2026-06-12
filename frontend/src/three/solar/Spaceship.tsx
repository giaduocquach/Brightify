import { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, Group, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { journeyPoint } from './journeyPath';

// A craft-like vessel (open cockpit under a glass canopy, swept wings, twin engines)
// with a Vietnamese red/gold stripe. The seated astronaut sits at the pod origin and
// is visible through the canopy. Journey drives the A→B path here; free-flight drives
// the refs from FreeFlight and the craft just renders wherever they point.
export default function Spaceship() {
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const ship = useRef<Group>(null);
  const tex = glowTexture();
  const next = useRef(new Vector3());
  const lookAt = useRef(new Vector3());

  useEffect(() => {
    solarRefs.shipActive = true;
    return () => { solarRefs.shipActive = false; };
  }, []);

  useFrame(() => {
    if (mode === 'journey') {
      const a = solarRefs.bodyPos[sel[0]];
      const b = solarRefs.bodyPos[sel[1]];
      if (a && b) {
        const st = useStore.getState();
        const { time, duration } = engine.progress(); // live playhead → smooth motion
        const n = st.queue.length || 1;
        const frac = duration > 0 ? time / duration : 0;
        const idx = Math.max(0, st.index);
        const p = Math.min(1, (idx + frac) / n);
        journeyPoint(a, b, p, solarRefs.shipPos);
        journeyPoint(a, b, Math.min(1, p + 0.02), next.current);
        solarRefs.shipForward.copy(next.current).sub(solarRefs.shipPos).normalize();
        if (solarRefs.shipForward.lengthSq() < 1e-4) solarRefs.shipForward.set(0, 0, 1);
      }
    }
    if (ship.current) {
      ship.current.position.copy(solarRefs.shipPos);
      lookAt.current.copy(solarRefs.shipPos).add(solarRefs.shipForward);
      ship.current.lookAt(lookAt.current); // -Z faces travel
    }
  });

  return (
    <group ref={ship}>
      {/* lower hull (the pilot sits in this; open on top) */}
      <mesh position={[0, -0.16, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <capsuleGeometry args={[0.46, 0.7, 10, 20]} />
        <meshStandardMaterial color="#d4dae8" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* nose cone (front, -Z) */}
      <mesh position={[0, -0.1, -0.85]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.34, 0.7, 24]} />
        <meshStandardMaterial color="#aebbd6" metalness={0.7} roughness={0.25} />
      </mesh>
      {/* VN red/gold stripe around the hull */}
      <mesh position={[0, -0.16, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.47, 0.05, 10, 28]} />
        <meshStandardMaterial color="#da251d" metalness={0.4} roughness={0.4} emissive="#da251d" emissiveIntensity={0.2} />
      </mesh>
      {/* glass canopy over the pilot */}
      <mesh position={[0, 0.12, -0.05]}>
        <sphereGeometry args={[0.5, 24, 18, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
        <meshStandardMaterial color="#bfe3ff" transparent opacity={0.2} metalness={0.1} roughness={0.05} depthWrite={false} />
      </mesh>
      {/* swept wings */}
      <mesh position={[0.62, -0.18, 0.18]} rotation={[0, -0.5, -0.15]}>
        <boxGeometry args={[0.7, 0.05, 0.4]} />
        <meshStandardMaterial color="#9fb0d4" metalness={0.6} roughness={0.35} />
      </mesh>
      <mesh position={[-0.62, -0.18, 0.18]} rotation={[0, 0.5, 0.15]}>
        <boxGeometry args={[0.7, 0.05, 0.4]} />
        <meshStandardMaterial color="#9fb0d4" metalness={0.6} roughness={0.35} />
      </mesh>
      {/* tail fin */}
      <mesh position={[0, 0.16, 0.55]} rotation={[0.4, 0, 0]}>
        <boxGeometry args={[0.05, 0.34, 0.3]} />
        <meshStandardMaterial color="#ffcd00" metalness={0.5} roughness={0.4} />
      </mesh>
      {/* twin engine glow (back, +Z) */}
      <sprite position={[0.18, -0.16, 0.7]} scale={0.5}>
        <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.9} blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite position={[-0.18, -0.16, 0.7]} scale={0.5}>
        <spriteMaterial map={tex} color="#7cc7ff" transparent opacity={0.9} blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <pointLight position={[0, 0.1, 0]} intensity={2.6} distance={3} color="#bfe3ff" />
    </group>
  );
}
