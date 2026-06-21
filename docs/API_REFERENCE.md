# Brightify — API Reference

> **Base URL**: `http://localhost:8000`  
> **Auto-generated docs**: `/docs` (Swagger UI) | `/redoc` (ReDoc)

---

## 1. Music Browse & Discovery

### GET `/api/songs` — Browse Songs
Duyệt bài hát với phân trang, sắp xếp và lọc.

**Query Parameters**:
| Param | Type | Default | Mô tả |
|---|---|---|---|
| `page` | int (≥1) | 1 | Trang |
| `limit` | int (1–100) | 20 | Số bài/trang |
| `sort` | string | "name" | Sắp xếp: `name`, `artist`, `energy`, `valence`, `danceability`, `random` |
| `mood` | string | null | Lọc theo mood quadrant (Q1, Q2, Q3, Q4) |
| `artist` | string | null | Lọc theo nghệ sĩ (substring match) |
| `search` | string | null | Tìm kiếm theo tên bài/nghệ sĩ |

**Response**: `{"success": true, "songs": [...], "total": 5000, "page": 1, "limit": 20, "total_pages": 250}`

---

### GET `/api/songs/featured` — Featured Songs
Bài hát nổi bật (highest energy + danceability + valence).

| Param | Default | Range |
|---|---|---|
| `count` | 12 | 1–50 |

---

### GET `/api/songs/new-releases` — New Releases
Bài hát mới nhất (cuối dataset).

| Param | Default | Range |
|---|---|---|
| `count` | 12 | 1–50 |

---

### GET `/api/songs/by-mood/{mood}` — Songs by Mood
Lọc bài theo tâm trạng.

**Path params**: `mood` = `happy`, `excited`, `angry`, `tense`, `energetic`, `sad`, `melancholic`, `calm`, `peaceful`, `relaxed`

---

### GET `/api/songs/time-of-day` — Time of Day Songs
Bài hát phù hợp theo thời điểm trong ngày.

| Param | Required | Values |
|---|---|---|
| `period` | Yes | `early_morning`, `morning`, `midday`, `afternoon`, `evening`, `night` |
| `count` | No (14) | 1–50 |

**Thuật toán**: Gaussian distance scoring trên 5 audio features (energy, valence, acousticness, danceability, tempo) theo profile từng period.

---

### GET `/api/songs/random` — Random Songs
Bài hát ngẫu nhiên.

---

### GET `/api/search` — Smart Search
Tìm kiếm đa tầng, không phân biệt dấu, có khôi phục lỗi gõ (rapidfuzz) + ngữ nghĩa (e5-large).

| Param | Required | Mô tả |
|---|---|---|
| `q` | Yes (min 1 char) | Query string |
| `limit` | No (20) | 1–50 |

Trả `{success, results, query, total, semantic_available}`. Mỗi kết quả có `match_type` ∈ `artist | name | lyrics | vibe` và `lyric_snippet`. Ưu tiên theo khối: nghệ sĩ → tên/album → lời → ngữ nghĩa.

---

## 2. Artists

### GET `/api/artists` — List Artists
Danh sách nghệ sĩ kèm số bài, ảnh, genres.

| Param | Default | Range |
|---|---|---|
| `limit` | 50 | 1–9999 |

---

### GET `/api/artists/{artist_name}/songs` — Artist Songs
Tất cả bài hát của một nghệ sĩ. Hỗ trợ substring matching.

---

### GET `/api/artist/{artist_id}/info` — Artist Info
Thông tin chi tiết nghệ sĩ (image, genres, followers, popularity).

---

## 3. Song Details & Audio

### GET `/api/song/{song_id}` — Song Details
Chi tiết bài hát. `song_id` có thể là Spotify track ID (string) hoặc integer index.

**Response bổ sung**: `acousticness`, `instrumentalness`, `speechiness`, `liveness`, `loudness`, `key`, `mode`, `sentiment_compound`, `lyrics`

---

### GET `/api/song/{song_id}/similar` — Similar Songs
Bài hát tương tự sử dụng 7-signal AI similarity.

| Param | Default | Range |
|---|---|---|
| `count` | 10 | 1–30 |

---

### GET `/api/audio/stream/{track_id}` — Stream Audio
Stream MP3 file. Headers: `Accept-Ranges: bytes`, `Cache-Control: public, max-age=3600`.

