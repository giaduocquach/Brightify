// Resolve a texture file name (e.g. '2k_mars.jpg') to its Vite-hashed asset URL.
// Textures live in src/assets/textures so Vite emits them under /assets — which the
// FastAPI backend already serves — instead of needing a new static route.
const MODS = import.meta.glob('../../assets/textures/*.{jpg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>;

export function textureUrl(file: string): string {
  for (const key in MODS) {
    if (key.endsWith('/' + file)) return MODS[key];
  }
  throw new Error(`texture not found: ${file}`);
}
