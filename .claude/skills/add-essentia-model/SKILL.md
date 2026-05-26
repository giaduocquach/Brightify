---
name: add-essentia-model
description: Add a new Essentia-TF pre-trained model to the audio feature extraction pipeline. Use when integrating new music analysis models like DEAM, timbre, approachability, or engagement classifiers.
---

# Add Essentia-TF Model to Pipeline

When adding a new Essentia-TF model to the project:

## Steps

1. **Download the model** (.pb file) to `models_cache/`:
   ```python
   # Models available at https://essentia.upf.edu/models.html
   # Download both the .pb (weights) and .json (metadata) files
   ```

2. **Add feature extraction** in `tools/extract_audio_features.py`:
   ```python
   from essentia.standard import MonoLoader, TensorflowPredict2D, TensorflowPredictEffnetDiscogs
   
   # Load embeddings from EffNet-Discogs backbone (already loaded)
   # Then run classifier on embeddings:
   model = TensorflowPredict2D(
       graphFilename='models_cache/<model-name>.pb',
       output='model/Softmax'  # Check .json metadata for correct output layer
   )
   predictions = model(embeddings)
   ```

3. **Add column to CSV** in the processing pipeline
4. **Add column to database** via Alembic migration:
   ```bash
   alembic revision -m "add_<feature>_column"
   ```
5. **Update `config.py`** if the feature needs weights or configuration
6. **Integrate into recommendation engine** (`core/recommendation_engine.py`)

## Available Essentia Models (already use EffNet-Discogs backbone)
- `deam-msd-musicnn` — Arousal/Valence regression [1,9]
- `emomusic-msd-musicnn` — Arousal/Valence regression [1,9]
- `timbre-discogs-effnet` — Bright/Dark classification
- `approachability_regression-discogs-effnet` — Approachability [0,1]
- `engagement_regression-discogs-effnet` — Engagement [0,1]
- `genre_discogs519` — 519 music styles including Nhạc Vàng

## Important Notes
- Check the `.json` metadata file for correct output layer name
- DEAM/emoMusic/MuSe models use MSD-MusiCNN backbone, not EffNet-Discogs
- V-A models output range [1,9] — normalize to [0,1] for consistency
- All Essentia models are CC BY-NC-SA 4.0 licensed
