# Brightify — Báo Cáo Tổng Quan Dự Án

> **Tên dự án**: Brightify — AI-Powered Vietnamese Music Streaming Platform  
> **Phiên bản**: 7.1.0  
> **Ngày đánh giá**: 22/05/2026  
> **Ngôn ngữ chính**: Python (Backend), TypeScript/React (Frontend)

> ⚠️ **Lưu ý (snapshot lịch sử 22/05/2026).** Một số phần dưới đây đã lỗi thời so với mã nguồn hiện tại. Các thay đổi chính kể từ snapshot này:
> - **Gỡ recommend-by-image** (CLIP / `core/image_analysis.py` không còn) và tính năng lyrics-search.
> - **Frontend là React 19 + Vite** (`frontend/` → `static_spa/`) với 2 giao diện: vũ trụ 3D (react-three-fiber) và "classic" 2D — không còn là HTML/CSS/JS thuần.
> - Bề mặt tính năng hiện tại: recommend-by-color, similar-song (radio vô tận), smart crossfade, tìm kiếm, player.
>
> Tài liệu chính xác nhất: [README.md](../README.md) và [SCIENTIFIC_AUDIT_AND_PLAN_V32.md](SCIENTIFIC_AUDIT_AND_PLAN_V32.md).

---

## 1. Giới Thiệu

Brightify là một nền tảng streaming nhạc Việt Nam tích hợp AI, cho phép gợi ý bài hát dựa trên nhiều tín hiệu đa phương thức (multimodal): **màu sắc**, **cảm xúc**, **lời bài hát** và **độ tương tự bài hát**. Hệ thống sử dụng các mô hình AI gồm bộ embedding lyrics đa ngữ (e5-large), MuQ (đặc trưng âm thanh), Essentia (DSP) và tự xây dựng bộ từ điển cảm xúc tiếng Việt với 730+ từ.

### Điểm nổi bật
- **6 chế độ gợi ý AI**: Color, Image, Mood, Song Similarity, Lyrics, Context-aware
- **2 tính năng nâng cao**: Emotion Journey (playlist chuyển cảm xúc), Musical DNA (hồ sơ sở thích)
- **Pipeline dữ liệu 7 giai đoạn** tự động hóa từ thu thập đến artifact serving + đồng bộ PostgreSQL
- **Frontend SPA** (Single Page Application) hoàn chỉnh với audio player, visualizer, queue management
- **Nền tảng nghiên cứu**: Mỗi thuật toán đều có trích dẫn paper học thuật (Russell 1980, Palmer et al. 2013, Kim et al. 2024, v.v.)

---

## 2. Kiến Trúc Hệ Thống

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (SPA)                         │
│   static/index.html + css/styles.css + js/app.js         │
│   + js/player.js + js/api.js                             │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / REST API
┌────────────────────────▼─────────────────────────────────┐
│                 FastAPI Application (app.py)              │
│  ├── api/music.py        — Browse, Search, Stream        │
│  ├── api/recommend.py    — AI Recommendations            │
│  ├── api/system.py       — Health, Stats, Backtest       │
│  ├── api/rate_limit.py   — Sliding-window Rate Limiter   │
│  └── api/utils.py        — Serialization Helpers         │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                  Core AI/ML Modules                       │
│  ├── core/recommendation_engine.py  (1838 dòng)          │
│  │     MusicRecommender: 7 signal song sim, color rec,   │
│  │     mood rec, image rec, emotion journey, context,     │
│  │     musical DNA, lyrics search                        │
│  ├── core/emotion_analysis.py (548 dòng)                 │
│  │     VietnameseEmotionLexicon, EmotionClassifier,       │
│  │     MultimodalEmotionFusion                           │
│  ├── core/image_analysis.py (846 dòng)                   │
│  │     ImageAnalyzer: CLIP + Color + Scene + Expression  │
│  └── core/advanced_color_mapping.py (505 dòng)           │
│        AdvancedColorMapper: HSL ↔ V-A ↔ Emotion          │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│               Data Layer                                  │
│  ├── data/           — Runtime serving artifacts          │
│  │                     (CSV, NPY, JSON)                   │
│  ├── db/models.py    — SQLAlchemy ORM (PostgreSQL)        │
│  ├── db/engine.py    — Connection pool & session          │
│  ├── db/seed.py      — Catalog sync / seed mirror         │
│  └── alembic/        — Database migrations                │
└──────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│            Data Pipeline (tools/)                         │
│  ├── pipeline.py          — 7-phase orchestrator          │
│  ├── collect_data.py      — YTMusic + Spotify collection  │
│  ├── filter_data.py       — Dedup & Vietnamese filter     │
│  ├── download_music.py    — MP3 download (5-tier YouTube) │
│  ├── extract_audio_features.py — Essentia DSP + ML        │
│  ├── process_data.py      — Feature engineering + embed   │
│  └── backtest.py          — Evaluation metrics suite      │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Thống Kê Mã Nguồn

