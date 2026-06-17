import type { ColorResult, Song } from '../api/client';
import { vaToHex } from '../three/va';

// Russell's circumplex of affect (valence × arousal). Plots the chosen colour(s) as glowing
// dots and the recommended songs as faint dots from their own V-A — so the user literally sees
// the songs cluster around the colour's point ("same V-A region = why these songs"). Pure SVG.
const SIZE = 152;
const PAD = 14;
const SPAN = SIZE - PAD * 2;
const px = (v: number) => PAD + v * SPAN;          // valence → x (left = buồn, right = vui)
const py = (a: number) => PAD + (1 - a) * SPAN;    // arousal → y (top = động, inverted for SVG)

export default function VACircumplex({ bridge, songs }: { bridge: ColorResult['bridge']; songs: Song[] }) {
  return (
    <svg
      className="va-map"
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label="Bản đồ Valence–Arousal: các bài hát nằm quanh vùng cảm xúc của màu đã chọn"
    >
      <rect x={PAD} y={PAD} width={SPAN} height={SPAN} className="va-frame" />
      <line x1={PAD} y1={py(0.5)} x2={SIZE - PAD} y2={py(0.5)} className="va-axis" />
      <line x1={px(0.5)} y1={PAD} x2={px(0.5)} y2={SIZE - PAD} className="va-axis" />

      {/* Russell quadrant labels (VN) */}
      <text x={px(0.97)} y={py(0.95)} className="va-quad" textAnchor="end">Hân hoan</text>
      <text x={px(0.03)} y={py(0.95)} className="va-quad">Căng thẳng</text>
      <text x={px(0.03)} y={py(0.05) + 7} className="va-quad">U buồn</text>
      <text x={px(0.97)} y={py(0.05) + 7} className="va-quad" textAnchor="end">Thư thái</text>

      {/* recommended songs */}
      {songs.map((s, i) => (
        <circle
          key={s.track_id || i}
          cx={px(s.valence)} cy={py(s.arousal)} r={2.3}
          fill={vaToHex(s.valence, s.arousal)} className="va-song"
        />
      ))}

      {/* chosen colour(s) — the recommendation target */}
      {bridge?.map((b) => (
        <circle
          key={b.hex}
          cx={px(b.valence)} cy={py(b.arousal)} r={5}
          fill={b.hex} stroke="#fff" strokeWidth={1.4} className="va-color"
        />
      ))}
    </svg>
  );
}
