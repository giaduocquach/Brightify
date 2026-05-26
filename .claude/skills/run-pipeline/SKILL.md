---
name: run-pipeline
description: Run the Brightify data pipeline or specific phases. Use when collecting, filtering, downloading, extracting features, processing, or seeding music data.
disable-model-invocation: true
---

# Run Brightify Data Pipeline

Run the data pipeline. Specify a phase or run all phases.

## Full pipeline
```bash
cd /Users/admin/Projects/Brightify
source .venv/bin/activate
python -m tools.pipeline
```

## Individual phases
```bash
# Phase 1: Collect tracks from YouTube Music
python -m tools.collect_data

# Phase 2: Filter Vietnamese tracks
python -m tools.filter_data

# Phase 3: Download MP3s
python -m tools.download_music

# Phase 5: Extract audio features
python -m tools.extract_audio_features

# Phase 6: Process embeddings
python -m tools.process_data

# Phase 7: Seed database
python -m db.seed
```

## Arguments
$ARGUMENTS

If a specific phase is mentioned, run only that phase. Otherwise, provide guidance on which phase to run based on the context.

## Checkpoints
Pipeline state is saved in `checkpoints/`. If a phase fails, it can be resumed from the last checkpoint.
