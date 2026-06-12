import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import {
  AdditiveBlending, Color, DoubleSide, Group, RingGeometry, Vector3,
} from 'three';
import type { BodyDef } from './bodies';
import { EMOTION_COLORS } from '../../data/colors';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { useBodyTextures } from './planetTextures';
import Atmosphere from './Atmosphere';

// ── Saturn-style ring with radial-correct UVs (sample the strip texture by radius) ──
function PlanetRing({ def }: { def: BodyDef }) {
  const { ring } = useBodyTextures(def);
  const geo = useMemo(() => {
    const inner = def.size * 1.35;
    const outer = def.size * 2.3;
    const g = new RingGeometry(inner, outer, 128);
    const pos = g.attributes.position;
    const uv = g.attributes.uv;
    const v = new Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      uv.setXY(i, (v.length() - inner) / (outer - inner), 0.5);
    }
    return g;
  }, [def.size]);

  if (!ring) return null;
  return (
    <mesh geometry={geo} rotation={[Math.PI / 2 - 0.35, 0, 0]}>
      <meshBasicMaterial map={ring} side={DoubleSide} transparent depthWrite={false} />
    </mesh>
  );
}

// ── Texture-backed planets + Moon (bump relief, Earth night-lights + clouds, ring) ──
function TexturedSphere({ def }: { def: BodyDef }) {
  const { map, clouds, night, bump } = useBodyTextures(def);
  const cloudRef = useRef<Group>(null);
  useFrame((_, dt) => { if (cloudRef.current) cloudRef.current.rotation.y += dt * 0.015; });

  return (
    <>
      <mesh>
        <sphereGeometry args={[def.size, 64, 64]} />
        <meshStandardMaterial
          map={map}
          bumpMap={bump}
          bumpScale={bump ? 0.015 : 0}
          // Earth city-lights: emissive only reads where the day map is dark, so it
          // glows on the night side — cheap, and Bloom makes the cities twinkle.
          emissiveMap={night}
          emissive={night ? '#ffffff' : '#000000'}
          emissiveIntensity={night ? 0.55 : 0}
          roughness={0.92}
          metalness={0.0}
        />
      </mesh>
      {clouds && (
        <group ref={cloudRef}>
          <mesh>
            <sphereGeometry args={[def.size * 1.02, 48, 48]} />
            <meshStandardMaterial map={clouds} transparent opacity={0.4} depthWrite={false} />
          </mesh>
        </group>
      )}
      {def.kind === 'ringed' && <PlanetRing def={def} />}
    </>
  );
}

// ── Pluto: no texture available → muted procedural tholin sphere ──
function PlutoSphere({ def }: { def: BodyDef }) {
  return (
    <mesh>
      <sphereGeometry args={[def.size, 40, 40]} />
      <meshStandardMaterial color="#9a7a5a" roughness={1} metalness={0} />
    </mesh>
  );
}

// ── Comet: icy nucleus + glowing green coma + tail ──
function Comet({ def, color }: { def: BodyDef; color: Color }) {
  const tex = glowTexture();
  const tail = useRef<Group>(null);
  useFrame(() => {
    const p = solarRefs.bodyPos[def.hex];
    if (tail.current && p) tail.current.rotation.y = Math.atan2(p.x, p.z);
  });
  return (
    <>
      <mesh>
        <icosahedronGeometry args={[def.size * 0.6, 1]} />
        <meshStandardMaterial color="#dfeee6" roughness={0.4} emissive={color} emissiveIntensity={0.3} />
      </mesh>
      <sprite scale={def.size * 3}>
        <spriteMaterial map={tex} color={color} transparent opacity={0.8}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
      <group ref={tail}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <sprite key={i} position={[0, 0, def.size * (1.6 + i * 1.2)]} scale={def.size * (2.6 - i * 0.36)}>
            <spriteMaterial map={tex} color={color} transparent opacity={(0.55 - i * 0.08)}
              blending={AdditiveBlending} depthWrite={false} />
          </sprite>
        ))}
      </group>
    </>
  );
}

