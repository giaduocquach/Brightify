# Brightify — Production Data Architecture & Database Plan (V24)

> **Mục tiêu:** chốt kiến trúc data/runtime để deploy production **không đổi logic feature hiện tại**, đồng thời dọn rõ ranh giới giữa dữ liệu serving, dữ liệu DB, media, và artifact offline.
>
> **Ràng buộc bắt buộc:** không thay đổi business logic của `crossfade`, `recommend_by_color`, `recommend_by_song`, `lyrics`, `image`, hay API contract hiện tại.

---

## 1. Kết luận điều hành

Với code hiện tại, Brightify là hệ thống **file-first serving**:

- Catalog runtime được nạp từ file trong `data/`
- Audio runtime được đọc từ `music_files/`
- PostgreSQL **không** là source-of-truth cho recommendation catalog
- PostgreSQL hiện đóng vai trò:
  - health/availability probe
  - persistence mirror cho catalog
  - source bổ sung cho `Smart Crossfade` (`loudness_lufs`, `fade_out_cue_s`, `fade_in_cue_s`, `downbeat_times_json`)

Vì vậy, production đúng chuẩn cho hệ thống hiện tại phải tách làm 4 lớp:

1. **Serving release**: file runtime bất biến, mount read-only vào app
2. **Operational database**: PostgreSQL cho side-data có tính phục vụ vận hành
3. **Media storage**: MP3 và ảnh, không nằm trong DB
4. **Offline/archive storage**: artifact pipeline, backup, audit, checkpoint, dữ liệu lịch sử

Không được ép PostgreSQL thành source-of-truth cho recommendation khi app runtime vẫn đọc từ file; làm vậy sẽ tạo lệch giữa code và deployment.

---

## 2. Nguyên tắc thiết kế

1. **Không đổi logic feature**  
   Mọi đề xuất trong tài liệu này phải giữ nguyên hành vi runtime hiện tại.

2. **Serving phải bất biến và versioned**  
   App production phải chạy trên một bộ artifact đã khóa version, có manifest, checksum, và có thể rollback.

3. **Database chỉ giữ dữ liệu có lý do tồn tại trong DB**  
   Nếu dữ liệu không được query bởi runtime, không cần consistency transaction, không cần operational indexing, thì không nên ở PostgreSQL.

4. **Media không nằm trong DB**  
   MP3, JPG, ảnh nghệ sĩ phải ở filesystem/object storage, không ở `BYTEA`.

5. **Artifact pipeline không đi cùng runtime deploy**  
   `incremental_runs/`, `backups/`, audit CSV/MD, checkpoint thô không được đi cùng app production.

6. **Deploy hiện tại phải đi qua compatibility-first**  
   Vì code chưa refactor sang DB-first, production schema trước mắt phải tương thích với runtime hiện có. Normalize mạnh chỉ làm ở phase sau.

---

## 3. Dữ liệu nào là source-of-truth hiện tại

### 3.1 Source-of-truth cho runtime app

Các file sau là **nguồn sự thật để app chạy feature hiện tại**:

| Artifact | Vai trò |
|---|---|
| `data/vietnamese_music_processed_full.csv` | Catalog runtime chính |
| `data/vietnamese_music_embeddings_full.npy` | Lyrics embedding cho search/recommend |
| `data/embeddings_metadata.json` | Metadata lyrics embeddings |
| `data/mert_embeddings.npy` | MERT signal cho `recommend_by_song` |
| `data/mert_metadata.json` | Metadata MERT |
| `data/kg_embeddings.npy` | KG/content embedding |
| `data/emotion_labels_v5c.json` | Emotion/valence/arousal runtime |
| `music_files/*.mp3` | Audio serving và extractor input |
| `checkpoints/phase1_artists.csv` | Fallback artist thumbnails hiện còn được app đọc |

### 3.2 Side-data DB đang được runtime dùng thật

Các cột DB sau đang được app đọc khi startup:

| Table | Columns |
|---|---|
| `songs` | `track_id`, `loudness_lufs`, `fade_out_cue_s`, `fade_in_cue_s`, `downbeat_times_json` |

Ngoài ra:

| Phần | Vai trò |
|---|---|
| DB connection | `/api/health` probe |
| Redis | cache + rate limit |

### 3.3 Dữ liệu không phải source-of-truth runtime

Không nên xem các phần sau là runtime source:

- `genres`, `artist_genres`, `recommendations`, `search_logs`
- `music_files/download_log.json`
- `data/audio_embeddings.json`
- các file `emotion_labels_v2/v3/v4/v5/v5b.json`
- audit reports, summary markdown, quarantine output, incremental runs

