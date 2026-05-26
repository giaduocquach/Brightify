---
name: debug-recommendation
description: Debug the recommendation engine when recommendations seem wrong, irrelevant, or when similarity scores are unexpected. Use when troubleshooting music recommendations.
---

# Debug Recommendation Engine

## Quick Health Check

```bash
cd /Users/admin/Projects/Brightify
source .venv/bin/activate
python -c "
from core.recommendation_engine import get_recommender
r = get_recommender()
print(f'Songs loaded: {len(r.df)}')
print(f'Embeddings shape: {r.embeddings_matrix.shape if r.embeddings_matrix is not None else \"None\"}')
print(f'Pre-computed features: {list(r.song_va.keys())[:5] if hasattr(r, \"song_va\") else \"Not loaded\"}')
"
```

## Common Issues

### 1. V-A Mismatch
Check emotion analysis for a specific song:
```python
from core.emotion_analysis import get_emotion_classifier
ec = get_emotion_classifier()
result = ec.analyze("lyrics text here")
print(f"Valence: {result['valence']}, Arousal: {result['arousal']}")
print(f"Emotions: {result['emotions']}")
```

### 2. Embedding Similarity Check
```python
import numpy as np
# Compare two songs' embeddings
sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
print(f"Cosine similarity: {sim}")
```

### 3. Signal Weight Analysis
Check `config.py` for current weights:
- WEIGHT_AUDIO_FEATURES (timbral + rhythmic + tonal)
- WEIGHT_LYRICS_EMBEDDING
- WEIGHT_VA_DISTANCE
- WEIGHT_EMOTION_OVERLAP
- WEIGHT_MOOD_BOOST

### 4. Color Mapping Debug
```python
from core.advanced_color_mapping import get_color_mapper
cm = get_color_mapper()
result = cm.get_emotion_for_color("#FF5733")
print(result)
```

## Key Files
- `core/recommendation_engine.py` — Main recommender (~1,810 lines)
- `core/emotion_analysis.py` — Emotion detection (~510 lines)
- `core/advanced_color_mapping.py` — Color-emotion mapping (~480 lines)
- `core/image_analysis.py` — CLIP image analysis (~850 lines)
- `config.py` — All weights and thresholds

$ARGUMENTS