| Thành phần | File | Số dòng | Kích thước |
|---|---|---|---|
| **Core AI** | `recommendation_engine.py` | 1,838 | 83.5 KB |
| **Core AI** | `image_analysis.py` | 846 | 36.6 KB |
| **Core AI** | `emotion_analysis.py` | 548 | 27.1 KB |
| **Core AI** | `advanced_color_mapping.py` | 505 | 20.6 KB |
| **API** | `music.py` | 726 | 27.7 KB |
| **API** | `recommend.py` | 389 | 14.5 KB |
| **API** | `system.py` | 285 | 10.7 KB |
| **API** | `rate_limit.py` | 70 | 2.8 KB |
| **API** | `utils.py` | 66 | 2.4 KB |
| **Database** | `models.py` | 298 | 11.5 KB |
| **Database** | `seed.py` | 590 | 24.8 KB |
| **Pipeline** | `pipeline.py` | 678 | 26.2 KB |
| **Pipeline** | `collect_data.py` | 4,964 | 230 KB |
| **Pipeline** | `filter_data.py` | 1,051 | 54.2 KB |
| **Pipeline** | `extract_audio_features.py` | 1,159 | 47.3 KB |
| **Pipeline** | `download_music.py` | 756 | 28.4 KB |
| **Pipeline** | `process_data.py` | 703 | 28.4 KB |
| **Pipeline** | `backtest.py` | 898 | 34.3 KB |
| **Frontend** | `app.js` | 2,451 | 128.8 KB |
| **Frontend** | `player.js` | 1,270 | 51.8 KB |
| **Frontend** | `styles.css` | 3,218 | 98.3 KB |
| **Frontend** | `index.html` | 298 | 21.1 KB |
| **Test** | 10 test files | ~11,000+ | ~130 KB |
| **Tổng ước tính** | **~40 files** | **~34,000+** | **~1 MB+** |

### Dữ liệu
| File | Kích thước | Mô tả |
|---|---|---|
| `vietnamese_music_processed_full.csv` | 45.8 MB | Dataset đã xử lý hoàn chỉnh |
| `audio_embeddings.json` | 50.7 MB | Audio embeddings |
| `lyrics_backup.json` | 29.4 MB | Backup lời bài hát |
| `vietnamese_music_embeddings_full.npy` | 17 MB | PhoBERT 768-dim embeddings |
| `embeddings_metadata.json` | 269 KB | Metadata cho embeddings |

---

## 4. Chi Tiết Các Thành Phần

### 4.1. Core AI — Recommendation Engine (`core/recommendation_engine.py`)

**Lớp chính**: `MusicRecommender` (1,838 dòng)

#### Các phương thức gợi ý:

