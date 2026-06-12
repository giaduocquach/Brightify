// The 12 emotion colours mapped onto 12 celestial bodies (the Sun is the centre
// and is NOT one of the twelve). Body choice is driven by each planet's real
// true-colour appearance reconciled with the colour's emotion + V-A; orbit radius
// follows real solar distance so a two-planet journey reads as a believable flight.
// `hex` links each body back to an entry in data/colors.ts (EMOTION_COLORS) and is
// the key passed to the (unchanged) recommend flow — never reorder/relabel by it.

export type BodyKind = 'planet' | 'ringed' | 'moon' | 'comet' | 'blackhole';

export interface BodyDef {
  hex: string;          // matches EMOTION_COLORS[].hex (recommend key)
  name: string;         // celestial name (vi)
  kind: BodyKind;
  orbitRadius: number;
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
  eccentricity?: number; // orbit ellipticity (Kepler-ish: Mercury/Mars/Pluto/comet are eccentric)
}

// Ordered by orbit radius (inner → outer). orbitSpeed ≈ 1.2 / r^1.5 (Kepler's third
// law feel — inner bodies lap outer ones). Eccentricities mirror reality: Mercury,
// Mars, Pluto and the comet are visibly elliptical; the others nearly circular.
export const BODIES: BodyDef[] = [
  { hex: '#848482', name: 'Sao Thuỷ',         kind: 'planet',    orbitRadius: 4.0,  size: 0.34, spinSpeed: 0.10, orbitSpeed: 0.150, phase: 0.4, inclination: 0.06, axialTilt: 0.01, eccentricity: 0.21, texture: '2k_mercury.jpg', bump: '2k_mercury.jpg' },
  { hex: '#F2F3F4', name: 'Sao Kim',          kind: 'planet',    orbitRadius: 5.4,  size: 0.50, spinSpeed: 0.06, orbitSpeed: 0.110, phase: 2.1, inclination: 0.03, axialTilt: 3.10, eccentricity: 0.01, texture: '2k_venus_atmosphere.jpg' },
  { hex: '#0067A5', name: 'Trái Đất',         kind: 'planet',    orbitRadius: 6.9,  size: 0.54, spinSpeed: 0.35, orbitSpeed: 0.088, phase: 3.7, inclination: 0.00, axialTilt: 0.41, eccentricity: 0.02, texture: '2k_earth_daymap.jpg', clouds: '2k_earth_clouds.jpg', night: '2k_earth_nightmap.jpg' },
  { hex: '#FFB7C5', name: 'Mặt Trăng',        kind: 'moon',      orbitRadius: 1.1,  size: 0.16, spinSpeed: 0.08, orbitSpeed: 0.620, phase: 5.2, inclination: 0.09, axialTilt: 0.12, eccentricity: 0.05, texture: '2k_moon.jpg', bump: '2k_moon.jpg', parent: '#0067A5' },
  { hex: '#BE0032', name: 'Sao Hoả',          kind: 'planet',    orbitRadius: 8.6,  size: 0.42, spinSpeed: 0.34, orbitSpeed: 0.070, phase: 1.1, inclination: 0.03, axialTilt: 0.44, eccentricity: 0.09, texture: '2k_mars.jpg', bump: '2k_mars.jpg' },
  { hex: '#F38400', name: 'Sao Mộc',          kind: 'planet',    orbitRadius: 10.8, size: 1.05, spinSpeed: 0.80, orbitSpeed: 0.044, phase: 4.4, inclination: 0.02, axialTilt: 0.05, eccentricity: 0.05, texture: '2k_jupiter.jpg' },
  { hex: '#F3C300', name: 'Sao Thổ',          kind: 'ringed',    orbitRadius: 13.0, size: 0.92, spinSpeed: 0.74, orbitSpeed: 0.032, phase: 0.9, inclination: 0.05, axialTilt: 0.47, eccentricity: 0.05, texture: '2k_saturn.jpg', ring: '2k_saturn_ring_alpha.png' },
  { hex: '#3AB09E', name: 'Sao Thiên Vương',  kind: 'planet',    orbitRadius: 15.0, size: 0.70, spinSpeed: 0.50, orbitSpeed: 0.024, phase: 3.0, inclination: 0.07, axialTilt: 1.71, eccentricity: 0.05, texture: '2k_uranus.jpg' },
  { hex: '#9C4F96', name: 'Sao Hải Vương',    kind: 'planet',    orbitRadius: 16.8, size: 0.68, spinSpeed: 0.48, orbitSpeed: 0.019, phase: 5.7, inclination: 0.06, axialTilt: 0.49, eccentricity: 0.01, texture: '2k_neptune.jpg' },
  { hex: '#80461B', name: 'Sao Diêm Vương',   kind: 'planet',    orbitRadius: 18.4, size: 0.28, spinSpeed: 0.12, orbitSpeed: 0.014, phase: 2.6, inclination: 0.20, axialTilt: 2.13, eccentricity: 0.25 },
  { hex: '#008856', name: 'Sao Chổi Lục Bảo', kind: 'comet',     orbitRadius: 20.2, size: 0.30, spinSpeed: 0.60, orbitSpeed: 0.012, phase: 4.0, inclination: 0.42, axialTilt: 0.0, eccentricity: 0.45 },
  { hex: '#222222', name: 'Hố Đen',           kind: 'blackhole', orbitRadius: 22.5, size: 0.55, spinSpeed: 1.10, orbitSpeed: 0.008, phase: 0.2, inclination: 0.30, axialTilt: 0.5 },
];

export const SUN_SIZE = 2.4;
export const SUN_TEXTURE = '2k_sun.jpg';
export const MILKYWAY_TEXTURE = '2k_stars_milky_way.jpg';
export const OUTER_RADIUS = BODIES[BODIES.length - 1].orbitRadius;

export function bodyByHex(hex: string): BodyDef | undefined {
  return BODIES.find((b) => b.hex === hex);
}