// ── Black hole: dark core + bright rotating accretion disk + lensing halo ──
function BlackHole({ def, color }: { def: BodyDef; color: Color }) {
  const tex = glowTexture();
  const disk = useRef<Group>(null);
  const ringGeo = useMemo(() => new RingGeometry(def.size * 1.3, def.size * 2.6, 96), [def.size]);
  useFrame((_, dt) => { if (disk.current) disk.current.rotation.z += dt * 0.5; });
  return (
    <>
      <mesh>
        <sphereGeometry args={[def.size, 32, 32]} />
        <meshBasicMaterial color="#04030a" />
      </mesh>
      <group ref={disk} rotation={[1.3, 0.2, 0]}>
        <mesh geometry={ringGeo}>
          <meshBasicMaterial color="#ffb066" side={DoubleSide} transparent opacity={0.9}
            blending={AdditiveBlending} depthWrite={false} />
        </mesh>
      </group>
      <sprite scale={def.size * 5}>
        <spriteMaterial map={tex} color={color} transparent opacity={0.35}
          blending={AdditiveBlending} depthWrite={false} />
      </sprite>
    </>
  );
}

// One celestial body: orbits (around the Sun, or its parent for the Moon), renders
// the realistic geometry for its kind, wears an emotion-hue atmosphere, and acts as
// the colour-selection control. The `hex` it passes to toggleColor never changes.
export default function CelestialBody({ def }: { def: BodyDef }) {
  const group = useRef<Group>(null);
  const tilt = useRef<Group>(null);
  const spin = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);

  const selected = useStore((s) => s.selectedColors.includes(def.hex));
  const exploring = useStore((s) => s.mode === 'explore' && s.selectedColors[0] === def.hex);
  const focused = useStore((s) => s.mode === 'explore' || s.mode === 'journey');
  const { toggleColor, setHover } = useStore.getState();

  const info = useMemo(() => EMOTION_COLORS.find((c) => c.hex === def.hex), [def.hex]);
  const color = useMemo(() => new Color(def.hex), [def.hex]);

  const worldPos = useMemo(() => {
    const v = new Vector3();
    solarRefs.bodyPos[def.hex] = v;
    return v;
  }, [def.hex]);

  useFrame((state, dt) => {
    const t = state.clock.elapsedTime;
    // orbit centre: the Sun, or the parent body (Moon → Earth)
    let cx = 0, cy = 0, cz = 0;
    if (def.parent) {
      const p = solarRefs.bodyPos[def.parent];
      if (p) { cx = p.x; cy = p.y; cz = p.z; }
    }
    const ang = def.phase + t * def.orbitSpeed;
    const e = def.eccentricity ?? 0;
    const r = e ? def.orbitRadius * (1 - e * e) / (1 + e * Math.cos(ang)) : def.orbitRadius;
    const x = cx + Math.cos(ang) * r;
    const z = cz + Math.sin(ang) * r;
    const y = cy + Math.sin(ang * 1.3) * r * def.inclination;
    worldPos.set(x, y, z);
    if (group.current) group.current.position.set(x, y, z);

    // self-rotation (slowed for the planet you're running on, so the path stays put)
    if (spin.current) spin.current.rotation.y += dt * (exploring ? def.spinSpeed * 0.08 : def.spinSpeed);
    // selected bodies breathe with the music (mesh only, not the orbit)
    if (tilt.current) tilt.current.scale.setScalar(selected ? 1 + engine.features.rms * 0.4 : 1);
  });

  const dim = focused && !selected;
  const showAtmo = def.kind === 'planet' || def.kind === 'ringed' || def.kind === 'moon';

  const enter = () => { setHovered(true); setHover(def.hex); document.body.style.cursor = 'pointer'; };
  const leave = () => { setHovered(false); setHover(null); document.body.style.cursor = 'default'; };

  return (
    <group
      ref={group}
      onPointerOver={(e) => { e.stopPropagation(); enter(); }}
      onPointerOut={(e) => { e.stopPropagation(); leave(); }}
      onClick={(e) => { e.stopPropagation(); toggleColor(def.hex); }}
    >
      <group ref={tilt} rotation={[0, 0, def.axialTilt]}>
        <group ref={spin}>
          {def.kind === 'comet' ? (
            <Comet def={def} color={color} />
          ) : def.kind === 'blackhole' ? (
            <BlackHole def={def} color={color} />
          ) : def.texture ? (
            <TexturedSphere def={def} />
          ) : (
            <PlutoSphere def={def} />
          )}
        </group>
      </group>

      {showAtmo && (
        <Atmosphere hex={def.hex} size={def.size} intensity={selected ? 1.9 : dim ? 0.5 : 1.1} />
      )}

      {(hovered || selected) && info && (
        <Html center distanceFactor={16} position={[0, def.size + 1.0, 0]} pointerEvents="none">
          <div className={`orb3d-label${hovered ? ' is-hover' : ''}`}>
            <span className="orb3d-name">{def.name}</span>
            <span className="orb3d-emotion">{info.label} · {info.emotion}</span>
          </div>
        </Html>
      )}
    </group>
  );
}