| Phương thức | Mô tả | Tín hiệu sử dụng |
|---|---|---|
| `recommend_by_colors()` | Gợi ý theo màu sắc | Audio(25%), Lyrics(35%), V-A(20%), Emotion(20%) |
| `recommend_by_song()` | Gợi ý bài tương tự | 7 tín hiệu: Timbral, Rhythmic, Tonal, Lyrics, V-A, Emotion, Mood |
| `recommend_by_mood()` | Gợi ý theo tâm trạng | V-A proximity (Gaussian kernel) |
| `recommend_by_image()` | Gợi ý theo hình ảnh | Audio(20%), Lyrics(25%), V-A(20%), Emotion(15%), Color(20%) |
| `recommend_by_lyrics_keywords()` | Tìm theo lời bài hát | PhoBERT semantic(40%) + Keyword(35%) + Centroid(25%) |
| `generate_emotion_journey()` | Playlist chuyển cảm xúc | Iso Principle, Bézier curve, 4-signal scoring |
| `smart_context_recommend()` | Gợi ý theo ngữ cảnh | Circadian(35%), User taste(25%), Activity(20%), Emotion(10%), Freshness(10%) |
| `compute_musical_dna()` | Phân tích sở thích | 6 DNA dimensions, ILD diversity, temporal patterns |

#### Đặc điểm kỹ thuật nổi bật:
- **Pre-computation**: Tất cả features (V-A, emotion vectors, color HSL, audio sub-matrices) được tính trước khi khởi tạo → thời gian query < 1ms
- **Vectorized operations**: Sử dụng NumPy vectorization thay vì vòng lặp Python
- **MMR-lite ranking** (`_fast_rank`): Artist diversity penalty escalating + mood novelty bonus
- **Research-grounded**: Mỗi phương thức đều có docstring trích dẫn nghiên cứu (Berenzweig 2004, Hu & Downie 2010, Russell 1980, v.v.)

### 4.2. Core AI — Emotion Analysis (`core/emotion_analysis.py`)

**3 lớp chính**:

1. **`VietnameseEmotionLexicon`**: Từ điển cảm xúc tiếng Việt mở rộng
   - 13 danh mục cảm xúc: happy, sad, love, angry, peaceful, excited, melancholic, longing, hope, nostalgia, disgust, fear, surprise
   - 730+ từ/cụm từ tiếng Việt (bao gồm từ vùng miền, Gen Z, loanwords)
   - Hỗ trợ intensifiers ("rất", "cực kỳ") và negations ("không", "chẳng")
   - Scoring: đếm từ → normalize → trả về phân phối xác suất

2. **`EmotionClassifier`**: PhoBERT-based encoder
   - Model: `vinai/phobert-base-v2` (135M params)
   - Vietnamese word segmentation via `pyvi.ViTokenizer`
   - Attention pooling (thay vì chỉ CLS token)
   - Emotion → V-A mapping theo Russell's Circumplex

3. **`MultimodalEmotionFusion`**: Kết hợp audio + lyrics
   - Adaptive weighting dựa trên confidence
   - Quadrant-based emotion labeling

### 4.3. Core AI — Image Analysis (`core/image_analysis.py`)

**Lớp chính**: `ImageAnalyzer` — Phân tích hình ảnh đa phương thức

**Pipeline phân tích**:
1. **Color Extraction**: Center-weighted K-Means (5 dominant colors, Gaussian spatial weighting)
2. **CLIP Emotion**: Zero-shot classification với 50 prompt tiếng Anh (10 emotions × 5 prompts)
3. **CLIP Scene**: 18 scene categories (nature, urban, beach, v.v.)
4. **CLIP Content Type**: 12 loại nội dung (portrait, landscape, art, food, v.v.)
5. **CLIP Expression**: 12 biểu cảm khuôn mặt (Ekman 1992 + AffectNet)
6. **CLIP Lighting**: 8 điều kiện ánh sáng (golden hour, neon, candlelight, v.v.)
7. **Visual Features**: Brightness, Saturation, Contrast, Warmth, Color Variety

**Content-aware adaptive fusion**: Trọng số tự điều chỉnh theo loại nội dung:
- Người (portrait) → biểu cảm mặt chiếm 30%
- Phong cảnh → scene context + color palette chiếm 55%
- Nghệ thuật trừu tượng → color chiếm 35%

### 4.4. Core AI — Color Mapping (`core/advanced_color_mapping.py`)

