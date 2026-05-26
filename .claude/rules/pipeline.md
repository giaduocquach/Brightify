---
paths:
  - "tools/**/*.py"
---

# Data Pipeline Rules

## 7-Phase Pipeline (`tools/pipeline.py`)
1. **collect** — YouTube Music artist/track discovery via ytmusicapi
2. **filter** — Vietnamese-only deduplication (diacritics, language detection)
3. **download** — MP3 download via yt-dlp with 5-tier fallback search
4. **lyrics** — Lyrics fetching (ytmusicapi)
5. **features** — Essentia-TF audio feature extraction + librosa DSP
6. **process** — PhoBERT embedding generation + feature engineering
7. **seed** — CSV→PostgreSQL via db/seed.py

## Strict Gates
- Each phase validates output before next phase can proceed
- Checkpoints in `checkpoints/` for resumable runs
- Phase outputs are cumulative CSV files

## Vietnamese-Specific
- Language detection for filtering Vietnamese tracks
- Diacritics handling and transliteration for matching
- Artist name normalization for Vietnamese artists

## Audio Files
- MP3 files: `music_files/`
- Album art: `album_art/`
- Artist images: `artist_images/`
- ML model cache: `models_cache/`
