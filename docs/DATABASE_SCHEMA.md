# Brightify — Database Schema Documentation

> **DBMS**: PostgreSQL 17  
> **Extensions**: pgvector, pg_trgm  
> **ORM**: SQLAlchemy 2.0  
> **Migrations**: Alembic

---

## 1. Entity Relationship Diagram

```mermaid
erDiagram
    ARTISTS ||--o{ SONG_ARTISTS : "has"
    ARTISTS ||--o{ ARTIST_GENRES : "belongs to"
    ALBUMS ||--o{ SONGS : "contains"
    MOODS ||--o{ SONGS : "classified as"
    GENRES ||--o{ ARTIST_GENRES : "categorizes"
    SONGS ||--o{ SONG_ARTISTS : "performed by"
    SONGS ||--o| SONG_EMBEDDINGS : "has embedding"
    SONGS ||--o{ RECOMMENDATIONS : "recommended as"

    ARTISTS {
        string artist_id PK "Spotify ID"
        string name "Indexed (GIN trgm)"
        json genres "Genre list"
        int followers
        smallint popularity
        text image_url
        bool has_image
        timestamp created_at
        timestamp updated_at
    }

    ALBUMS {
        string album_id PK "Spotify ID"
        string name
        string album_type "album|single|compilation"
        string release_date "YYYY or YYYY-MM-DD"
        smallint release_year "Indexed"
        smallint total_tracks
        text image_url_large
        text image_url_medium
        text image_url_small
    }

    GENRES {
        int genre_id PK "Auto-increment"
        string name UK "Unique, indexed"
    }

    MOODS {
        int mood_id PK "Auto-increment"
        string quadrant "Q1-Q4"
        string quadrant_name "e.g. Happy/Excited"
        string mood_label UK "e.g. happy, calm"
        float valence_center
        float energy_center
    }

    SONGS {
        string track_id PK "Spotify ID"
        string track_name "Indexed (GIN trgm)"
        string album_id FK
        string primary_artist_id FK
        string primary_artist_name
        string isrc
        smallint popularity "Indexed"
        int duration_ms
        bool explicit
        float danceability
        float energy
        float valence
        float tempo
        float arousal "DEAM model"
        float timbre_bright
        text plain_lyrics
        text lyrics_cleaned
        string color_hex "Indexed"
        string mood_quadrant "Indexed"
        int mood_id FK
        float sentiment_compound
        bool has_mp3
        bool has_lyrics "Indexed"
        bool has_art
    }

    SONG_ARTISTS {
        int id PK
        string track_id FK
        string artist_id FK
        bool is_primary
    }

    ARTIST_GENRES {
        int id PK
        string artist_id FK
        int genre_id FK
    }

    SONG_EMBEDDINGS {
        string track_id PK_FK
        vector embedding "768-dim, HNSW indexed"
        string model_name "vinai/phobert-base"
    }

    RECOMMENDATIONS {
        bigint id PK
        string track_id FK
        string rec_type "color|mood|lyrics|image|context|dna|radio"
        float similarity_score
        smallint rank_position
        json query_params
        bool was_played
        bool was_liked
        timestamp recommended_at "Indexed"
    }

    SEARCH_LOGS {
        bigint id PK
        string query
        int result_count
        timestamp searched_at "Indexed"
    }
```

---

## 2. Bảng Chi Tiết

### 2.1. `songs` — Bảng Trung Tâm (72 cột)

Bảng `songs` là entity chính, chứa toàn bộ metadata, audio features, lyrics, processed features.

#### Nhóm cột:

**Spotify Metadata**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `track_id` | VARCHAR(64) PK | Spotify track ID |
| `track_name` | VARCHAR(512) | Tên bài hát |
| `album_id` | VARCHAR(64) FK | → albums.album_id |
| `primary_artist_id` | VARCHAR(64) FK | → artists.artist_id |
| `primary_artist_name` | VARCHAR(512) | Tên nghệ sĩ chính |
| `isrc` | VARCHAR(16) | International Standard Recording Code |
| `track_number` | SMALLINT | Số thứ tự trong album |
| `disc_number` | SMALLINT | Số đĩa |
| `popularity` | SMALLINT | Spotify popularity (0–100) |
| `duration_ms` | INT | Thời lượng (ms) |
| `explicit` | BOOL | Nội dung 18+ |
| `track_url` | TEXT | Spotify URL |
| `preview_url` | TEXT | 30s preview URL |
| `available_markets_count` | SMALLINT | Số thị trường khả dụng |

**Album Art**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `image_url_large` | TEXT | 640x640 |
| `image_url_medium` | TEXT | 300x300 |
| `image_url_small` | TEXT | 64x64 |
| `has_art` | BOOL | Có ảnh album art |

