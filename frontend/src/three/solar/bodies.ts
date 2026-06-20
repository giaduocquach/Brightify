// The 12 emotion colours mapped onto 12 celestial bodies (the Sun is the centre
// and is NOT one of the twelve). Body choice is driven by each planet's real
// true-colour appearance reconciled with the colour's emotion + V-A; orbit radius
// follows real solar distance so a two-planet journey reads as a believable flight.
// `hex` links each body back to an entry in data/colors.ts (EMOTION_COLORS) and is
// the key passed to the (unchanged) recommend flow — never reorder/relabel by it.
import { Vector3 } from 'three';

export type BodyKind = 'planet' | 'ringed' | 'moon';

// How the astronaut moves while exploring this body (see SurfaceRun dispatch). Optional —
// `locomotionFor()` derives a sensible default from kind/special so rows rarely need it.
export type LocomotionType = 'walk' | 'hop' | 'float' | 'ringwalk' | 'surf' | 'sink';

export interface BodyDef {
  hex: string;          // matches EMOTION_COLORS[].hex (recommend key)
  name: string;         // celestial name (vi)
  kind: BodyKind;
  orbitRadius: number;  // semi-major axis a (perihelion = a(1-e), aphelion = a(1+e))
  size: number;
  spinSpeed: number;    // self-rotation rad/s
  orbitSpeed: number;   // orbital angular speed rad/s (inner faster ≈ Kepler feel)
  phase: number;        // initial orbital angle (rad)
  inclination: number;  // small vertical tilt of the orbit
  axialTilt: number;    // self-rotation axis tilt (rad)
  texture?: string;     // /textures/<file> equirectangular map
  clouds?: string;      // optional cloud layer (Earth)
  night?: string;       // optional night-lights emissive map (Earth)
  bump?: string;        // optional bump map for surface relief (rocky bodies)
  ring?: string;        // optional ring texture (Saturn)
  parent?: string;      // hex of the body this orbits (Moon → Earth)
  eccentricity?: number; // orbit ellipticity
  special?: 'comet' | 'blackhole'; // procedural showpiece (overrides the textured sphere)
  locomotionType?: LocomotionType; // explore-movement override (else derived)
}

// Ordered by orbit radius (inner → outer). orbitSpeed ≈ 1.2 / r^1.5 (Kepler's third law
// feel). Spacing is set so NO body/ring/atmosphere overlaps at any orbital phase: Jupiter &
// Saturn trimmed, Saturn's ring contained (outer = size*2.0), outer planets spread out. The
// comet rides a visibly ECCENTRIC ellipse (perihelion just past Pluto); the black hole sits
// FAR out, near-stationary — an exotic object, not a planet on a tidy orbit.
export const BODIES: BodyDef[] = [
  { hex: '#848482', name: 'Sao Thuỷ',         kind: 'planet',    orbitRadius: 4.0,  size: 0.34, spinSpeed: 0.10, orbitSpeed: 0.150, phase: 0.4, inclination: 0.06, axialTilt: 0.01, eccentricity: 0.15, texture: '2k_mercury.jpg', bump: '2k_mercury.jpg' },
  { hex: '#F2F3F4', name: 'Sao Kim',          kind: 'planet',    orbitRadius: 5.4,  size: 0.50, spinSpeed: 0.06, orbitSpeed: 0.096, phase: 2.1, inclination: 0.03, axialTilt: 3.10, eccentricity: 0.01, texture: '2k_venus_atmosphere.jpg' },
  { hex: '#0067A5', name: 'Trái Đất',         kind: 'planet',    orbitRadius: 6.9,  size: 0.54, spinSpeed: 0.35, orbitSpeed: 0.066, phase: 3.7, inclination: 0.00, axialTilt: 0.41, eccentricity: 0.02, texture: '2k_earth_daymap.jpg', clouds: '2k_earth_clouds.jpg', night: '2k_earth_nightmap.jpg' },
  { hex: '#FFB7C5', name: 'Mặt Trăng',        kind: 'moon',      orbitRadius: 1.1,  size: 0.16, spinSpeed: 0.08, orbitSpeed: 0.620, phase: 5.2, inclination: 0.09, axialTilt: 0.12, eccentricity: 0.05, texture: '2k_moon.jpg', bump: '2k_moon.jpg', parent: '#0067A5' },
  { hex: '#BE0032', name: 'Sao Hoả',          kind: 'planet',    orbitRadius: 8.6,  size: 0.42, spinSpeed: 0.34, orbitSpeed: 0.048, phase: 1.1, inclination: 0.03, axialTilt: 0.44, eccentricity: 0.09, texture: '2k_mars.jpg', bump: '2k_mars.jpg' },
  { hex: '#F38400', name: 'Sao Mộc',          kind: 'planet',    orbitRadius: 12.0, size: 0.95, spinSpeed: 0.80, orbitSpeed: 0.029, phase: 4.4, inclination: 0.02, axialTilt: 0.05, eccentricity: 0.05, texture: '2k_jupiter.jpg' },
  { hex: '#F3C300', name: 'Sao Thổ',          kind: 'ringed',    orbitRadius: 17.0, size: 0.82, spinSpeed: 0.74, orbitSpeed: 0.017, phase: 0.9, inclination: 0.05, axialTilt: 0.47, eccentricity: 0.05, texture: '2k_saturn.jpg', ring: '2k_saturn_ring_alpha.png' },
  { hex: '#3AB09E', name: 'Sao Thiên Vương',  kind: 'planet',    orbitRadius: 22.0, size: 0.70, spinSpeed: 0.50, orbitSpeed: 0.012, phase: 3.0, inclination: 0.07, axialTilt: 1.71, eccentricity: 0.05, texture: '2k_uranus.jpg' },
  { hex: '#9C4F96', name: 'Sao Hải Vương',    kind: 'planet',    orbitRadius: 25.5, size: 0.68, spinSpeed: 0.48, orbitSpeed: 0.0093, phase: 5.7, inclination: 0.06, axialTilt: 0.49, eccentricity: 0.01, texture: '2k_neptune.jpg' },
  { hex: '#80461B', name: 'Sao Diêm Vương',   kind: 'planet',    orbitRadius: 29.0, size: 0.28, spinSpeed: 0.12, orbitSpeed: 0.0077, phase: 2.6, inclination: 0.18, axialTilt: 2.13, eccentricity: 0.05, texture: '2k_pluto.jpg', bump: '2k_pluto.jpg' },
  // Sao chổi (xanh lá #008856): coma huỳnh quang xanh (C₂). Quỹ đạo ELIP lệch tâm rõ —
  // perihelion ~32 (ngoài Pluto), aphelion ~64 — lượn từ xa vào, đúng đặc tính sao chổi.
  { hex: '#008856', name: 'Sao chổi',         kind: 'planet',    orbitRadius: 48.0, size: 0.26, spinSpeed: 0.40, orbitSpeed: 0.0055, phase: 4.0, inclination: 0.16, axialTilt: 0.07, eccentricity: 0.34, special: 'comet' },
  // Hố đen (#222222): RẤT XA, gần như đứng yên — vật thể bí ẩn, KHÔNG phải hành tinh.
  { hex: '#222222', name: 'Hố đen',           kind: 'planet',    orbitRadius: 70.0, size: 0.40, spinSpeed: 0.16, orbitSpeed: 0.0020, phase: 0.2, inclination: 0.10, axialTilt: 0.30, eccentricity: 0.05, special: 'blackhole' },
];

