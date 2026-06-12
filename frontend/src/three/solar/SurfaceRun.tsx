import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { Color, Group, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { vaToColor } from '../va';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';

const YUP = new Vector3(0, 1, 0);
const TILT = 0.5; // tilt the run path off the equator so it reads in 3D

// Explore stage: the astronaut runs a great-circle path on the chosen planet, past
// one marker per recommended song (title + artist). The runner's angle is driven by
// playback progress through the queue, so passing marker k ⇔ track k is playing.
// Order is exactly `results` (the recommend order) — never reshuffled here.
export default function SurfaceRun() {
  const hex = useStore((s) => s.selectedColors[0]);
  const tracks = useStore((s) => s.results);
  const index = useStore((s) => s.index);
  const body = hex ? bodyByHex(hex) : undefined;
  const n = tracks.length;

  const u = useMemo(() => new Vector3(1, 0, 0), []);
  const v = useMemo(() => new Vector3(0, Math.cos(TILT), Math.sin(TILT)), []);
  const colors = useMemo(() => tracks.map((t) => vaToColor(t.valence, t.arousal, new Color())), [tracks]);

  const markerRefs = useRef<(Group | null)[]>([]);
  const dir = useRef(new Vector3());
  const center = useRef(new Vector3());

  useEffect(() => {
    solarRefs.runnerActive = true;
    return () => { solarRefs.runnerActive = false; };
  }, []);

  useFrame(() => {
    if (!body || !hex) return;
    const c = solarRefs.bodyPos[hex];
    if (!c) return;
    center.current.copy(c);

    const st = useStore.getState();
    const { time, duration } = engine.progress(); // live playhead → smooth run
    const frac = duration > 0 ? time / duration : 0;
    const idx = Math.max(0, st.index);
    const p = n > 0 ? (idx + frac) / n : 0;

    // runner pose
    const th = p * Math.PI * 2;
    dir.current.copy(u).multiplyScalar(Math.cos(th)).addScaledVector(v, Math.sin(th)).normalize();
    solarRefs.runnerPos.copy(center.current).addScaledVector(dir.current, body.size * 1.06);
    solarRefs.runnerForward
      .copy(u).multiplyScalar(-Math.sin(th)).addScaledVector(v, Math.cos(th)).normalize();

    // markers
    for (let k = 0; k < n; k++) {
      const g = markerRefs.current[k];
      if (!g) continue;
      const thk = (k / n) * Math.PI * 2;
      dir.current.copy(u).multiplyScalar(Math.cos(thk)).addScaledVector(v, Math.sin(thk)).normalize();
      g.position.copy(center.current).addScaledVector(dir.current, body.size * 1.04);
      g.quaternion.setFromUnitVectors(YUP, dir.current); // pole points radially out
      g.scale.setScalar(k === idx ? 1.35 : 1);
    }
  });

  if (!body || !hex || n === 0) return null;
  const s = body.size;

  return (
    <group>
      {tracks.map((t, k) => (
        <group key={t.track_id || k} ref={(el) => { markerRefs.current[k] = el; }}>
          <mesh position={[0, s * 0.18, 0]}>
            <cylinderGeometry args={[s * 0.012, s * 0.012, s * 0.36, 6]} />
            <meshBasicMaterial color={colors[k]} transparent opacity={0.7} />
          </mesh>
          <mesh position={[0, s * 0.4, 0]}>
            <sphereGeometry args={[s * 0.06, 12, 12]} />
            <meshStandardMaterial color={colors[k]} emissive={colors[k]} emissiveIntensity={1} />
          </mesh>
          <Html center distanceFactor={7} position={[0, s * 0.66, 0]} pointerEvents="none">
            <div className={`song-card${k === index ? ' is-active' : ''}`}>
              <span className="song-card-title">{t.track_name}</span>
              <span className="song-card-artist">{t.artist}</span>
            </div>
          </Html>
        </group>
      ))}
    </group>
  );
}
