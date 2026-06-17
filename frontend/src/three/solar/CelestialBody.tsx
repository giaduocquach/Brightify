import { Suspense, useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import {
  DoubleSide, Group, RingGeometry, Vector3,
} from 'three';
import type { BodyDef } from './bodies';
import { orbitPosAt } from './bodies';
import { EMOTION_COLORS } from '../../data/colors';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { solarRefs } from './refs';
import { useBodyTextures } from './planetTextures';
import { useDeviceTier } from './deviceTier';
import { hasHiRes } from './texturesHi';
import { isFocused } from './focus';
import { useHiResMap } from './useHiResMap';
import { giantParamsFor } from './giantConfig';
import Atmosphere from './Atmosphere';
import GasGiantDetail from './GasGiantDetail';
import Comet from './Comet';
import BlackHole from './BlackHole';

// ── Saturn-style ring with radial-correct UVs (sample the strip texture by radius) ──
function PlanetRing({ def }: { def: BodyDef }) {
  const { ring } = useBodyTextures(def);
  const geo = useMemo(() => {
    const inner = def.size * 1.35;
    const outer = def.size * 2.0; // contained so the ring never reaches the neighbouring orbits
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
  // Adaptive LOD: on capable devices, the planet you're close to (explore/journey) swaps its
  // day map to 4K; everyone else (and all distant planets) stays on the 2K baseline. The 2K
  // map renders the whole time (`hi ?? map`) so the upgrade reads as a sharpen, never a flash.
  const tier = useDeviceTier();
  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const active = tier === 'high' && hasHiRes(def.hex) && isFocused(mode, sel, def.hex);
  const hi = useHiResMap(def.hex, active);
  const activeMap = hi ?? map;
  // Ice giants (Uranus/Neptune): tint the map + add a subtle detail shell so they don't read
  // as flat single-colour discs. Tint is free (every tier); the shell is high-tier only.
  const giant = giantParamsFor(def.hex);
  useFrame((_, dt) => { if (cloudRef.current && !solarRefs.reducedMotion) cloudRef.current.rotation.y += dt * 0.015; });

  return (
    <>
      <mesh>
        <sphereGeometry args={[def.size, 64, 64]} />
        <meshStandardMaterial
          map={activeMap}
          color={giant ? giant.tint : undefined}
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
      {giant && tier === 'high' && <GasGiantDetail def={def} params={giant} />}
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

  const worldPos = useMemo(() => {
    const v = new Vector3();
    solarRefs.bodyPos[def.hex] = v;
    return v;
  }, [def.hex]);
  // Last live clock time, so reduced-motion freezes orbits where they are (no jump).
  const frozenTime = useRef(0);

  useFrame((state, dt) => {
    const rm = solarRefs.reducedMotion;
    if (!rm) frozenTime.current = state.clock.elapsedTime;
    const t = rm ? frozenTime.current : state.clock.elapsedTime;
    // orbit centre: the Sun, or the parent body (Moon → Earth). Shared `orbitPosAt` keeps the
    // ellipse math identical to what SurfaceRun's surf handler uses for the comet's velocity.
    const parent = def.parent ? solarRefs.bodyPos[def.parent] : null;
    orbitPosAt(def, t, worldPos, parent);
    if (group.current) group.current.position.copy(worldPos);

    // self-rotation (slowed for the planet you're running on, so the path stays put; frozen under reduced-motion)
    if (spin.current && !rm) spin.current.rotation.y += dt * (exploring ? def.spinSpeed * 0.08 : def.spinSpeed);
    // scale = hover bump (so clicks visibly register) × audio breathe (selected). Lerped → spring feel.
    if (tilt.current) {
      const target = (hovered ? 1.1 : 1) * (selected ? 1 + engine.features.rms * 0.4 : 1);
      const cur = tilt.current.scale.x;
      tilt.current.scale.setScalar(cur + (target - cur) * Math.min(1, dt * 12));
    }
  });

  const dim = focused && !selected;
  // Procedural showpieces (comet/black hole) bring their own glow → no fresnel atmosphere.
  const showAtmo = !def.special && (def.kind === 'planet' || def.kind === 'ringed' || def.kind === 'moon');

  const enter = () => { setHovered(true); setHover(def.hex); document.body.style.cursor = 'pointer'; };
  const leave = () => { setHovered(false); setHover(null); document.body.style.cursor = 'default'; };

  return (
    <group
      ref={group}
      onPointerOver={(e) => { e.stopPropagation(); enter(); }}
      onPointerOut={(e) => { e.stopPropagation(); leave(); }}
      onClick={(e) => { e.stopPropagation(); toggleColor(def.hex); }}
    >
      {def.special === 'comet' ? (
        <Comet def={def} selected={selected} />
      ) : def.special === 'blackhole' ? (
        <BlackHole def={def} selected={selected} />
      ) : (
        <group ref={tilt} rotation={[0, 0, def.axialTilt]}>
          <group ref={spin}>
            {/* fallback: a flat emotion-hue sphere until the texture streams in (no blank/blurry pop) */}
            <Suspense fallback={
              <mesh>
                <sphereGeometry args={[def.size, 32, 32]} />
                <meshStandardMaterial color={def.hex} roughness={1} metalness={0} />
              </mesh>
            }>
              {def.texture ? (
                <TexturedSphere def={def} />
              ) : (
                <PlutoSphere def={def} />
              )}
            </Suspense>
          </group>
        </group>
      )}

      {/* invisible (opacity 0) but raycastable halo so distant specks — the comet (r48) and
          black hole (r70) — stay easy to hover/click despite being sub-pixel on screen. */}
      {def.special && (
        <mesh>
          <sphereGeometry args={[Math.max(def.size * 4, 2), 8, 8]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
      )}

      {showAtmo && (
        // A thin, faint limb rim (high fresnel power = edge-only) so the photoreal texture
        // reads as a real planet — not a glowing colour ball — while keeping a hint of the
        // emotion hue. Brighter only when the body is the selected destination.
        <Atmosphere hex={def.hex} size={def.size} intensity={selected ? 0.85 : hovered ? 0.6 : dim ? 0.18 : 0.34} power={5.0} />
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
