import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { AdditiveBlending, Color, Group, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { vaToColor } from '../va';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { bodyByHex } from './bodies';

// Smooth wandering direction on the unit sphere (sum of out-of-phase sines → organic,
// non-repeating, deterministic — no Math.random). Used for the roaming astronaut.
function wanderDir(t: number, out: Vector3): Vector3 {
  const theta = t * 0.16 + Math.sin(t * 0.073) * 1.6 + Math.sin(t * 0.031) * 0.8;
  const phi = Math.sin(t * 0.051) * 0.95 + Math.sin(t * 0.117) * 0.4;
  const cp = Math.cos(phi);
  return out.set(cp * Math.cos(theta), Math.sin(phi), cp * Math.sin(theta));
}

// Explore stage: the astronaut just ROAMS the chosen planet — a smooth, continuous,
// random-looking walk (no planted markers). The recommended songs float as small glowing
// orbs in low orbit around the planet; you wander past them. Only the track that's
// currently PLAYING shows a small title card — every other song is just a dim orb — so a
// card can never grow large and cover the screen.
export default function SurfaceRun() {
  const hex = useStore((s) => s.selectedColors[0]);
  const tracks = useStore((s) => s.results);
  const index = useStore((s) => s.index);
  const body = hex ? bodyByHex(hex) : undefined;
  const n = tracks.length;
  const tex = glowTexture();

  const colors = useMemo(() => tracks.map((t) => vaToColor(t.valence, t.arousal, new Color())), [tracks]);
  // golden-angle scatter on a sphere → even spread of song orbs around the planet
  const orbDirs = useMemo(() => tracks.map((_, k) => {
    const y = 1 - ((k + 0.5) / Math.max(1, n)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = k * 2.39996;
    return new Vector3(Math.cos(phi) * r, y, Math.sin(phi) * r);
  }), [tracks, n]);

  const cluster = useRef<Group>(null);
  const orbRefs = useRef<(Group | null)[]>([]);
  const dir = useRef(new Vector3());
  const dirNext = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const center = useRef(new Vector3());

  useEffect(() => {
    solarRefs.runnerActive = true;
    return () => { solarRefs.runnerActive = false; };
  }, []);

  useFrame((state) => {
    if (!body || !hex) return;
    const c = solarRefs.bodyPos[hex];
    if (!c) return;
    center.current.copy(c);
    const t = state.clock.elapsedTime;

    // ── continuous roam: position + tangent forward from the smooth wander path ──
    wanderDir(t, dir.current).normalize();
    solarRefs.runnerPos.copy(center.current).addScaledVector(dir.current, body.size * 1.01);
    wanderDir(t + 0.05, dirNext.current).normalize();
    fwd.current.copy(dirNext.current).sub(dir.current);
    fwd.current.addScaledVector(dir.current, -fwd.current.dot(dir.current)); // tangent
    if (fwd.current.lengthSq() < 1e-6) fwd.current.set(0, 0, 1);
    solarRefs.runnerForward.copy(fwd.current).normalize();

    // ── song orbs float in low orbit; the cluster slowly turns + each orb bobs ──
    if (cluster.current) {
      cluster.current.position.copy(center.current);
      cluster.current.rotation.y += 0.0008;
    }
    for (let k = 0; k < n; k++) {
      const g = orbRefs.current[k];
      if (!g) continue;
      const bob = Math.sin(t * 0.9 + k) * body.size * 0.06;
      g.position.copy(orbDirs[k]).multiplyScalar(body.size * 1.35 + bob);
      g.scale.setScalar(k === index ? 1.7 : 0.85);
    }
  });

  if (!body || !hex || n === 0) return null;
  const s = body.size;

  return (
    <group ref={cluster}>
      {tracks.map((t, k) => (
        <group key={t.track_id || k} ref={(el) => { orbRefs.current[k] = el; }}>
          <mesh>
            <sphereGeometry args={[s * 0.07, 14, 14]} />
            <meshStandardMaterial color={colors[k]} emissive={colors[k]}
              emissiveIntensity={k === index ? 1.8 : 0.7} transparent opacity={k === index ? 1 : 0.55} />
          </mesh>
          <sprite scale={s * (k === index ? 0.7 : 0.4)}>
            <spriteMaterial map={tex} color={colors[k]} transparent
              opacity={k === index ? 0.9 : 0.35} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
          {k === index && (
            <Html center distanceFactor={3} position={[0, s * 0.28, 0]} pointerEvents="none">
              <div className="song-card is-active">
                <span className="song-card-title">{t.track_name}</span>
                <span className="song-card-artist">{t.artist}</span>
              </div>
            </Html>
          )}
        </group>
      ))}
    </group>
  );
}
