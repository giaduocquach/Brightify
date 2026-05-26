# Brightify — Data Pipeline Documentation

> **Module**: `tools/pipeline.py` v9.0  
> **Phiên bản pipeline**: v12.0 (Spotify Artists + YTMusic Tracks)

---

## 1. Tổng Quan Pipeline

Pipeline dữ liệu Brightify gồm 7 giai đoạn, với **3 strict removal gates** đảm bảo chỉ dữ liệu hoàn chỉnh mới đi vào hệ thống.

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 0: PRE-FLIGHT (Backup + optional DB truncate)            │
├─────────────────────────────────────────────────────────────────┤
│  Phase 1: COLLECT                                               │
│  - Spotify artist discovery (BFS from seed artists)             │
│  - YTMusic Charts VN + Search + Explore                        │
│  → Output: checkpoints/phase1_spotify.csv                       │
│            checkpoints/phase1_artists.csv                       │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: FILTER                                                │
│  - Deduplication (by ISRC, track_id, name+artist fuzzy)         │
│  - Remove non-Vietnamese tracks                                 │
│  - Remove tracks missing required metadata                      │
│  → Output: checkpoints/phase2_filtered.csv                      │
│            logs/phase2_filter_report.md                         │
├─────────────────────────────────────────────────────────────────┤
│  Phase 3: DOWNLOAD                                              │
│  - 5-tier YouTube search (YTMusic → YT lyrics → YT MV → ...)   │
│  - Parallel download (configurable workers)                     │
│  - Audio fingerprint validation                                 │
│  → Output: music_files/*.mp3                                    │
│  ┌── GATE 3: Remove tracks without MP3 ─────────────────────┐  │
│  │  → checkpoints/phase3_downloaded.csv                      │  │
│  └──────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  Phase 4: LYRICS                                                │
│  - YTMusic lyrics → LRCLIB fallback                             │
│  - Support for synced (LRC) and plain lyrics                    │
│  → Output: checkpoints/phase4_lyrics.csv                        │
│  ┌── GATE 4: Remove tracks without lyrics ──────────────────┐  │
│  │  → checkpoints/phase4_lyrics_gated.csv                    │  │
│  └──────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  Phase 5: EXTRACT                                               │
│  - Essentia DSP: spectral, temporal, tonal features             │
│  - Essentia TF Models: arousal, mood tags, instrument tags      │
│  - Timbre brightness, voice gender classification               │
│  → Output: checkpoints/phase5_features.csv                      │
│  ┌── GATE 5: Remove tracks with incomplete features ────────┐  │
│  │  Essential: valence, energy, danceability, acousticness,  │  │
│  │             tempo, instrumentalness, speechiness,         │  │
│  │             loudness, key, mode                           │  │
│  └──────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  Phase 6: PROCESS                                               │
│  - Color mapping (Palmer et al. 2013 → HSL assignment)          │
│  - Sentiment analysis (Vietnamese lexicon + compound score)     │
│  - Mood quadrant classification (Russell circumplex)            │
│  - PhoBERT lyrics embeddings (768-dim)                          │
│  - Audio embeddings (Essentia TF)                               │
│  - Hybrid embedding fusion                                      │
│  → Output: data/vietnamese_music_processed_full.csv              │
│            data/vietnamese_music_embeddings_full.npy              │
│            data/embeddings_metadata.json                         │
├─────────────────────────────────────────────────────────────────┤
│  Phase 7: SEED                                                  │
│  - ETL: CSV → PostgreSQL (moods, artists, genres, albums,       │
│          songs, song_artists, embeddings)                       │
│  - Create HNSW index on song_embeddings                         │
│  - Create trigram indexes (pg_trgm)                             │
│  - Post-seed validation                                         │
│  → Output: PostgreSQL brightify_dw database                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Cách Sử Dụng

### Full Production Run
```bash
python -m tools.pipeline
```

### Test Mode (50 tracks)
```bash
python -m tools.pipeline --test-mode --limit 50
```

### Chạy 1 Phase
```bash
python -m tools.pipeline --phase 3         # Chỉ Phase 3 (Download)
```

### Resume từ Phase cụ thể
```bash
python -m tools.pipeline --from-phase 5    # Từ Phase 5 trở đi
```

### Skip Download
```bash
python -m tools.pipeline --skip-download   # Bỏ qua Phase 3
```

### Chỉ Backup
```bash
python -m tools.pipeline --preflight-only
```

### Reset DB trước khi chạy
```bash
python -m tools.pipeline --truncate-db
```

### Custom seed artists
```bash
python -m tools.pipeline --seed-file artists.txt --discovery-depth 2
```

### Full options
```bash
python -m tools.pipeline \
  --test-mode \
  --limit 100 \
  --truncate-db \
  --continue-on-error \
  --discovery-depth 2
```

---

## 3. Chi Tiết Từng Phase

### Phase 1: COLLECT (`tools/collect_data.py`)
- **Input**: Seed artists list / YTMusic Charts VN
- **Process**: 
  - Spotify API: Artist discovery (BFS traversal)
  - YTMusic API: Track metadata, charts, search
  - Merge & normalize metadata
- **Output**: `checkpoints/phase1_spotify.csv`, `checkpoints/phase1_artists.csv`
- **Resume**: `tracks_collected.json` cache

### Phase 2: FILTER (`tools/filter_data.py`)
- **Input**: `phase1_spotify.csv`
- **Process**:
  - ISRC deduplication
  - track_id deduplication
  - Name+Artist fuzzy matching dedup
  - Vietnamese language filter
  - Remove tracks missing: track_name, primary_artist
- **Output**: `phase2_filtered.csv`
- **Report**: `logs/phase2_filter_report.md`

### Phase 3: DOWNLOAD (`tools/download_music.py`)
- **Input**: `phase2_filtered.csv`
- **Process**:
  - 5-tier YouTube search strategy
  - Parallel download (configurable workers, default 8)
  - Audio fingerprint validation
  - Quality assessment: clean / has_extra / low
- **Output**: `music_files/*.mp3`
- **GATE**: Loại bài không có MP3 → `phase3_downloaded.csv`

### Phase 4: LYRICS
- **Input**: `phase3_downloaded.csv`
- **Process**:
  - YTMusic lyrics API
  - LRCLIB fallback
  - Support synced (LRC) + plain lyrics
- **Output**: `phase4_lyrics.csv`
- **GATE**: Loại bài không có lyrics → `phase4_lyrics_gated.csv`

### Phase 5: EXTRACT (`tools/extract_audio_features.py`)
- **Input**: `phase4_lyrics_gated.csv` + `music_files/*.mp3`
- **Process**:
  - Essentia DSP: spectral centroid, bandwidth, rolloff, MFCC
  - Essentia TF: DEAM arousal model, mood/theme classifier, instrument classifier
  - Timbre brightness computation
  - Voice gender classification
- **Output**: `phase5_features.csv`
- **GATE**: Loại bài thiếu essential features (10 features required)
- **Essential features**: valence, energy, danceability, acousticness, tempo, instrumentalness, speechiness, loudness, key, mode

### Phase 6: PROCESS (`tools/process_data.py`)
- **Input**: `phase5_features.csv`
- **Process**:
  - Audio → Color mapping (HSL via Palmer et al. 2013)
  - Vietnamese sentiment analysis
  - Mood quadrant assignment (Russell circumplex)
  - PhoBERT lyrics encoding (768-dim)
  - Audio embeddings (Essentia TF)
  - Feature normalization & fusion
- **Output**: 
  - `data/vietnamese_music_processed_full.csv`
  - `data/vietnamese_music_embeddings_full.npy`
  - `data/embeddings_metadata.json`

### Phase 7: SEED (`db/seed.py`)
- **Input**: All Phase 6 outputs + `data/artist_images.json`
- **Process**:
  1. Seed moods (Russell's 4 quadrants × 3 labels = 12 moods)
  2. Seed artists (bulk upsert, 500/batch)
  3. Seed genres (from artist genres) + artist-genre bridges
  4. Seed albums (bulk upsert)
  5. Seed songs (row-by-row with media availability check)
  6. Seed song-artist bridges
  7. Seed embeddings (768-dim vectors into pgvector)
  8. Create HNSW index (m=16, ef_construction=64)
  9. Create trigram indexes (pg_trgm)
  10. Post-seed validation

---

## 4. Checkpoint Files

| File | Phase | Mô tả | Approx Size |
|---|---|---|---|
| `tracks_collected.json` | 1 | Cache các tracks đã collect | 26 MB |
| `artists_discovered.json` | 1 | Cache các artists đã discover | 303 KB |
| `phase1_spotify.csv` | 1 | Raw collected tracks | 3.4 MB |
| `phase1_artists.csv` | 1 | Artist metadata | 64 KB |
| `phase2_filtered.csv` | 2 | Filtered & deduped tracks | 1.95 MB |
| `phase3_downloaded.csv` | 3 | Tracks with MP3 | 1.95 MB |
| `lyrics.json` | 4 | Lyrics cache | 29 MB |
| `phase4_lyrics.csv` | 4 | Tracks with lyrics | 30 MB |
| `phase5_features.csv` | 5 | Tracks with audio features | 31 MB |

---

## 5. Quality Gates

### Gate 3: MP3 Availability
```python
# Kiểm tra MP3 file tồn tại trong music_files/
mp3_files = {f.stem for f in MUSIC_DIR.glob("*.mp3")}
df = df[df["track_id"].astype(str).isin(mp3_files)]
```

### Gate 4: Lyrics Availability
```python
# Kiểm tra has_lyrics flag hoặc plain_lyrics not null
df = df[df["has_lyrics"] == True]
```

### Gate 5: Feature Completeness
```python
# 10 essential features phải không null
ESSENTIAL_FEATURES = [
    "valence", "energy", "danceability", "acousticness", "tempo",
    "instrumentalness", "speechiness", "loudness", "key", "mode",
]
null_mask = df[available].isnull().any(axis=1)
df = df[~null_mask]
```

---

## 6. Validation

### Phase Output Validation
Sau mỗi phase, pipeline tự động kiểm tra:
1. Output file tồn tại
2. Có thể đọc bằng pandas
3. Số rows ≥ 10 (MIN_ROWS)
4. Required columns tồn tại
5. `track_id` không có null

### Test Mode Validation
Sau khi pipeline hoàn tất (test mode), chạy:
1. Kiểm tra DB row counts (songs, embeddings, artists)
2. Verify mood quadrant distribution (Q1–Q4)
3. Sample embedding similarity query

### Post-Seed Validation
1. Row counts cho tất cả bảng
2. FK integrity (songs → albums, songs → artists)
3. Mood quadrant coverage (≥4 quadrants)
4. HNSW index active check

---

## 7. Configuration

| Variable | Default | Mô tả |
|---|---|---|
| `PIPELINE_PHASE_TIMEOUT` | 14400 (4h) | Timeout mỗi phase (seconds) |
| `DOWNLOAD_WORKERS` | 4 | Số workers download MP3 |
| `--limit` | None (prod), 50 (test) | Giới hạn số tracks |
| `--discovery-depth` | 1 | Độ sâu BFS cho artist discovery |
| `MIN_ROWS` | 10 | Minimum rows cho validation |
