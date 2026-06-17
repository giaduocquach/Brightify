import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, Group, IcosahedronGeometry,
  Quaternion, type ShaderMaterial, type Sprite, Vector3,
} from 'three';
import type { BodyDef } from './bodies';
import { solarRefs } from './refs';
import { glowTexture, cometSurfaceTexture } from './glow';
import { useDeviceTier } from './deviceTier';
import { COMET_TAIL_VERT, COMET_TAIL_FRAG } from '../shaders';

const UP = new Vector3(0, 1, 0);
const RAD = new Vector3();
const Q = new Quaternion();

interface TailProps {
  count: number; len: number; speed: number; width: number; curve: number;
  size: number; colNear: string; colFar: string; opacity: number;
}

// One particle tail (THREE.Points), animated entirely in the vertex shader from per-particle
// seeds + uTime. Lives inside the parent `tail` group whose quaternion aims +Y anti-sunward.
function TailCloud({ count, len, speed, width, curve, size, colNear, colFar, opacity }: TailProps) {
  const tex = glowTexture();
  const gl = useThree((s) => s.gl);
  const matRef = useRef<ShaderMaterial>(null);

  const geo = useMemo(() => {
    const g = new BufferGeometry();
    const pos = new Float32Array(count * 3);            // unused base (position computed in shader)
    const seed = new Float32Array(count);
    const len01 = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      seed[i] = (i * 0.61803398875) % 1;                // golden-ratio → deterministic spread
      len01[i] = i / count;
    }
    g.setAttribute('position', new BufferAttribute(pos, 3));
    g.setAttribute('aSeed', new BufferAttribute(seed, 1));
    g.setAttribute('aLength01', new BufferAttribute(len01, 1));
    return g;
  }, [count]);

  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uLen: { value: len }, uSpeed: { value: speed },
    uWidth: { value: width }, uCurve: { value: curve }, uSize: { value: size },
    uPixelRatio: { value: gl.getPixelRatio() },
    uTex: { value: tex }, uColNear: { value: new Color(colNear) },
    uColFar: { value: new Color(colFar) }, uOpacity: { value: opacity },
  }), [len, speed, width, curve, size, gl, tex, colNear, colFar, opacity]);

  useFrame((state) => { if (matRef.current && !solarRefs.reducedMotion) matRef.current.uniforms.uTime.value = state.clock.elapsedTime; });

  return (
    <points geometry={geo} frustumCulled={false}>
      <shaderMaterial ref={matRef} vertexShader={COMET_TAIL_VERT} fragmentShader={COMET_TAIL_FRAG}
        uniforms={uniforms} transparent blending={AdditiveBlending} depthWrite={false} />
    </points>
  );
}

// A green-coma comet — the visual for the #008856 emotion slot. A dark, cratered, irregular
// rock-ice nucleus (charcoal, lit only by the Sun → no "plastic" self-glow), a soft GREEN coma
// (C₂ fluoresces green — head only), and two lively PARTICLE tails: a broad curved white/yellow
// DUST tail + a thin straight blue ION tail. Both anti-sunward (the tail group is auto-aimed).
export default function Comet({ def, selected }: { def: BodyDef; selected: boolean }) {
  const tex = glowTexture();
  const bump = cometSurfaceTexture();
  const tier = useDeviceTier();
  const tail = useRef<Group>(null);
  const coma = useRef<Sprite>(null);
  const dustLen = def.size * 9;
  const ionLen = def.size * 13;
  const dustN = tier === 'high' ? 900 : 360;
  const ionN = tier === 'high' ? 600 : 240;

  // Craggy bilobed nucleus: deform a high-detail icosahedron with deterministic layered trig
  // (a low-freq lobe → "rubber-duck" 67P silhouette) — no Math.random.
  const nucleusGeo = useMemo(() => {
    const g = new IcosahedronGeometry(def.size * 0.55, 4);
    const p = g.attributes.position;
    const v = new Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i).normalize();
      const disp = 1
        + 0.22 * Math.sin(v.x * 2.3 + 1.7)        // big lobe → bilobed shape
        + 0.16 * Math.sin(v.x * 7 + v.y * 5)
        + 0.10 * Math.sin(v.y * 11 - v.z * 9)
        + 0.06 * Math.sin(v.z * 17 + v.x * 13);
      v.multiplyScalar(def.size * 0.55 * disp);
      p.setXYZ(i, v.x, v.y, v.z);
    }
    g.computeVertexNormals();
    return g;
  }, [def.size]);

  useFrame((state) => {
    const pos = solarRefs.bodyPos[def.hex];
    if (!pos) return;
    RAD.copy(pos);
    if (RAD.lengthSq() < 1e-6) RAD.set(0, 0, 1);
    RAD.normalize();
    if (tail.current) {
      Q.setFromUnitVectors(UP, RAD); // tails built along +Y → rotate +Y onto the radial
      tail.current.quaternion.copy(Q);
    }
    if (coma.current) {
      const breathe = solarRefs.reducedMotion ? 0 : Math.sin(state.clock.elapsedTime * 2) * 0.08;
      const pulse = 1 + breathe + (selected ? 0.35 : 0);
      coma.current.scale.setScalar(def.size * 3.2 * pulse);
    }
  });

  return (
    <group>
      {/* dark cratered rock-ice nucleus — lit by the Sun, no self-glow (was "plastic") */}
      <mesh geometry={nucleusGeo}>
        <meshStandardMaterial color="#2b2622" roughness={1} metalness={0} bumpMap={bump} bumpScale={0.02} flatShading />
      </mesh>

      {/* green coma (C₂ fluorescence) — soft, gaseous, head-only */}
      <sprite ref={coma}>
        <spriteMaterial map={tex} color="#27e8a0" transparent opacity={0.55} blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite scale={def.size * 1.8}>
        <spriteMaterial map={tex} color="#d8fff0" transparent opacity={0.35} blending={AdditiveBlending} depthWrite={false} />
      </sprite>

      {/* particle tails — anti-sunward (group +Y → radial); NEVER green */}
      <group ref={tail}>
        <TailCloud count={dustN} len={dustLen} speed={0.16} width={def.size * 1.6} curve={0.18}
          size={def.size * 70} colNear="#fff2d8" colFar="#ffcf7a" opacity={0.5} />
        <TailCloud count={ionN} len={ionLen} speed={0.26} width={def.size * 0.35} curve={0}
          size={def.size * 42} colNear="#cfe6ff" colFar="#5f96ff" opacity={0.45} />
      </group>
    </group>
  );
}
