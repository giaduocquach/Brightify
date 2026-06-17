// Registry of high-res (4K) day maps available for on-demand LOD, keyed by emotion hex.
// Files live in public/textures4k/ → copied unhashed to static_spa/ by Vite, fetched by
// stable URL at runtime (NOT bundled). Only bodies with real surface detail are listed;
// Venus/Uranus/Neptune/Moon/Pluto stay 2K (featureless and/or no worthwhile 8K source).
export const HI_RES_MAP: Readonly<Record<string, string>> = {
  '#848482': '/textures4k/4k_mercury.jpg',     // Mercury
  '#0067A5': '/textures4k/4k_earth_daymap.jpg', // Earth
  '#BE0032': '/textures4k/4k_mars.jpg',         // Mars
  '#F38400': '/textures4k/4k_jupiter.jpg',      // Jupiter
  '#F3C300': '/textures4k/4k_saturn.jpg',       // Saturn
};

export const hasHiRes = (hex: string): boolean => hex in HI_RES_MAP;