// Global multiplier on every body's orbital speed. Inner bodies otherwise visibly race around
// while the camera dwells; 0.6 calms the whole scene while preserving the Kepler-feel ratios
// (it's a single factor, so per-body relationships are mathematically untouched).
export const ORBIT_SCALE = 0.6;

export const SUN_SIZE = 2.4;
export const SUN_TEXTURE = '2k_sun.jpg';
export const MILKYWAY_TEXTURE = '4k_milkyway_panorama.jpg';
export const OUTER_RADIUS = BODIES[BODIES.length - 1].orbitRadius;
// Default camera so the inner/mid system frames nicely; comet + black hole sit far out
// (distant specks until you travel to them — the intended "remote abyss" feel).
export const CAMERA_START: [number, number, number] = [0, 18, 46];

export function bodyByHex(hex: string): BodyDef | undefined {
  return BODIES.find((b) => b.hex === hex);
}

// Position of a body on its (elliptical) orbit at time t — shared by CelestialBody (render)
// and SurfaceRun's surf handler (comet velocity = finite difference of this). Writes `out`.
export function orbitPosAt(def: BodyDef, t: number, out: Vector3, parent?: Vector3 | null): Vector3 {
  const ang = def.phase + t * def.orbitSpeed * ORBIT_SCALE;
  const e = def.eccentricity ?? 0;
  const r = e ? def.orbitRadius * (1 - e * e) / (1 + e * Math.cos(ang)) : def.orbitRadius;
  const cx = parent ? parent.x : 0;
  const cy = parent ? parent.y : 0;
  const cz = parent ? parent.z : 0;
  return out.set(cx + Math.cos(ang) * r, cy + Math.sin(ang * 1.3) * r * def.inclination, cz + Math.sin(ang) * r);
}

const GAS_GIANTS = new Set(['#F38400', '#3AB09E', '#9C4F96']); // Jupiter, Uranus, Neptune

// Default locomotion per body (explicit `locomotionType` overrides). Keeps SurfaceRun's
// dispatch data-driven so adding a body never needs a code change here.
export function locomotionFor(def: BodyDef): LocomotionType {
  if (def.locomotionType) return def.locomotionType;
  if (def.special === 'comet') return 'surf';
  if (def.special === 'blackhole') return 'sink';
  if (def.kind === 'ringed') return 'ringwalk';
  if (GAS_GIANTS.has(def.hex)) return 'float';
  if (def.kind === 'moon') return 'hop';
  return 'walk';
}