**Audio Features (Spotify/ReccoBeats)**:
| Cột | Kiểu | Range | Mô tả |
|---|---|---|---|
| `danceability` | FLOAT | 0.0–1.0 | Khả năng nhảy |
| `energy` | FLOAT | 0.0–1.0 | Năng lượng |
| `key` | SMALLINT | 0–11 | Tone nhạc (C=0, C#=1, ...) |
| `loudness` | FLOAT | -60–0 dB | Âm lượng trung bình |
| `mode` | SMALLINT | 0/1 | Minor=0, Major=1 |
| `speechiness` | FLOAT | 0.0–1.0 | Tỷ lệ giọng nói |
| `acousticness` | FLOAT | 0.0–1.0 | Tính acoustic |
| `instrumentalness` | FLOAT | 0.0–1.0 | Tính instrumental |
| `liveness` | FLOAT | 0.0–1.0 | Live performance probability |
| `valence` | FLOAT | 0.0–1.0 | Tích cực/Tiêu cực |
| `tempo` | FLOAT | BPM | Nhịp độ |
| `time_signature` | SMALLINT | 3–7 | Nhịp nhạc |
| `has_audio_features` | BOOL | | Có đủ audio features |

**ML-Predicted Features (Essentia)**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `arousal` | FLOAT | DEAM arousal (0–1) |
| `timbre_bright` | FLOAT | Timbre brightness (0=dark, 1=bright) |
| `mood_tags` | JSON | MTG-Jamendo mood/theme predictions |
| `instrument_tags` | JSON | MTG-Jamendo instrument predictions |
| `voice_gender` | VARCHAR(16) | male / female |
| `voice_gender_confidence` | FLOAT | Gender classifier confidence |

**Lyrics**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `lrclib_id` | BIGINT | LRCLIB external ID |
| `plain_lyrics` | TEXT | Raw lyrics text |
| `synced_lyrics` | TEXT | LRC-format synced lyrics |
| `instrumental` | BOOL | Không có lời |
| `has_lyrics` | BOOL | Có lời bài hát |
| `lyrics_cleaned` | TEXT | Cleaned/normalized lyrics |

**Processed Features (Phase 6)**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `color_hue` | FLOAT | HSL Hue (0–360) |
| `color_saturation` | FLOAT | HSL Saturation (0–1) |
| `color_lightness` | FLOAT | HSL Lightness (0–1) |
| `color_hex` | VARCHAR(8) | Hex color (#RRGGBB) |
| `sentiment_compound` | FLOAT | Compound sentiment score |
| `sentiment_positive` | FLOAT | Positive sentiment ratio |
| `sentiment_neutral` | FLOAT | Neutral sentiment ratio |
| `sentiment_negative` | FLOAT | Negative sentiment ratio |
| `sentiment_category` | VARCHAR(16) | pos/neg/neu |
| `mood_score` | FLOAT | Composite mood score |
| `mood_quadrant` | VARCHAR(32) | Q1/Q2/Q3/Q4 + label |
| `mood_id` | INT FK | → moods.mood_id |
| `dance_score` | FLOAT | Composite dance score |
| `acoustic_score` | FLOAT | Composite acoustic score |
| `combined_positivity` | FLOAT | Valence × Sentiment |
| `energy_level` | VARCHAR(16) | low/medium/high |
| `tempo_category` | VARCHAR(16) | slow/medium/fast |

**Media**:
| Cột | Kiểu | Mô tả |
|---|---|---|
| `has_mp3` | BOOL | Có file MP3 local |
| `mp3_filename` | VARCHAR(512) | Tên file |
| `mp3_path` | TEXT | Đường dẫn đầy đủ |
| `mp3_source` | VARCHAR(32) | youtube_music / youtube_lyrics / ... |
| `mp3_duration_s` | INT | Thời lượng MP3 (giây) |
| `mp3_quality` | VARCHAR(16) | clean / has_extra / low |
| `youtube_music_id` | VARCHAR(32) | YTMusic video ID |
| `youtube_id` | VARCHAR(32) | YouTube video ID |

---

## 3. Indexes

| Index Name | Table | Type | Columns | Mục đích |
|---|---|---|---|---|
| `ix_song_track_name_trgm` | songs | GIN (trgm) | track_name | Fuzzy text search |
| `ix_song_mood` | songs | B-tree | mood_quadrant | Mood filtering |
| `ix_song_color` | songs | B-tree | color_hex | Color filtering |
| `ix_song_valence_energy` | songs | B-tree | valence, energy | V-A proximity queries |
| `ix_artist_name_trgm` | artists | GIN (trgm) | name | Fuzzy artist search |
| `ix_song_embedding_hnsw` | song_embeddings | HNSW | embedding | Vector similarity search |

### HNSW Index Parameters
```sql
CREATE INDEX ix_song_embedding_hnsw ON song_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```
- **m = 16**: Số neighbors per layer (cân bằng accuracy/memory)
- **ef_construction = 64**: Build-time accuracy
- **vector_cosine_ops**: Cosine similarity metric

---

## 4. Connection Configuration

```python
# db/engine.py
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # Concurrent connections
    max_overflow=20,        # Max extra connections
    pool_pre_ping=True,     # Health check before use
    pool_recycle=1800,      # Recycle connections after 30 min
)
```

---

## 5. Backward Compatibility Aliases

```python
DimArtist = Artist
DimAlbum = Album
DimGenre = Genre
DimMood = Mood
DimSong = Song
FactRecommendation = Recommendation
FactSearch = SearchLog
BridgeSongArtist = SongArtist
BridgeArtistGenre = ArtistGenre
```

Các alias này giữ tương thích với code cũ sử dụng naming convention Dim/Fact/Bridge (star schema terminology).