---

### GET `/api/album-art/{track_id}` — Album Art
Serve ảnh album art (JPEG). Cache 24h.

---

### GET `/api/artist-image/{artist_id}` — Artist Image
Serve ảnh nghệ sĩ (JPEG). Cache 24h.

---

## 4. Genres & Moods

### GET `/api/genres` — List Genres/Moods
Danh sách mood quadrants + fused emotions kèm counts và gradients.

---

### GET `/api/moods` — Available Moods
Mood keywords và quadrant definitions từ config.

---

## 5. AI Recommendations

### POST `/api/recommend/color` — Recommend by Color
Gợi ý bài hát theo màu sắc (CIEDE2000 perceptual distance).

**Body (JSON)**:
```json
{
  "colors": ["#FF5733", "#3498DB"],
  "top_k": 10,
  "weights": [0.25, 0.35, 0.20, 0.20],
  "diversity_penalty": 0.15
}
```

---

### POST `/api/recommend/lyrics` — Search by Lyrics
Tìm bài theo lời bài hát (PhoBERT semantic + keyword hybrid).

**Body (JSON)**:
```json
{
  "keywords": "tình yêu mùa đông",
  "top_k": 10,
  "diversity_penalty": 0.15
}
```

---

### POST `/api/recommend/image` — Recommend by Image
Gợi ý bài theo hình ảnh (CLIP + color analysis).

**Form Data**: `file` (JPEG/PNG/WebP, max 10MB), `top_k` (1–50), `diversity_penalty` (0–1)

**Response bổ sung**: `image_analysis` object chứa dominant_colors, mood_label, valence, arousal, top_emotions, top_scenes, content_type, expression, lighting.

---

### POST `/api/recommend/emotion-journey` — Emotion Journey
Tạo playlist chuyển cảm xúc (Iso Principle).

**Body (JSON)**:
```json
{
  "start_valence": 0.2,
  "start_arousal": 0.3,
  "end_valence": 0.8,
  "end_arousal": 0.7,
  "steps": 10
}
```

**Response**: `songs` (ordered playlist), `waypoints` (V-A trajectory points), `journey_info`

---

### POST `/api/recommend/context-mix` — Context-Aware Mix
Gợi ý dựa trên ngữ cảnh (thời gian, hoạt động, thời tiết, sở thích).

**Body (JSON)**:
```json
{
  "hour": 14,
  "day_of_week": 3,
  "activity": "study",
  "season": "summer",
  "weather": "rainy",
  "user_history": [...],
  "user_liked": [...],
  "count": 15
}
```

**Activities**: `workout`, `study`, `relax`, `commute`, `party`, `sleep`, `focus`, `cooking`, `morning_routine`

---

### POST `/api/recommend/musical-dna` — Musical DNA
Phân tích "DNA âm nhạc" từ lịch sử nghe.

**Body (JSON)**:
```json
{
  "user_liked": [{"track_id": "abc", "play_count": 5}],
  "user_history": [{"track_id": "def", "played_at": "2026-05-01"}]
}
```

**Response**: 6 DNA dimensions, top genres, taste profile, recommendations.

---

## 6. System

### GET `/api/health` — Health Check
Trạng thái hệ thống: recommender, DB, embeddings.

### GET `/api/statistics` — System Statistics
Thống kê: tổng bài, features, models.

### GET `/api/config` — Configuration
Cấu hình hiện tại: weights, thresholds, methods.

### GET `/api/image/status` — Image Service Status
Trạng thái CLIP model.

---

## 7. Backtest (Admin only — X-Admin-Key header)

### POST `/api/backtest/run` — Run Backtest
Chạy evaluation metrics suite.

### POST `/api/backtest/test-weights` — Test Custom Weights
So sánh custom weights vs default.

### GET `/api/backtest/dataset-stats` — Dataset Statistics
Thống kê chi tiết dataset.

---

## 8. Rate Limits

| Route | Limit |
|---|---|
| `/api/recommend/*` | 30 req/min |
| `/api/backtest/*` | 5 req/min |
| `/api/auth/login` | 10 req/min |
| `/api/auth/register` | 5 req/min |
| Default | 120 req/min |
| `/api/health`, `/static/*` | Unlimited |

**Response khi bị limit**: `429 Too Many Requests` + `Retry-After` header
