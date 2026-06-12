import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { AdditiveBlending, Color, Group } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { vaToColor } from '../va';
import { solarRefs } from './refs';
import { glowTexture } from './glow';
import { journeyPoint } from './journeyPath';

// The journey songs, strung along the flight path as glowing gates with a title +
// artist card. As the cockpit advances they stream past the canopy ("trôi qua").
// The card the ship is passing (= the song now playing) glows brightest. Order is
// exactly `results` — never reshuffled here.
export default function Cockpit() {
  const tracks = useStore((s) => s.results);
  const sel = useStore((s) => s.selectedColors);
  const index = useStore((s) => s.index);
  const tex = glowTexture();

  const colors = useMemo(
    () => tracks.map((t) => vaToColor(t.valence, t.arousal, new Color())),
    [tracks],
  );
  const refs = useRef<(Group | null)[]>([]);
  const n = tracks.length;

  useFrame(() => {
    const a = solarRefs.bodyPos[sel[0]];
    const b = solarRefs.bodyPos[sel[1]];
    if (!a || !b || n === 0) return;
    for (let k = 0; k < n; k++) {
      const g = refs.current[k];
      if (!g) continue;
      journeyPoint(a, b, (k + 0.5) / n, g.position);
      g.scale.setScalar(k === index ? 1.5 + engine.features.bass * 0.8 : 0.9);
    }
  });

  if (n === 0) return null;

  return (
    <group>
      {tracks.map((t, k) => (
        <group key={t.track_id || k} ref={(el) => { refs.current[k] = el; }}>
          <sprite scale={1.4}>
            <spriteMaterial map={tex} color={colors[k]} transparent
              opacity={k === index ? 0.95 : 0.45}
              blending={AdditiveBlending} depthWrite={false} />
          </sprite>
          <Html center distanceFactor={9} position={[0, 0.9, 0]} pointerEvents="none">
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