---

## 4. Production storage layout

### 4.1 Lớp 1 — Serving release

Nơi lưu: filesystem hoặc object-mounted path, **read-only**

Ví dụ:

```text
/srv/brightify/releases/2026-06-07/
  manifest.json
  data/
    vietnamese_music_processed_full.csv
    vietnamese_music_embeddings_full.npy
    embeddings_metadata.json
    mert_embeddings.npy
    mert_metadata.json
    kg_embeddings.npy
    emotion_labels_v5c.json
  music_files/
    *.mp3
  checkpoints/
    phase1_artists.csv
```

Quy tắc:

- app chỉ đọc từ release đang active
- release phải có checksum
- rollback = trỏ symlink `current` về release cũ

### 4.2 Lớp 2 — Media storage

Ngắn hạn, tương thích ngay:

- `music_files/` để ngoài image, mount `:ro`
- `album_art/`, `artist_images/` chỉ mount nếu có dữ liệu thật

Trung hạn:

- chuyển MP3/JPG sang object storage + CDN
- DB chỉ lưu storage key / URL, không lưu binary

### 4.3 Lớp 3 — Operational database

Nơi lưu: PostgreSQL data directory / managed Postgres

Chỉ nên giữ:

- metadata có tính relational
- side-data cần query/index/transaction
- serving crossfade columns
- optional pgvector khi thực sự dùng DB-native retrieval

### 4.4 Lớp 4 — Offline/archive

Nơi lưu: archive volume hoặc object storage riêng

Bao gồm:

- `backups/`
- `incremental_runs/`
- `var/runtime/backtest/`
- artifact evaluation / audit / quarantine
- checkpoint pipeline cũ

Không mount lớp này vào app production.

---

## 5. Docker database nên chứa gì

### 5.1 Nên để trong Docker DB / Postgres production

**Bắt buộc cho compatibility hiện tại:**

- `songs`
- `song_embeddings`
- `artists`
- `albums`
- `song_artists`
- `moods`
- `alembic_version`

**Tùy chọn giữ tạm thời vì compatibility hoặc migration path:**

- `genres`
- `artist_genres`
- `recommendations`
- `search_logs`

### 5.2 Không nên để trong Docker DB

- MP3
- JPG/PNG album art
- artist image binary
- pipeline checkpoints
- backup JSON/CSV/NPY
- offline audit reports
- `download_log.json`
- quarantine folders
- historical label versions

### 5.3 Không nên bake vào image app

- `backups/`
- `incremental_runs/`
- `var/runtime/backtest/`
- large audit CSV/MD
- unused label/history files

---

## 6. Database design cho production hiện tại: compatibility schema

Do app hiện tại còn đọc ORM/seed/schema cũ, **deploy production ngay bây giờ không nên drop schema mạnh**. Thay vào đó:

### 6.1 Mục tiêu của compatibility schema

1. App hiện tại khởi động không đổi code
2. Smart Crossfade hydrate từ DB vẫn chạy
3. Seed pipeline hiện tại vẫn có chỗ ghi
4. Có thể migrate sang normalized schema sau mà không gãy runtime

### 6.2 Bảng giữ lại ở compatibility phase

| Table | Giữ | Lý do |
|---|---|---|
| `songs` | Có | runtime crossfade + seed compatibility |
| `song_embeddings` | Có | seed/validation compatibility |
| `artists` | Có | seed + artist metadata |
| `albums` | Có | FK + metadata |
| `song_artists` | Có | artist relations |
| `moods` | Có | current seed compatibility |
| `alembic_version` | Có | migration tracking |

### 6.3 Bảng nên đánh dấu deprecated

| Table | Trạng thái |
|---|---|
| `genres` | deprecated |
| `artist_genres` | deprecated |
| `recommendations` | deprecated |
| `search_logs` | deprecated |

Ở phase deploy đầu tiên, **không cần xóa ngay**. Chỉ cần:

- ngừng xem chúng là runtime dependency
- không xây thêm logic mới dựa trên các bảng này
- lên migration drop ở phase cleanup sau

### 6.4 Cột trong `songs` nên coi là active

#### Core identity / catalog

- `track_id`
- `track_name`
- `album_id`
- `primary_artist_id`
- `primary_artist_name`
- `duration_ms`
- `explicit`
- `popularity`

#### Audio / ML / affect đang còn ý nghĩa runtime hoặc data science

