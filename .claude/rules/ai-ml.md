---
paths:
  - "core/**/*.py"
  - "config.py"
---

# AI/ML Module Rules

## Models
- PhoBERT: `vinai/phobert-base` (768-dim embeddings). Model name is set in `config.py` as `PHOBERT_MODEL`.
- CLIP: `openai/clip-vit-base-patch32`. Pre-compute text embeddings for all prompt categories.
- Essentia: EffNet-Discogs backbone. Models are in `models_cache/`.

## Emotion System
- 13 emotion categories: happiness, sadness, anger, fear, surprise, disgust, love, hope, nostalgia, loneliness, pride, gratitude, calm
- Russell's Circumplex: valence (positive/negative) × arousal (high/low energy)
- Audio V-A fusion: 60% audio features + 40% lyrics analysis
- Vietnamese Emotion Lexicon: 730+ words including Gen-Z slang, Southern/Central variants

## Recommendation Engine
- 7-signal multimodal fusion: timbral + rhythmic + tonal + lyrics embeddings + V-A + emotion vectors + mood boost
- Timbral/rhythmic/tonal decomposition per Berenzweig et al. 2004
- Artist diversity via `_fast_rank()` — avoid repeating same artist in recommendations
- Iso-Principle for emotion journey playlists (Altshuler 1948, Davis & Thaut 1989)

## Color Mapping
- CIEDE2000 perceptual distance (CIE 2001) via colormath
- References: Jonauskaite et al. 2020, Palmer et al. 2013
- Graceful fallback to RGB Euclidean when colormath unavailable

## Performance
- Pre-compute features at startup in `_precompute_all_features()`
- Use NumPy vectorized operations for similarity calculations
- PhoBERT embedding generation is CPU-bottlenecked — use batch processing