**Lớp chính**: `AdvancedColorMapper` v5.2

- **13 emotion-color profiles** dựa trên Jonauskaite et al. (2020) — nghiên cứu 12 quốc gia, 4,598 người tham gia
- **V-A anchor interpolation**: 11 anchor points, inverse distance weighting cho 3 nearest
- **Bidirectional mapping**: Color → V-A → Audio features và ngược lại
- **CIEDE2000 perceptual distance** (thông qua colormath)
- **Vietnamese cultural adjustments**: Điều chỉnh hue/saturation cho văn hóa Việt Nam

### 4.5. API Layer (`api/`)

**Framework**: FastAPI 0.108+ với Pydantic v2 validation

| Router | Prefix | Số endpoint | Chức năng chính |
|---|---|---|---|
| `music.py` | `/api/` | 18 | Browse, Search, Stream, Artists, Genres, Audio |
| `recommend.py` | `/api/recommend/` | 6 | Color, Image, Lyrics, Emotion Journey, Context Mix, Musical DNA |
| `system.py` | `/api/` | 7 | Health, Stats, Config, Image Status, Backtest (3) |

**Middleware**:
- **RateLimitMiddleware**: Sliding-window per IP+route, cấu hình khác nhau cho AI endpoints (30/min), admin (5/min), login (10/min), mặc định (120/min)
- **CORSMiddleware**: Cấu hình từ env `ALLOWED_ORIGINS`

**Bảo mật**:
- Admin API key via `X-Admin-Key` header, so sánh timing-safe (`hmac.compare_digest`)
- Image upload: chunk reading (64KB), giới hạn 10MB, `MAX_IMAGE_PIXELS = 25M`
- Track ID validation: chỉ cho phép alphanumeric + `-_`

### 4.6. Database (`db/`)

**DBMS**: PostgreSQL 17 + pgvector extension

**Vai trò thực tế hiện tại**:
- runtime recommendation catalog: file-based (`data/*.csv/*.npy/*.json`)
- runtime audio: `music_files/*.mp3`
- PostgreSQL: serving mirror, health probe, crossfade side-data

Blueprint production chuẩn hóa ở [PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md](./PLAN_PRODUCTION_DATA_ARCHITECTURE_V24.md).

**Schema** (10 bảng):

| Bảng | Loại | Mô tả |
|---|---|---|
| `songs` | Core | Bài hát + audio features + lyrics + processed features |
| `artists` | Core | Nghệ sĩ với genres, followers, image |
| `albums` | Core | Album metadata |
| `genres` | Core | Thể loại nhạc |
| `moods` | Core | Russell's Circumplex mood quadrants |
| `song_artists` | Bridge | Song ↔ Artist (many-to-many) |
| `artist_genres` | Bridge | Artist ↔ Genre (many-to-many) |
| `song_embeddings` | Vector | PhoBERT 768-dim embeddings (pgvector) |
| `recommendations` | Analytics | Log gợi ý (cho backtest) |
| `search_logs` | Analytics | Log tìm kiếm |

**Indexes**:
- HNSW index trên `song_embeddings` (m=16, ef=64) cho vector similarity search
- GIN trigram indexes trên `artists.name` và `songs.track_name` cho fuzzy text search
- B-tree indexes trên valence+energy, mood_quadrant, color_hex, popularity

### 4.7. Data Pipeline (`tools/pipeline.py`)

**7 giai đoạn với Strict Removal Gates**:

```
Phase 1: COLLECT    → YTMusic + Spotify artist discovery → phase1_spotify.csv
Phase 2: FILTER     → Dedup, Vietnamese filter → phase2_filtered.csv
Phase 3: DOWNLOAD   → MP3 download (5-tier YouTube) → music_files/
   └── GATE: Remove tracks without MP3 → phase3_downloaded.csv
Phase 4: LYRICS     → YTMusic/LRCLIB lyrics → phase4_lyrics.csv
   └── GATE: Remove tracks without lyrics → phase4_lyrics_gated.csv
Phase 5: EXTRACT    → Essentia DSP + TF ML models → phase5_features.csv
   └── GATE: Remove tracks with incomplete features
Phase 6: PROCESS    → Feature engineering + PhoBERT embeddings → data/*.csv + *.npy
Phase 7: SEED       → Sync serving artifacts into PostgreSQL mirror + HNSW index
```