- `danceability`
- `energy`
- `key`
- `loudness`
- `mode`
- `speechiness`
- `acousticness`
- `instrumentalness`
- `liveness`
- `valence`
- `tempo`
- `time_signature`
- `arousal`
- `timbre_bright`
- `mood_tags`
- `instrument_tags`
- `voice_gender`
- `voice_gender_confidence`
- `plain_lyrics`
- `synced_lyrics`
- `lyrics_cleaned`
- `lrclib_id`
- `has_lyrics`
- `instrumental`
- `color_hue`
- `color_saturation`
- `color_lightness`
- `color_hex`
- `sentiment_compound`
- `sentiment_positive`
- `sentiment_neutral`
- `sentiment_negative`
- `sentiment_category`
- `mood_score`
- `mood_quadrant`
- `dance_score`
- `acoustic_score`
- `combined_positivity`
- `energy_level`
- `tempo_category`
- `has_mp3`
- `mp3_filename`
- `has_art`
- `image_url_large`
- `image_url_medium`
- `image_url_small`
- `loudness_lufs`
- `fade_out_cue_s`
- `fade_in_cue_s`
- `downbeat_times_json`

### 6.5 Cột nên đánh dấu legacy / prepare-to-drop

Các cột sau đang stale, rỗng, hoặc không còn logic runtime tiêu thụ:

- `ytmusic_video_id`
- `audio_feature_source`
- `valence_estimated`
- `ytmusic_thumbnail_url`
- `lyrics_source`
- `genre_tags`
- `audio_fingerprint`
- `thumbnail_url`
- `preview_url`
- `available_markets_count`
- `isrc`
- `track_number`
- `disc_number`
- `mp3_path`
- `mp3_source`
- `mp3_duration_s`
- `mp3_quality`
- `youtube_music_id`
- `youtube_id`

**Quan trọng:** vì app/seed hiện còn biết tới một phần các cột này, phase 1 production chỉ gắn nhãn deprecated. Drop vật lý làm ở phase cleanup sau khi migration xong.

---

## 7. Database design mục tiêu sau này: normalized serving schema

Schema đích đúng chuẩn hơn, chỉ nên làm **sau khi app được refactor khỏi God-table**.

### 7.1 Bảng lõi

#### `artists`

- `artist_id`
- `name`
- `followers`
- `popularity`
- `image_url`
- `has_image`
- `created_at`
- `updated_at`

#### `albums`

- `album_id`
- `name`
- `album_type`
- `release_date`
- `release_year`
- `total_tracks`
- `image_url_large`
- `image_url_medium`
- `image_url_small`

#### `songs`

- `track_id`
- `track_name`
- `album_id`
- `primary_artist_id`
- `primary_artist_name`
- `duration_ms`
- `explicit`
- `popularity`
- `created_at`
- `updated_at`

#### `song_artists`

- `track_id`
- `artist_id`
- `is_primary`

### 7.2 Feature tables

#### `song_text_features`

- `track_id`
- `plain_lyrics`
- `lyrics_cleaned`
- `synced_lyrics`
- `lrclib_id`
- `has_lyrics`
- `instrumental`

#### `song_audio_features`

- `track_id`
- `danceability`
- `energy`
- `key`
- `loudness`
- `mode`
- `speechiness`
- `acousticness`
- `instrumentalness`
- `liveness`
- `valence`
- `tempo`
- `time_signature`

#### `song_ml_features`

- `track_id`
- `arousal`
- `timbre_bright`
- `mood_tags JSONB`
- `instrument_tags JSONB`
- `voice_gender`
- `voice_gender_confidence`

#### `song_affect_features`

- `track_id`
- `color_hue`
- `color_saturation`
- `color_lightness`
- `color_hex`
- `sentiment_compound`
- `sentiment_positive`
- `sentiment_neutral`
- `sentiment_negative`
- `sentiment_category`
- `mood_score`
- `mood_quadrant`
- `dance_score`
- `acoustic_score`
- `combined_positivity`
- `energy_level`
- `tempo_category`

#### `song_mix_features`

- `track_id`
- `loudness_lufs`
- `fade_out_cue_s`
- `fade_in_cue_s`
- `downbeat_times_json JSONB`

#### `song_media_assets`

- `track_id`
- `has_mp3`
- `audio_storage_key`
- `album_art_storage_key`
- `artist_image_storage_key`
- `image_url_large`
- `image_url_medium`
- `image_url_small`

### 7.3 Embedding table

#### `song_embeddings`

- `track_id`
- `lyrics_embedding vector(768)` hoặc `embedding vector(768)`
- `mert_embedding vector(768)` nếu thực sự dùng DB-native
- `kg_embedding vector(64)` nếu thực sự dùng DB-native
- `embedding_version`
- `created_at`

### 7.4 Release governance

#### `catalog_releases`

