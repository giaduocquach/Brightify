# 📋 BÁO CÁO ĐÁNH GIÁ DỰ ÁN — BRIGHTIFY v7.0

**Ngày đánh giá:** 07/04/2026  
**Phiên bản:** 7.0 (API) / 7.1 (Config)  
**Người thực hiện:** Senior Engineer — Comprehensive Technical Audit  

---

## 1. Tổng Quan Dự Án

### Mục đích và chức năng chính

**Brightify** là nền tảng streaming nhạc Việt Nam tích hợp AI, có khả năng:

- **Gợi ý nhạc đa phương thức (multimodal):** theo màu sắc (CIEDE2000), tâm trạng (Russell's Circumplex), lời bài hát (PhoBERT), hình ảnh (CLIP), bối cảnh (thời gian/hoạt động/thời tiết)
- **Phân tích cảm xúc nhạc Việt:** bộ từ điển ~500+ từ cảm xúc tiếng Việt, phân loại 13 loại cảm xúc
- **Data pipeline 7 giai đoạn:** thu thập từ Spotify → lọc → tải MP3 → trích xuất audio features → xử lý NLP → tạo embeddings → seed vào Data Warehouse
- **Streaming audio:** phát nhạc trực tuyến với crossfade, visualizer FFT, radio mode tự động
- **Hệ thống user:** đăng ký/đăng nhập, playlist cá nhân, lịch sử nghe, like/follow, Musical DNA

### Tech Stack & Dependencies

| Layer | Công nghệ |
|-------|-----------|
| **Backend** | Python 3.10+, FastAPI 0.108+, Uvicorn |
| **Database** | PostgreSQL 17, SQLAlchemy 2.0, Alembic, pgvector |
| **AI/ML** | PyTorch, Transformers (PhoBERT, CLIP), scikit-learn, Essentia-TF |
| **NLP** | vinai/phobert-base (768-dim), PyVI tokenizer, langdetect |
| **Audio** | Essentia, Librosa, yt-dlp, FFmpeg, Mutagen |
| **Frontend** | Vanilla HTML/CSS/JS (SPA), Web Audio API, Canvas |
| **APIs bên ngoài** | Spotify API, YTMusic API, LRCLIB, YouTube |
| **Color Science** | colormath (CIEDE2000), Russell's Circumplex Model |

### Quy mô

| Metric | Giá trị |
|--------|---------|
| Tổng số file source | ~75 files |
| Tổng dòng code | **~29,500 LOC** |
| File Python | 47 files (~23,000 LOC) |
| File JS | 3 files (~5,900 LOC) |
| File HTML | 1 file (490 LOC) |
| File CSS | 1 file (~2,800 LOC) |
| Module chính | 5 (api, core, db, tools, static) |
| Migration DB | 8 versions |
| Test files | 11 files (~4,000 LOC) |
| ML Models | 10+ (PhoBERT, CLIP, 8 Essentia models) |

---

## 2. Điểm Mạnh 💪

### 2.1. Kiến trúc AI đa phương thức xuất sắc
Hệ thống recommendation sử dụng **fusion 7 tín hiệu** (timbral, rhythmic, tonal, lyrics, V-A, emotion, mood) — đây là approach rất tiên tiến, có trích dẫn nghiên cứu đầy đủ (Berenzweig 2004, Zhang 2024, Kim 2024). Xem `core/recommendation_engine.py` — class `MusicRecommender` với phương thức `recommend_by_song()`.

### 2.2. Database schema chuyên nghiệp
Star schema chuẩn Data Warehouse với dimension tables (DimArtist, DimAlbum, DimSong, DimMood, DimUser), fact tables (FactListen, FactLike, FactFollow, FactRecommendation), bridge tables và vector embeddings (pgvector 768-dim). Xem `db/models.py` — 420 dòng ORM models. Có đầy đủ indexes (trigram GIN, HNSW vector, composite) và constraints.

### 2.3. Pipeline dữ liệu hoàn chỉnh
Pipeline 7 giai đoạn từ discovery → production với checkpoint recovery, backup preflight, và validation gates. Xem `tools/pipeline.py`. Hệ thống rate limiter thông minh với multi-app Spotify rotation tại `tools/collect_data.py` dòng 278 — class `SpotifyRateLimiter`.

### 2.4. Bảo mật authentication tốt
- Password hashing: PBKDF2 310,000 iterations (`api/auth.py` dòng 58)
- Timing-safe comparison: `hmac.compare_digest()` (`api/auth.py` dòng 65)
- Cookie security: `httponly=True, samesite="strict", secure=True` (`api/auth.py` dòng 253)
- JWT secret từ env var với validation (`api/auth.py` dòng 46)
- Account lockout sau nhiều lần đăng nhập thất bại (`api/auth.py` dòng 230)

### 2.5. Test suite chất lượng cao
11 file test với ~4,000 LOC bao phủ hầu hết các component quan trọng: Vietnamese detection, audio extraction, pipeline integration, rate limiter, lyrics fetching. Xem `test/test_pipeline_v6.py` — 1,500+ dòng với 100+ test cases.

### 2.6. Xử lý tiếng Việt chuyên sâu
Bộ phát hiện tiếng Việt đa lớp (`VietnameseDetector`) kết hợp dấu thanh, pattern matching, langdetect, và foreign character detection. Từ điển cảm xúc 500+ từ Việt phân loại 13 loại cảm xúc. Xem `core/emotion_analysis.py` dòng 12.

### 2.7. Trải nghiệm frontend ấn tượng
Audio player với crossfade equal-power, FFT visualizer 16-bar, radio mode tự động, keyboard shortcuts 13 phím, drag-to-reorder queue, ambient background gradient. Xem `static/js/player.js`.

### 2.8. ETL seed có post-validation
Script seed (`db/seed.py`) thực hiện bulk upsert, tạo HNSW vector index, trigram indexes, và chạy FK integrity validation sau khi seed xong.

---

## 3. Vấn Đề Nghiêm Trọng 🔴

### 🔴 3.1. Endpoint `/api/recommend/mood` bị "chết" — Dead Code

**File:** `api/recommend.py` dòng 130–153  
**Mô tả:** Code xử lý mood recommendation nằm **bên trong** except block của endpoint `/color`, sau dòng `raise HTTPException(...)`. Code này không bao giờ được thực thi vì:
1. Thiếu decorator `@router.post("/mood")`
2. Docstring `"""Recommend songs by mood..."""` nằm ngay sau `raise HTTPException`

```python
# Dòng 130-135 — SAU dòng raise, code này KHÔNG BAO GIỜ chạy
raise HTTPException(status_code=500, detail="Color recommendation failed")
"""Recommend songs by mood using Russell's Circumplex Model"""   # ← DEAD CODE
try:
    results = _recommender.recommend_by_mood(...)  # ← UNREACHABLE
```

**Impact:** Tính năng gợi ý theo tâm trạng hoàn toàn không hoạt động trên production.  
**Fix:** Tách thành function riêng với decorator `@router.post("/mood")`.

### 🔴 3.2. Cookies.txt chứa credentials thực — 800 dòng cookie data

**File:** `cookies.txt` (project root)  
**Mô tả:** File chứa 800 dòng Netscape cookies từ YouTube, Google, Bing — bao gồm 125+ cookie liên quan YouTube/Google. Tuy đã được gitignore, file vẫn tồn tại trong workspace.  
**Risk:** Nếu vô tình commit hoặc chia sẻ project, session cookies bị lộ.  
**Fix:** Xóa nội dung, chỉ giữ file rỗng hoặc chuyển sang ngoài project root.

### 🔴 3.3. Command Injection risk trong yt-dlp

**File:** `tools/download_music.py`  
**Mô tả:** Tên nghệ sĩ và bài hát được truyền trực tiếp vào subprocess yt-dlp command mà không sanitize. Nếu tên bài hát chứa ký tự đặc biệt shell (`; rm -rf /`), có thể bị khai thác.  
**Fix:** Sử dụng danh sách arguments thay vì string interpolation: `subprocess.run([...args], shell=False)`.

### 🔴 3.4. XSS risk trong frontend app.js

**File:** `static/js/app.js`  
**Mô tả:** File monolithic ~3,500 dòng sử dụng `innerHTML` để render data từ API. Hàm `esc()` được tạo nhưng **không được áp dụng nhất quán** — nhiều chỗ render trực tiếp song name, artist name từ JSON response.  
**Impact:** Nếu attacker inject HTML/JS vào tên bài hát hoặc nghệ sĩ qua database, có thể thực thi XSS stored.  
**Fix:** Sử dụng `esc()` cho mọi user-controlled data, hoặc chuyển sang `textContent`/template literal safe.

### 🔴 3.5. Thiếu admin authorization cho các endpoint tốn tài nguyên

**File:** `api/system.py` dòng 109, 157, 195  
**Mô tả:** Endpoints `/api/system/backtest`, `/api/system/test-weights`, `/api/system/dataset-stats` yêu cầu auth nhưng **bất kỳ user đăng nhập nào cũng có thể trigger**, không kiểm tra admin role.  
**Impact:** Bất kỳ user nào cũng có thể DoS server bằng cách gọi backtest liên tục.  
**Fix:** Thêm admin role check hoặc rate limit cho các endpoint tốn tài nguyên.

### 🔴 3.6. Negation logic sai trong Emotion Analysis

**File:** `core/emotion_analysis.py`  
**Mô tả:** Khi phát hiện phủ định (ví dụ "không vui"), code cộng điểm vào cảm xúc đối lập (sad) thay vì giảm điểm cảm xúc hiện tại (happy). Kết quả: "không vui" = "buồn" (sai về ngữ nghĩa — "không vui" ≠ "buồn", có thể là "bình thường").  
**Impact:** Phân tích cảm xúc lời bài hát thiếu chính xác, ảnh hưởng tới recommendation accuracy.

---

## 4. Vấn Đề Cần Cải Thiện 🟡

### 🟡 4.1. File `app.js` monolithic 3,500+ dòng
**File:** `static/js/app.js`  
Cần tách thành ít nhất 4 module: router.js, auth.js, pages.js, ailab.js. Hiện tại rất khó maintain và debug.

### 🟡 4.2. File `styles.css` 2,800+ dòng không modular
**File:** `static/css/styles.css`  
Nên tách thành: base.css, components.css, ai-lab.css, auth.css, player.css.

### 🟡 4.3. Magic numbers và duplicate definitions tràn lan
- Emotion labels hardcoded ở 3+ vị trí: `core/recommendation_engine.py`, `core/emotion_analysis.py`, `core/image_analysis.py`
- Fusion weights (0.25, 0.35, 0.20, 0.20) ở cả `config.py` và trong function bodies
- V-A coordinates cho emotions copy-paste giữa 3 files

### 🟡 4.4. Global state pattern tạo tight coupling
Tất cả API modules (music, recommend, playlist, events, system) sử dụng pattern `global _recommender` với function `init()`. Tạo dependency order và initialization race conditions. Xem `api/music.py` dòng 25, `api/recommend.py` dòng 20.

### 🟡 4.5. Thiếu rate limiting cho API endpoints
Không có rate limiting middleware cho các endpoint công khai (search, browse, recommend). Chỉ có rate limit cho login (5 lần thất bại → lockout). Xem `api/auth.py` dòng 230.

### 🟡 4.6. Event endpoints không reject anonymous users
**File:** `api/events.py` dòng 80  
Các endpoint `/api/events/play`, `/like`, `/follow` trả về `{"success": false}` cho anonymous user nhưng vẫn trả status 200 — không tận dụng proper HTTP 401.

### 🟡 4.7. Memory leaks trong frontend
**File:** `static/js/app.js`  
Event listeners không được cleanup khi navigate giữa các pages. Canvas visualizer vẫn render khi tab bị minimize.

### 🟡 4.8. Unicode normalization không nhất quán
**File:** `tools/collect_data.py`, `tools/filter_data.py`  
5+ hàm normalize khác nhau (`_strip_vn`, `_norm_dedup`, `unicodedata.normalize`) được sử dụng không nhất quán. Cần merge thành 1 utility function.

### 🟡 4.9. Blocklist nghệ sĩ hardcoded và phân tán
Danh sách ~1,000+ nghệ sĩ bị block/whitelist nằm rải rác trong `tools/collect_data.py` và `tools/filter_data.py`. Nên chuyển ra file JSON/YAML riêng.

### 🟡 4.10. Playlist có thể có bài trùng lặp
**File:** `api/playlist.py` dòng 153  
Endpoint `add_song_to_playlist` không kiểm tra dedup — cùng bài hát có thể thêm nhiều lần vào playlist.

### 🟡 4.11. ColorRecommendationRequest validator không trả về modified input
**File:** `api/recommend.py` dòng 71–77  
Validator `validate_colors()` thêm `#` prefix vào biến local nhưng **không return list đã modify**. Colors không có `#` sẽ pass validation nhưng fail ở downstream.

### 🟡 4.12. `_track_id_to_song_index()` — Dead code
**File:** `api/playlist.py` dòng 20  
Hàm được định nghĩa nhưng không bao giờ được gọi trong file.

### 🟡 4.13. Crossfade race condition
**File:** `static/js/player.js`  
Crossfade có thể desync nếu user toggle shuffle/repeat trong lúc đang fade. Cần state machine cho audio playback.

### 🟡 4.14. Valence estimation sử dụng arbitrary weights
**File:** `tools/extract_audio_features.py`  
Công thức ước tính valence dùng trọng số tùy ý (0.15, 0.2, 0.15, 0.1) không có nguồn trích dẫn hay validation.

### 🟡 4.15. Password complexity validation bị lặp (DRY violation)
**File:** `api/auth.py` dòng 124–137 và 156–159  
Regex patterns cho password validation được copy-paste giữa `RegisterRequest` và `ChangePasswordRequest`.

---

## 5. Đề Xuất Nâng Cấp 🟢

### 🟢 5.1. Thêm Dockerfile & Docker Compose
Project hiện không có Dockerfile hoặc docker-compose.yml. Cần tạo để:
- Containerize FastAPI app + PostgreSQL 17 + pgvector
- Định nghĩa volume mounts cho `music_files/`, `album_art/`, `data/`
- Multi-stage build cho production (giảm image size)

### 🟢 5.2. Thêm CI/CD Pipeline
Không có GitHub Actions, GitLab CI, hay bất kỳ CI/CD nào. Cần:
- Lint (ruff/flake8)
- Test runner (pytest)
- Type checking (mypy)
- Security scan (bandit, safety)
- Auto-deploy

### 🟢 5.3. Bổ sung API documentation
FastAPI đã auto-generate `/docs` nhưng cần bổ sung:
- Request/response examples cho mỗi endpoint
- Error code documentation  
- Authentication flow documentation

### 🟢 5.4. Chuyển frontend sang component framework
Vanilla JS 6,000+ dòng rất khó maintain. Cân nhắc:
- Svelte/SvelteKit (lightweight, reactive)
- React + Vite (ecosystem lớn)
- Hoặc ít nhất là Web Components custom elements

### 🟢 5.5. Caching layer
- Redis hoặc in-memory cache cho recommendation results
- Cache invalidation khi data thay đổi
- Hiện tại mỗi request tính toán lại similarity từ đầu

### 🟢 5.6. Async database operations
`db/engine.py` dòng 19 sử dụng SQLAlchemy sync engine. Với FastAPI async, nên chuyển sang `create_async_engine` + `AsyncSession` để tránh block event loop.

### 🟢 5.7. Centralized logging & monitoring
Cần thống nhất logging format, level, và output. Hiện tại mỗi module tự tạo logger riêng không có correlation ID. Cần thêm structured logging, metrics collection.

### 🟢 5.8. Thêm README.md hoàn chỉnh
Project thiếu README.md đầy đủ. Cần:
- Setup instructions step-by-step
- Environment variables guide
- Architecture diagram
- API endpoint reference
- Contributing guidelines

### 🟢 5.9. Password reset flow
`api/auth.py` thiếu hoàn toàn tính năng quên mật khẩu / reset password. Không có email verification.

### 🟢 5.10. Refresh token mechanism
JWT hiện có expiry 72 giờ mà không có refresh token. User phải đăng nhập lại mỗi 3 ngày.

### 🟢 5.11. Model download checksum verification
`tools/extract_audio_features.py` tải 8 ML model từ URL hardcoded mà không verify checksum. Cần thêm SHA256 hash verification.

---

## 6. Đánh Giá Theo Từng Chiều

| Chiều đánh giá | Điểm (1–10) | Nhận xét ngắn |
|---|---|---|
| **Kiến trúc & Thiết kế** | **7** | Star schema DW chuẩn, API modular hợp lý, pipeline 7 phase hoàn chỉnh. Điểm trừ: global state coupling, frontend monolithic. |
| **Chất lượng Code** | **6** | Codebase ~29.5K LOC có naming conventions tốt, nhưng magic numbers tràn lan, duplicate definitions, Unicode normalization không nhất quán. |
| **Bảo mật** | **6** | Auth/password hashing xuất sắc (PBKDF2 310K). Điểm trừ: thiếu rate limiting API, thiếu admin authorization, XSS risk frontend, cookies.txt chứa credentials. |
| **Hiệu năng** | **7** | Vectorized numpy operations, HNSW index cho vector search, pre-computed embeddings. Điểm trừ: thiếu caching layer, sync DB operations block event loop. |
| **Xử lý lỗi** | **5** | Nhiều silent failures (`except Exception: pass`), generic exception handling. Fallback chains tốt nhưng thiếu logging. Missing bounds checking. |
| **Testing** | **7** | 11 file test, ~4,000 LOC, bao phủ tốt pipeline và detection logic. Điểm trừ: thiếu API endpoint tests, integration tests DB, frontend tests hoàn toàn. |
| **Tài liệu** | **5** | Research citations xuất sắc trong docstrings. Điểm trừ: thiếu README đầy đủ, API docs, architecture docs, onboarding guide. |
| **DevOps & Deployment** | **3** | Chỉ có .env.example và Alembic migrations. Hoàn toàn thiếu Dockerfile, docker-compose, CI/CD, monitoring. Manual deployment only. |

**Tổng điểm trung bình: 5.75/10**

---

## 7. Nợ Kỹ Thuật

| # | Khoản nợ | Vị trí | Effort ước tính |
|---|----------|--------|----------------|
| 1 | **Mood endpoint dead code** — tính năng core không hoạt động | `api/recommend.py` dòng 130 | 30 phút |
| 2 | **app.js monolithic 3,500 LOC** — không thể maintain hiệu quả | `static/js/app.js` | 2–3 ngày |
| 3 | **styles.css 2,800 LOC** — không modular | `static/css/styles.css` | 1 ngày |
| 4 | **50+ magic numbers** rải rác trong core/ | `core/recommendation_engine.py`, `emotion_analysis.py`, `image_analysis.py` | 1 ngày |
| 5 | **Duplicate emotion labels** ở 3+ vị trí | 3 files `core/` | 2 giờ |
| 6 | **5+ hàm Unicode normalize** khác nhau không nhất quán | `tools/collect_data.py`, `tools/filter_data.py` | 3 giờ |
| 7 | **Blocklist nghệ sĩ hardcoded** ~1,000+ entries phân tán 2 files | `tools/collect_data.py`, `tools/filter_data.py` | 2 giờ |
| 8 | **Global init pattern** cho tất cả API modules | `api/*.py` | 1 ngày |
| 9 | **Sync DB engine** với FastAPI async framework | `db/engine.py` | 2 ngày |
| 10 | **Thiếu Dockerfile/CI/CD** hoàn toàn | project root | 1–2 ngày |
| 11 | **Color validator bug** — không return modified list | `api/recommend.py` dòng 71 | 15 phút |
| 12 | **Dead code** `_track_id_to_song_index()` | `api/playlist.py` dòng 20 | 5 phút |
| 13 | **Negation logic sai** trong emotion analysis | `core/emotion_analysis.py` | 3 giờ |
| 14 | **Event listeners memory leak** trong frontend | `static/js/app.js` | 1 ngày |
| 15 | **Thiếu README.md** đầy đủ | project root | 3 giờ |
| 16 | **Valence estimation arbitrary weights** | `tools/extract_audio_features.py` | 2 giờ |
| 17 | **Password validation DRY violation** | `api/auth.py` | 30 phút |

---

## 8. Lộ Trình Cải Thiện Ưu Tiên

### P0 — Ngay lập tức (trong 1–2 ngày)
1. **Fix mood endpoint dead code** — tách thành function riêng với `@router.post("/mood")` trong `api/recommend.py`. *Effort: 30 phút*
2. **Fix color validator** — đảm bảo return modified list với `#` prefix. *Effort: 15 phút*
3. **Sanitize yt-dlp input** — sử dụng `shlex.quote()` hoặc list arguments cho `subprocess.run()`. *Effort: 1 giờ*
4. **Áp dụng `esc()` nhất quán** trong `app.js` — audit mọi `innerHTML` assignment chèn user-controlled data. *Effort: 3 giờ*
5. **Thêm admin role check** cho `/api/system/backtest`, `/api/system/test-weights`, `/api/system/dataset-stats`. *Effort: 1 giờ*

### P1 — Trong 1–2 tuần
6. **Consolidate magic numbers** — chuyển tất cả weights, thresholds, emotion labels vào `config.py` hoặc JSON config riêng
7. **Centralize emotion labels** — single source of truth (trong config), import ở mọi nơi
8. **Thêm rate limiting middleware** (`slowapi` hoặc custom) cho API endpoints
9. **Fix negation logic** trong `emotion_analysis.py` — sử dụng valence reduction thay vì opposite emotion addition
10. **Merge Unicode normalize functions** thành 1 utility duy nhất
11. **Cleanup event listeners** trong `app.js` — thêm cleanup function cho mỗi page renderer
12. **Xóa dead code** — `_track_id_to_song_index()` và các unused imports
13. **Fix password validation DRY** — extract shared validation logic

### P2 — Trong 1 tháng
14. **Tách `app.js`** → `router.js`, `auth.js`, `pages.js`, `ailab.js` (~2–3 ngày)
15. **Tách `styles.css`** → component modules (~1 ngày)
16. **Tạo Dockerfile + docker-compose** cho development và production
17. **Chuyển sang async DB** — `create_async_engine` + `AsyncSession`
18. **Externalize blocklists** — chuyển từ hardcode sang JSON/YAML file
19. **Thêm README.md** chi tiết với setup guide, architecture, API reference
20. **Thêm password reset flow** với email verification

### P3 — Long-term (1–3 tháng)
21. **CI/CD Pipeline** — GitHub Actions với lint, test, type check, security scan, auto-deploy
22. **Caching layer** — Redis cho recommendation results và session data
23. **Frontend framework** — migrate sang Svelte hoặc React components
24. **Unit tests cho API endpoints** — pytest + httpx cho tất cả routes
25. **Monitoring & Observability** — structured logging, health checks, metrics (Prometheus/Grafana)
26. **Content Security Policy** header cho frontend
27. **Refresh token mechanism** cho JWT authentication
28. **Audio playback state machine** — thay thế complex dual-audio crossfade logic

---

## 9. Kết Luận

### Đánh giá tổng thể

Brightify là một dự án **tham vọng và ấn tượng về mặt kỹ thuật** — đặc biệt ở khả năng AI/ML với fusion 7 tín hiệu recommendation, bộ từ điển cảm xúc tiếng Việt 500+ từ, và pipeline dữ liệu hoàn chỉnh 7 giai đoạn. Database schema star-schema chuẩn Data Warehouse với pgvector cho similarity search thể hiện thiết kế chuyên nghiệp. Authentication layer sử dụng best practices ngành (PBKDF2 310K iterations, timing-safe comparison).

Tuy nhiên, dự án có **vấn đề nghiêm trọng ở layer production-readiness**:
- Một endpoint core (`/api/recommend/mood`) không hoạt động do dead code bị ẩn
- Frontend monolithic 3,500 dòng JS với XSS risks chưa được xử lý triệt để
- Hoàn toàn thiếu DevOps infrastructure (Docker, CI/CD, monitoring)
- Error handling yếu với silent failures tràn lan trong pipeline và core modules

### Sức khỏe dự án: ⚠️ TRUNG BÌNH — KHÁ (5.75/10)

Dự án có **nền tảng vững chắc** về kiến trúc, thuật toán AI, và database design, nhưng cần **tập trung đáng kể vào engineering practices** (testing, security hardening, DevOps, code modularization) trước khi đưa vào production.

### Khuyến nghị cuối

| Ưu tiên | Hành động | Timeline |
|---------|-----------|----------|
| **#1** | Fix 5 vấn đề P0 — đặc biệt mood endpoint dead code và XSS sanitization | 1–2 ngày |
| **#2** | Đầu tư vào DevOps (Docker + CI/CD) để tự động hóa quality gates | 1–2 tuần |
| **#3** | Refactor frontend — tách `app.js` là bước cải thiện maintainability lớn nhất | 2–3 ngày |
| **#4** | Chuyển sang async DB, thêm caching, và xem xét frontend framework | 1–3 tháng |

Với ~2–3 tuần effort tập trung vào P0 + P1, dự án có thể đạt mức **production-ready** cho demo hoặc internal release.

---

*Báo cáo được tạo từ phân tích toàn bộ codebase (~29,500 dòng code, 75+ files). Mọi file path, line number và code snippet đều được xác minh trực tiếp từ source code.*
