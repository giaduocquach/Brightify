// 12 emotion colours (ISCC-NBS vivid centroids) with their Valence-Arousal
// coordinates. SINGLE SOURCE OF TRUTH: v/a are the backend's raw Oklab hsl_to_va()
// output (uncalibrated, matches /api/recommend/color bridge). Regenerate after any
// change to the colour→V-A model so the orb layout, picker atmosphere, and the actual
// recommendation target stay coherent. (V31, 2026-06-12 — replaced 3 divergent
// formulas: hardcoded values, frontend Wilms-Oberfeld va.ts, backend Oklab.)
export interface EmotionColor {
  hex: string;
  label: string;
  emotion: string;
  v: number; // valence 0..1 (backend raw Oklab)
  a: number; // arousal 0..1 (backend raw Oklab)
}

// v/a = backend hsl_to_va (V33): valence Oklab-ridge-fit to ICEAS (r=0.97), arousal
// ridge-fit to ICEAS arousal norms (mean|err| 0.053). Regenerate after any colour→V-A change.
export const EMOTION_COLORS: EmotionColor[] = [
  { hex: '#BE0032', label: 'Đỏ',         emotion: 'Đam mê · Mãnh liệt',     v: 0.37, a: 0.62 },
  { hex: '#F38400', label: 'Cam',        emotion: 'Vui tươi · Năng động',   v: 0.60, a: 0.59 },
  { hex: '#F3C300', label: 'Vàng',       emotion: 'Vui vẻ · Lạc quan',      v: 0.77, a: 0.57 },
  { hex: '#FFB7C5', label: 'Hồng',       emotion: 'Ngọt ngào · Dịu dàng',   v: 0.68, a: 0.51 },
  { hex: '#008856', label: 'Xanh lá',    emotion: 'Tươi mát · Cân bằng',    v: 0.62, a: 0.48 },
  { hex: '#3AB09E', label: 'Ngọc',       emotion: 'Thư thái · Tươi mát',    v: 0.67, a: 0.39 },
  { hex: '#0067A5', label: 'Xanh dương', emotion: 'Phấn chấn · Sâu lắng',   v: 0.56, a: 0.47 },
  { hex: '#9C4F96', label: 'Tím',        emotion: 'Trầm tư · Mãnh liệt',    v: 0.46, a: 0.51 },
  { hex: '#F2F3F4', label: 'Trắng',      emotion: 'Thanh thản · Tinh khôi', v: 0.59, a: 0.33 },
  { hex: '#848482', label: 'Xám',        emotion: 'U hoài · Trầm lắng',     v: 0.41, a: 0.42 },
  { hex: '#80461B', label: 'Nâu',        emotion: 'Trầm mặc · Bất an',      v: 0.39, a: 0.60 },
  { hex: '#222222', label: 'Đen',        emotion: 'U tối · Nặng nề',        v: 0.25, a: 0.50 },
];