- `release_id`
- `version`
- `manifest_sha256`
- `created_at`
- `is_active`
- `notes`

Mục đích:

- ràng buộc rõ app đang chạy release dữ liệu nào
- giúp audit rollback
- tránh tình trạng file runtime và DB drift không kiểm soát

---

## 8. File/folder nào nên giữ, chuyển, bỏ

### 8.1 Giữ trong production runtime

| Path | Giữ |
|---|---|
| `data/vietnamese_music_processed_full.csv` | Có |
| `data/vietnamese_music_embeddings_full.npy` | Có |
| `data/embeddings_metadata.json` | Có |
| `data/mert_embeddings.npy` | Có |
| `data/mert_metadata.json` | Có |
| `data/kg_embeddings.npy` | Có |
| `data/emotion_labels_v5c.json` | Có |
| `music_files/*.mp3` | Có |
| `checkpoints/phase1_artists.csv` | Có, vì app còn fallback |

### 8.2 Giữ ngoài runtime nhưng còn hữu ích cho vận hành

| Path | Vai trò |
|---|---|
| `data/crossfade_features.json` | repair/backfill artifact |
| `var/runtime/trained_models/` | model output nếu có |
| `var/runtime/annotations/` | annotation asset |

### 8.3 Chuyển sang archive/offline

| Path/pattern | Lý do |
|---|---|
| `backups/` | archival only |
| `incremental_runs/` | pipeline working trees |
| `var/runtime/backtest/` | offline evaluation only |
| `data/catalog_*` reports | audit only |
| `data/filtered_out_tracks_*` | audit only |
| `data/duplicate_clusters_*` | audit only |
| `data/*audit*.csv` | audit only |
| `data/*summary*.md` | audit only |
| `data/*.bak.csv` | history only |
| `data/*.bak.npy` | history only |
| `data/audio_embeddings.json` | pipeline helper, not runtime |
| `data/lyrics_backup.json` | pipeline helper, not runtime |
| `data/emotion_labels_v2.json` | lineage only |
| `data/emotion_labels_v3.json` | lineage only |
| `data/emotion_labels_v4.json` | lineage only |
| `data/emotion_labels_v5.json` | lineage only after `v5c` freeze |
| `data/emotion_labels_v5b.json` | lineage only |
| `data/arousal_v2.json` | lineage only |
| `data/arousal_v3.json` | lineage only |
| `music_files/download_log.json` | pipeline provenance, not runtime |

### 8.4 Có thể xóa khỏi runtime deploy context ngay

| Path/pattern | Ghi chú |
|---|---|
| `music_files/*.part` | downloader residue |
| `music_files/*.ytdl` | downloader residue |
| `music_files/*.part-Frag*` | downloader residue |

---

## 9. Thứ tự migration/cleanup an toàn

### Phase 1 — Production freeze without feature changes

1. Freeze serving release
2. Tạo `manifest.json` + checksum
3. Mount serving release read-only vào app
4. Giữ DB schema compatibility hiện tại
5. Archive artifact offline, không xóa mù

### Phase 2 — Schema governance

1. Sửa `alembic_version` drift
2. Chụp inventory cột active vs deprecated
3. Đánh dấu deprecated trong docs/migration notes
4. Ngừng sinh dữ liệu vào các cột/bảng deprecated

### Phase 3 — Runtime cleanup

1. Loại artifact offline khỏi build/deploy context
2. Tách backup/incremental khỏi app host path
3. Verify smoke test trên mount production

### Phase 4 — Optional future normalization

1. Refactor app đọc qua repository/service layer
2. Chuyển crossfade và serving metadata sang schema normalized
3. Drop vật lý bảng/cột deprecated

---

## 10. Quyết định chốt

### 10.1 Chốt cho production hiện tại

- **File serving release là source-of-truth**
- **PostgreSQL là operational side-store**
- **MP3 và ảnh ở filesystem/object storage**
- **Artifact pipeline ở archive**

### 10.2 Không nên làm ngay

- ép feature hiện tại sang DB-first
- normalize schema mạnh rồi drop hàng loạt trước khi app đổi
- xóa trực tiếp artifact mà không chụp manifest/backup

### 10.3 Nên làm ngay trước deploy

- chốt serving release
- chuẩn hóa docs theo đúng runtime hiện tại
- tách build/deploy context khỏi artifact offline
- audit và sửa migration drift

---

## 11. Tài liệu liên quan

- [PLAN_DOCKERIZATION.md](./PLAN_DOCKERIZATION.md)
- [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)
- [DATA_PIPELINE.md](./DATA_PIPELINE.md)
- [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)