**Features**:
- Resumable execution (`--from-phase`, `--resume`)
- Test mode (`--test-mode --limit 50`)
- Pre-flight backup tự động
- Phase output validation (min rows, required columns, null checks)
- Configurable timeouts (4h mặc định/phase)

### 4.8. Frontend (`static/`)

**Công nghệ**: Vanilla HTML/CSS/JavaScript (SPA, no framework)

| File | Dòng | Chức năng |
|---|---|---|
| `index.html` | 298 | Layout: Sidebar + Main + Player Bar + Queue Panel + Modals |
| `css/styles.css` | 3,218 | Dark theme, glassmorphism, gradient animations |
| `js/app.js` | 2,451 | Router, Page rendering, AI Lab UI, Home, Browse |
| `js/player.js` | 1,270 | Audio player, visualizer, queue, crossfade, radio mode |
| `js/api.js` | ~200 | API client wrapper |

**UI Features**:
- Dark mode + ambient background gradient
- Audio visualizer (canvas-based)
- Keyboard shortcuts (Space, arrows, M, S, R, Q, etc.)
- Sleep timer, crossfade, playback speed
- AI Lab: Color picker, Image upload, Mood selector, Lyrics search, Emotion Journey, Context Mix, Musical DNA

### 4.9. Testing (`test/`)

10 test files covering:
- `test_pipeline_v6.py` (38,016 bytes) — Comprehensive pipeline test
- `test_filter_v2.py` — Data filtering tests
- `test_artist_detection.py` — Artist detection logic
- `test_essentia.py`, `test_librosa.py` — Audio feature extraction
- `test_ytdlp.py`, `test_ytmusicapi.py` — Download & API tests
- `test_lyrics_ytmusic.py` — Lyrics fetching
- `validate_final.py`, `verify_integration.py` — Integration tests

---

## 5. Công Nghệ & Dependencies

### AI/ML Models
| Model | Mục đích | Kích thước |
|---|---|---|
| PhoBERT v2 (`vinai/phobert-base-v2`) | Vietnamese NLP embeddings | 135M params |
| CLIP ViT-B/32 (`openai/clip-vit-base-patch32`) | Image understanding | 151M params |
| Essentia TensorFlow models | Audio feature extraction | ~50MB |

### Thư viện chính
| Nhóm | Thư viện |
|---|---|
| **Web** | FastAPI, Uvicorn, Pydantic v2 |
| **ML/AI** | PyTorch, Transformers, scikit-learn |
| **NLP** | pyvi (Vietnamese tokenizer), sentencepiece, langdetect |
| **Audio** | essentia-tensorflow, librosa, mutagen |
| **Database** | SQLAlchemy 2.0, psycopg2, pgvector, Alembic |
| **Data** | pandas, numpy |
| **Color** | colormath (CIEDE2000) |
| **Image** | Pillow |
| **Data Collection** | ytmusicapi, yt-dlp, requests |

---

## 6. Cấu Hình & Vận Hành

### Biến môi trường (`.env`)
```
DATABASE_URL=postgresql://...
BRIGHTIFY_JWT_SECRET=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
ALLOWED_ORIGINS=...
DOWNLOAD_WORKERS=4
BRIGHTIFY_ADMIN_KEY=...
```

### Khởi chạy
```bash
source .venv/bin/activate
uvicorn app:app --reload --port 8000
```

### Pipeline
```bash
python -m tools.pipeline                     # Full production run
python -m tools.pipeline --test-mode         # Test with 50 tracks
python -m tools.pipeline --from-phase 5      # Resume from Phase 5
```

### Database
```bash
alembic upgrade head    # Run migrations
python -m db.seed       # Seed from CSV
```
