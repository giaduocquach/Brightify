import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { AdditiveBlending, Color, Group, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { vaToColor } from '../va';
import { solarRefs } from './refs';
import { glowTexture } from './glow';

// Deterministic scatter for node i (no Math.random → stable across renders).
function nodePos(i: number, out: Vector3): Vector3 {
  const a = i * 2.39996; // golden angle
  const r = 7 + (i % 5) * 2.3;
  return out.set(Math.cos(a) * r, Math.sin(i * 1.7) * 6, Math.sin(a) * r);
}

const R = 12; // wander envelope radius

// Free-flight ("similar songs"): the pod wanders a smooth Lissajous path through open
// space past floating song nodes (title + artist). Driving the pod here means the
// third-person camera follow + the seated chibi follow along. The node the pod is nearest
// to the playing track (store.index) glows brightest.
export default function FreeFlight() {
  const tracks = useStore((s) => s.flyTracks);
  const index = useStore((s) => s.index);
  const tex = glowTexture();
  const n = tracks.length;

  const colors = useMemo(() => tracks.map((t) => vaToColor(t.valence, t.arousal, new Color())), [tracks]);
  const positions = useMemo(() => tracks.map((_, i) => nodePos(i, new Vector3())), [tracks]);
  const refs = useRef<(Group | null)[]>([]);
  const a = useRef(new Vector3());
  const b = useRef(new Vector3());

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    // wander path + forward = derivative
    a.current.set(Math.sin(t * 0.13) * R, Math.sin(t * 0.19) * R * 0.4, Math.cos(t * 0.11) * R);
    const t2 = t + 0.06;
    b.current.set(Math.sin(t2 * 0.13) * R, Math.sin(t2 * 0.19) * R * 0.4, Math.cos(t2 * 0.11) * R);
    solarRefs.shipPos.copy(a.current);
    solarRefs.shipForward.copy(b.current).sub(a.current).normalize();
    if (solarRefs.shipForward.lengthSq() < 1e-4) solarRefs.shipForward.set(0, 0, 1);

    for (let k = 0; k < n; k++) {
      const g = refs.current[k];
      if (!g) continue;
      g.scale.setScalar(k === index ? 1.6 : 0.9);
    }
  });

  if (n === 0) return null;

  return (
    <group>
      {tracks.map((track, k) => (
        <group key={track.track_id || k} ref={(el) => { refs.current[k] = el; }} position={positions[k]}>
          <sprite scale={1.4}>
            <spriteMaterial map={tex} color={colors[k]} transparent
              opacity={k === index ? 0.95 : 0.4}
              blending={AdditiveBlending} depthWrite={false} />
          </sprite>
          {k === index && (
            <Html center distanceFactor={3} position={[0, 0.9, 0]} pointerEvents="none">
              <div className="song-card is-active">
                <span className="song-card-title">{track.track_name}</span>
                <span className="song-card-artist">{track.artist}</span>
              </div>
            </Html>
          )}
        </group>
      ))}
    </group>
  );
}
