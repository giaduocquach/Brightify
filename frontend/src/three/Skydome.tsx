import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { BackSide, Color, ShaderMaterial } from 'three';
import { SKY_VERT, SKY_FRAG } from './shaders';
import { vaToColor, hexToVA } from './va';
import { useStore } from '../state/store';
import { engine } from '../audio/engine';

// Full-view gradient atmosphere. Lerps toward the current target (V,A) every
// frame and brightens with audio energy.
export default function Skydome() {
  const matRef = useRef<ShaderMaterial>(null);
  const topNow = useRef(new Color('#1b1840'));
  const botNow = useRef(new Color('#050410'));
  const topTarget = useMemo(() => new Color(), []);
  const botTarget = useMemo(() => new Color(), []);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uRms: { value: 0 },
      uTop: { value: new Color('#1b1840') },
      uBot: { value: new Color('#050410') },
    }),
    [],
  );

  useFrame((_, dt) => {
    const { targetV, targetA, hoverHex } = useStore.getState();
    // Hovering an orb previews its mood without committing the selection.
    const va = hoverHex ? hexToVA(hoverHex) : { v: targetV, a: targetA };
    vaToColor(va.v, va.a, topTarget);
    botTarget.copy(topTarget).multiplyScalar(0.28);

    const k = Math.min(1, dt * 1.6);
    topNow.current.lerp(topTarget, k);
    botNow.current.lerp(botTarget, k);

    const u = uniforms;
    u.uTop.value.copy(topNow.current);
    u.uBot.value.copy(botNow.current);
    u.uTime.value += dt;
    u.uRms.value += (engine.features.rms - u.uRms.value) * 0.1;
  });

  return (
    <mesh scale={60}>
      <sphereGeometry args={[1, 32, 32]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={SKY_VERT}
        fragmentShader={SKY_FRAG}
        uniforms={uniforms}
        side={BackSide}
        depthWrite={false}
      />
    </mesh>
  );
}
