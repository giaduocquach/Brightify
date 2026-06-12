// Typed client for the existing FastAPI backend. Contract unchanged.

export interface WhyExplanation {
  reason?: string;
  top_signal?: string;
  song_emotion_vi?: string;
  [k: string]: unknown;
}

export interface Song {
  song_index: number;
  track_id: string;
  track_name: string;
  artist: string;
  album_name: string;
  color_hex: string;
  valence: number;
  arousal: number;
  energy: number;
  has_audio: boolean;
  has_album_art: boolean;
  album_art_url: string | null;
  why: WhyExplanation | null;
  // Optional audio features used by smart crossfade (absent → graceful fallback).
  tempo?: number;
  loudness?: number;
  mode?: number;
  key?: number;
  danceability?: number;
  duration_ms?: number;
}

interface RawSong {
  song_index?: number;
  original_index?: number;
  track_id?: string;
  track_name?: string;
  artist?: string;
  primary_artist?: string;
  artists?: string;
  album_name?: string;
  color_hex?: string;
  valence?: number;
  arousal?: number;
  energy?: number;
  has_audio?: boolean;
  has_album_art?: boolean;
  album_art_url?: string | null;
  thumbnail_url?: string | null;
  why?: WhyExplanation | null;
  tempo?: number;
  loudness?: number;
  mode?: number;
  key?: number;
  danceability?: number;
  track_duration_ms?: number;
}

export interface ColorMood {
  hex: string;
  mood: string;
}
export interface ColorResult {
  results: Song[];
  journey: { from: ColorMood; to: ColorMood } | null;
  bridge: Array<{ hex: string; emotion_vi: string; valence: number; arousal: number }> | null;
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/;
function safeColor(hex?: string): string {
  return hex && HEX_RE.test(hex) ? hex : '#a78bfa';
}

export function normalizeSong(r: RawSong): Song {
  let art = r.album_art_url || r.thumbnail_url || null;
  if (art) art = art.replace(/=w\d+-h\d+-/, '=w226-h226-');
  return {
    song_index: r.song_index ?? r.original_index ?? 0,
    track_id: r.track_id || '',
    track_name: r.track_name || 'Unknown',
    artist: r.artist || r.primary_artist || r.artists || 'Unknown',
    album_name: r.album_name || '',
    color_hex: safeColor(r.color_hex),
    valence: r.valence ?? 0.5,
    arousal: r.arousal ?? 0.5,
    energy: r.energy ?? 0.5,
    has_audio: r.has_audio || false,
    has_album_art: r.has_album_art || !!r.thumbnail_url,
    album_art_url: art,
    why: r.why ?? null,
    tempo: r.tempo,
    loudness: r.loudness,
    mode: r.mode,
    key: r.key,
    danceability: r.danceability,
    duration_ms: r.track_duration_ms,
  };
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
  return res.json() as Promise<T>;
}
async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail || `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async recommendByColor(
    colors: string[],
    topK = 12,
    diversityPenalty = 0.15,
    novelty = 0.5,
  ): Promise<ColorResult> {
    const data = await postJSON<{
      results: RawSong[];
      query?: { journey?: ColorResult['journey']; bridge?: ColorResult['bridge'] };
    }>('/api/recommend/color', {
      colors,
      top_k: topK,
      diversity_penalty: diversityPenalty,
      novelty,
    });
    return {
      results: (data.results || []).map(normalizeSong),
      journey: data.query?.journey ?? null,
      bridge: data.query?.bridge ?? null,
    };
  },

  async getSimilar(songId: number | string, count = 12): Promise<Song[]> {
    const data = await getJSON<{ songs?: RawSong[]; results?: RawSong[]; similar?: RawSong[] }>(
      `/api/song/${songId}/similar?count=${count}`,
    );
    return (data.songs || data.results || data.similar || []).map(normalizeSong);
  },

  async batchAudioStatus(trackIds: string[]): Promise<Record<string, boolean>> {
    if (!trackIds.length) return {};
    const data = await getJSON<{ status?: Record<string, boolean> }>(
      `/api/audio/batch-status?track_ids=${trackIds.join(',')}`,
    );
    return data.status || {};
  },

  streamUrl: (trackId: string) => `/api/audio/stream/${trackId}`,
  albumArtUrl: (trackId: string) => `/api/album-art/${trackId}`,
};
