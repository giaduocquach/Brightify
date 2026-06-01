# Brightify — Kế hoạch Tái cấu trúc Kiến trúc Toàn diện (V13)

> **Mục tiêu:** Đưa toàn bộ dự án (AI/ML · Backend/API · Frontend · Data Pipeline · Database · Infra) về một cấu trúc **đạt chuẩn công nghiệp 2025–2026**, có tính khoa học, tách bạch concern, dễ kiểm thử, dễ tái lập (reproducible) và dễ mở rộng — mà **không làm gãy** sản phẩm đang chạy.
>
> **Trạng thái:** Đề xuất (Proposal). Cần review & phê duyệt trước khi thực thi.
> **Ngày:** 2026-05-31 · **Tác giả:** DS/SA review · **Phiên bản codebase:** v7.x runtime / v12 feature.
> **Nguyên tắc tối thượng:** Mỗi bước migration phải **xanh test** (`python -m pytest test/`) và **không tụt số liệu backtest** (`tools/backtest_v2`) so với baseline trước khi merge.

---

## 0. Tóm tắt điều hành (Executive Summary)

Brightify là một hệ thống **trưởng thành, nhiều tín hiệu, có nền tảng nghiên cứu vững** (Russell Circumplex, Jonauskaite 2020, PhoBERT, MERT, CLAP, RRF, MMR/DPP). Kiến trúc **vĩ mô tốt** (tách layer frontend/API/core/db/infra, Docker hoá kỹ, feature-flag để A/B, có khung backtest khoa học `backtest_v2`). Tuy nhiên **vi mô có nợ kỹ thuật nghiêm trọng** tập trung ở vài "điểm nóng" monolith và thiếu các lớp trừu tượng tiêu chuẩn.

### Bảng điểm hiện trạng

| Phân hệ | Điểm /10 | Vấn đề chính | Mức ưu tiên |
|---|---|---|---|
| Core AI/ML | **4.5** | `recommendation_engine.py` = God Object 1990 dòng; trộn I/O + feature engineering + inference + fusion + ranking; singleton toàn cục; trùng lặp logic (Russell V-A, lyrics-encode) | 🔴 P0 |
| Backend/API | **5.5** | Fat controllers (`music.py` 798 dòng thao tác DataFrame trực tiếp); module-level globals thay vì DI; chỉ ~60% endpoint có Pydantic schema; API chạm thẳng DB & filesystem | 🔴 P0 |
| Data Pipeline/Tools | **5.0** | `collect_data.py` 4964 dòng (5-trong-1); trùng `VietnameseDetector`; data artifact sprawl, versioning ad-hoc; không có lineage/experiment tracking | 🟠 P1 |
| Config | **4.0** | 1 file 332 dòng trộn paths + weights + flags + model IDs; nhiều magic number vẫn hardcode trong code; không validate; không tách env | 🔴 P0 |
| Database | **6.5** | Bảng `Song` ~180 cột (metadata + audio + ML + lyrics + color + media trộn lẫn); seed all-or-nothing; migration thiếu `down()` | 🟠 P1 |
| Frontend | **6.0** | `player.js` 1426 dòng + `styles.css` 3241 dòng monolith; globals-on-window; không build tooling/lint | 🟡 P2 |
| Infra/DevOps | **7.5** | Docker 2-stage tốt, Makefile tốt, `var/` gọn; nhưng 4 compose drift, chưa validate env, chưa CI/CD | 🟡 P2 |
| Khung backtest | **8.5** | `backtest_v2/` là **hình mẫu** modular (baselines/metrics/ground_truth/improve/reporters) | ✅ Reference |
| **Tổng thể** | **5.7** | Tốt về macro & khoa học, nợ kỹ thuật ở micro-architecture | — |

**Luận điểm trung tâm:** `tools/backtest_v2/` đã chứng minh team **biết viết code modular đạt chuẩn** ngay trong repo này. Kế hoạch V13 là **nhân rộng kỷ luật đó** ra toàn bộ `core/`, `api/`, `tools/`, `config/`.

---

## 1. Phương pháp luận & Tiêu chuẩn tham chiếu

Đánh giá và thiết kế dựa trên các chuẩn được công nhận rộng rãi (2025–2026):

| Lĩnh vực | Chuẩn / Tham chiếu | Áp dụng vào Brightify |
|---|---|---|
| Backend layering | **Layered + Domain-Driven** (Router → Service → Repository → Model); business logic ra khỏi router; tách `schemas/` | Tái cấu trúc `api/` + thêm `services/` + `repositories/` |
| Dependency Injection | FastAPI `Depends()` thay module-global; testability | Xoá pattern `init(recommender, …)` |
| ML project layout | **Cookiecutter Data Science / Kedro** (tách `data/raw|interim|processed`, `pipelines/`, `config/`, `models/`) | Tổ chức lại `data/` + `tools/` thành pipeline nodes |
| Data/Model versioning | **DVC** (data ngoài Git, lineage, `dvc repro` chỉ chạy stage đổi dependency) | Quản lý `*.npy`/`*.csv`/`*.json` + manifest |
| Experiment tracking | **MLflow / W&B** (param–metric–artifact, run registry) | Gắn vào `backtest_v2` + relabel/optimize |
| Clean Architecture | **Ports & Adapters (Hexagonal)** — core không phụ thuộc I/O cụ thể | `DataSource` interface (CSV ↔ DB ↔ pgvector) |
| Strategy pattern | Mỗi tín hiệu reco là một strategy độc lập, có thể bật/tắt/ablate | Tách 7–8 signal khỏi God Object |
| 12-Factor App | Config qua env, tách build/run, log ra stdout | Đã làm phần lớn; chuẩn hoá `config/` |
| Packaging | `pyproject.toml` + layout `src/`, có thể `pip install -e .` | Bỏ import phụ thuộc cwd |

**Nguồn tham chiếu:**
- [FastAPI Best Practices (zhanymkanov)](https://github.com/zhanymkanov/fastapi-best-practices) — domain-based structure, service layer.
- [FastAPI Project Structure: Production Guide 2026 (Zestminds)](https://www.zestminds.com/blog/fastapi-project-structure/) — Models → Repositories → Services → Routers.
- [Building Production-Ready FastAPI with Service Layer (Medium)](https://medium.com/@abhinav.dobhal/building-production-ready-fastapi-applications-with-service-layer-architecture-in-2025-f3af8a6ac563).
- [Cookiecutter Data Science / Kedro MLOps templates](https://github.com/Chim-SO/cookiecutter-mlops) — `data/raw|processed`, `config/`, pipeline nodes.
- [Structuring ML Projects with MLOps in Mind (TDS)](https://towardsdatascience.com/structuring-your-machine-learning-project-with-mlops-in-mind-41a8d65987c9/).
- [DVC — Data Version Control](https://doc.dvc.org/user-guide) — data lineage & reproducibility.

---

## 2. Đánh giá hiện trạng chi tiết (Current-State Findings)

### 2.1 Core AI/ML — God Object 🔴

**`core/recommendation_engine.py` (1990 dòng, class `MusicRecommender`)** ôm 7 trách nhiệm:
1. Data loading (CSV/NPY/JSON) — `__init__:36–163`
2. Feature engineering & normalize — `_normalize_audio_features`, `_precompute_all_features:180–259`
3. Model inference (PhoBERT/CLAP/MERT) — rải rác
4. Signal fusion — `_color_score:559–595`, fusion `recommend_by_song`
5. Retrieval (RRF) — `_rrf_candidates`
6. Diversity ranking (MMR/DPP/greedy) — `_fast_rank:1678–1786`
7. Public API (color/song/audio/image/lyrics)

**Hệ quả & bằng chứng:**
- **Trộn I/O với business logic:** đổi nguồn dữ liệu CSV→DB phải viết lại toàn bộ `__init__`. Path hardcode tương đối (`config.py:27–29`), giả định cwd = project root.
- **Singleton toàn cục** (`_recommender`, + 8 singleton khác ở `emotion_analysis`, `color_mapping`, `image_analysis`, `clap`, `mert`, `reranker`): test phải nạp full dataset (~5–10s/startup), không inject mock, state rò rỉ giữa test (`reload=True` là hack).
- **Trùng lặp logic (DRY vi phạm):**
  - Russell V-A mapping ở `recommendation_engine.py:303–306` **và** `advanced_color_mapping.py:42–108` — **giá trị lệch nhau** (happy valence 0.90 vs 0.88), không rõ cái nào đúng.
  - Lyrics encode+normalize lặp ở `recommend_by_colors:469–483` và `recommend_by_lyrics_keywords:1813–1820`.
  - `VietnameseDetector` viết ở `tools/collect_data.py` nhưng `tools/filter_data.py` **tự reimplement** thay vì import.
- **Magic number rải trong code** thay vì config: cap 3 màu (`:427`), RBF sigma (`:449`), trọng số `0.40/0.30/0.30` (`:573`), quadrant penalties (`:582–590`).
- **Dead/disconnected code:** `recommend_by_audio()` không route nào gọi; `_sentiment_vec` load nhưng không dùng; `lyrics_router.py` (Pillar B) chưa nối vào inference; `retrieval.py` RRF chỉ dùng ở `recommend_by_song`, color thì hardcode fusion → chiến lược retrieval **không nhất quán**.
- **Coupling chéo:** `app.py:51–85` vá cột crossfade từ DB vào `recommender.df` sau init (order-dependent, fragile, fail-silent).

### 2.2 Backend/API — Fat Controllers, thiếu DI & schema 🔴

- **Module-level globals + `init()`** (`app.py:122–124` bơm `recommender/paths` vào từng module; `music.py:20–26`, `recommend.py:22–24`, `system.py:25–26`) thay vì `Depends()`. → không test cô lập được, không request-scope.
- **Fat controllers:** `music.py` (798 dòng) thao tác DataFrame trực tiếp ~53 chỗ: `browse_songs:164–223`, `time_of_day_songs:262–322` (Gaussian scoring inline), `_song_to_dict:74–157` (serialize + file-exists + URL build). Logic lọc/sort lặp lại, không tái dùng.
- **Schema không đồng nhất:** chỉ `recommend.py`/`system.py` có Pydantic; toàn bộ `music.py` trả raw dict, không `response_model`. Không có thư mục `schemas/`.
- **Vi phạm layering:** `system.py:62–71` query DB trong health; `app.py:62–72` query SQL thô lúc startup; `music.py:29–72` đọc JSON/CSV trực tiếp; `recommend.py:27–46` & `utils.py:42–50` quét filesystem.
- **Validation/HTTP status lẫn lộn:** chỗ Pydantic validator, chỗ kiểm ký tự thủ công (`music.py:699–700`); `track_id` không giới hạn độ dài; status code không nhất quán (404 cho "service unavailable").
- **Điểm mạnh giữ nguyên:** rate limit sliding-window có Redis fallback, `hmac.compare_digest`, CORS tập trung, chống decompression-bomb ảnh, cache Redis graceful.

### 2.3 Data Pipeline/Tools — Monolith & data sprawl 🟠

- **File khổng lồ trộn concern:** `collect_data.py` 4964 dòng (Spotify client + YTMusic discovery + VietnameseDetector 1412 dòng + LRCLIB + pipeline); `extract_audio_features.py` 1264 (Essentia DSP + TF heads + LUFS/librosa, MODEL_REGISTRY hardcode); `filter_data.py` 1051; `process_data.py` 786.
- **Data artifact sprawl** (`data/`, ~129MB, 15+ file): versioning ad-hoc — `emotion_labels_v2/v3` có version, `*_embeddings_full.npy` không; `.bak.npy` không dọn; `*_checkpoint.json` mồ côi; `lyrics_backup.json` 28MB không rõ active. **Không có `MANIFEST`/lineage.**
- **Không có experiment tracking** (MLflow/DVC/W&B): chỉ JSON/CSV/NPY thủ công; checkpoint pipeline bị xoá mỗi lần chạy (mất lịch sử); `config.py` bị sửa tại chỗ bởi backtest CLI (`cli.py` `_update_config_weights`) → không version config.
- **Hình mẫu ngược lại:** `backtest_v2/` chia `baselines/ metrics/ ground_truth/ improve/ reporters/`, dataclass config, baseline <50 dòng — **chuẩn cần nhân rộng.**

### 2.4 Config — Monolith, magic number, không validate 🔴

`config.py` (332 dòng) trộn: secrets + paths + model IDs + feature lists + 10+ bộ weights + Russell quadrants + Pillar A–F flags + viz settings. Không tách env (dev/prod dùng chung số), không schema validation (typo silent), nhiều giá trị vẫn hardcode trong `core/`.

### 2.5 Database — Bảng God 🟠

Bảng `Song` ~180 cột trộn 8 nhóm concern (Spotify metadata / audio features / ML predictions / lyrics / color / emotion derived / media availability / processing meta). Nhiều cột nullable → coalesce khắp nơi. JSON columns không validate. `seed.py` all-or-nothing (fail giữa chừng → DB bẩn). Migration thiếu `down()` rõ ràng.

### 2.6 Frontend — Monolith JS/CSS 🟡

SPA vanilla, globals-on-window, **không build tooling/lint/test**. `player.js` 1426 dòng (playback + visualizer + queue + radio + sleep timer + like tracking), `styles.css` 3241 dòng một file, không responsive/media query, thứ tự `<script>` quan trọng (crossfade trước player). `api.js` là client mỏng sạch — giữ.

### 2.7 Infra — Tốt, cần hợp nhất 🟡

Docker 2-stage (build/runtime tách, non-root, pin amd64 cho essentia), `var/` layout gọn (secrets 700, volumes bind-backed, backups, logs), Makefile đầy đủ. Nhược: 4 compose file drift (DRY), chưa validate env bắt buộc, **chưa có CI/CD**, nginx chưa thấy security headers/TLS enforce.

---

## 3. Kiến trúc mục tiêu (Target Architecture)

### 3.1 Nguyên tắc thiết kế

1. **Hexagonal core:** `core/` chứa logic thuần, phụ thuộc vào **interface** (`DataSource`, `Embeddings`, `EmotionProvider`) chứ không phụ thuộc CSV/DB cụ thể → đổi nguồn không sửa logic.
2. **Layered API:** `Router (HTTP) → Service (workflow) → Repository (data access) → Model`. Router mỏng, không chứa business logic, không chạm DataFrame/DB/FS.
3. **Strategy cho signals:** mỗi tín hiệu (timbral/rhythmic/tonal/lyrics/va/emotion/mood/mert/kg) là một class `Signal` riêng, đăng ký vào `FusionEngine`; ablation = bật/tắt strategy, không sửa God Object.
4. **Single Source of Truth:** Russell V-A, emotion profiles, mọi weight/threshold/path nằm **một chỗ** trong `config/` (đã validate bằng Pydantic Settings).
5. **Reproducibility:** data/model versioned bằng DVC + manifest; mọi experiment ghi vào tracker (param/metric/artifact); config snapshot theo run.
6. **Packaging chuẩn:** `pyproject.toml`, layout `src/brightify/`, cài `pip install -e .` → hết phụ thuộc cwd.
7. **Bất biến khoa học:** không đổi thuật toán/trọng số khi refactor; mọi thay đổi hành vi phải qua `backtest_v2` với CI và Bonferroni như hiện tại.

### 3.2 Cấu trúc thư mục mục tiêu

```
brightify/
├── pyproject.toml                # packaging + deps + tool config (ruff, mypy, pytest)
├── README.md  CLAUDE.md  Makefile  Dockerfile
├── dvc.yaml  .dvc/               # data/model versioning + pipeline stages
├── compose/                      # hợp nhất compose (base + override theo env)
│   ├── docker-compose.yml
│   └── overrides/{dev,staging,prod}.yml
│
├── src/brightify/                # ⬅ package cài đặt được (src-layout)
│   │
│   ├── config/                   # 🔧 Config có cấu trúc + validate (thay config.py)
│   │   ├── __init__.py           #    Settings tổng (Pydantic BaseSettings, đọc .env)
│   │   ├── paths.py              #    path tuyệt đối, suy từ project root
│   │   ├── models.py             #    model IDs + hyperparams (PhoBERT/CLAP/MERT/CLIP)
│   │   ├── recommendation.py     #    MỌI weight/threshold (gồm các magic number đã gom)
│   │   ├── color.py  mood.py     #    HSL ranges, Russell quadrants, keywords
│   │   └── features.py           #    AUDIO_FEATURES, NORMALIZED_FEATURES
│   │
│   ├── domain/                   # 🧠 Logic thuần, KHÔNG biết I/O cụ thể
│   │   ├── emotion/              #    lexicon, V-A mapping (SSoT Russell), fusion
│   │   ├── color/                #    CIEDE2000, color→V-A→emotion (Jonauskaite)
│   │   ├── signals/              #    ⬅ tách God Object thành strategies
│   │   │   ├── base.py           #       interface Signal.score(query, catalog)->np.ndarray
│   │   │   ├── timbral.py rhythmic.py tonal.py
│   │   │   ├── lyrics.py va.py emotion.py mood.py
│   │   │   ├── mert.py kg.py
│   │   ├── retrieval.py          #    RRF (Cormack 2009) — dùng CHUNG cho mọi query
│   │   ├── diversity.py          #    MMR / DPP
│   │   └── reranker.py           #    cross-encoder (Pillar C)
│   │
│   ├── ml/                       # 🤖 Inference wrappers + ports cho model
│   │   ├── ports.py              #    interface: Embedder, EmotionProvider, ImageEncoder
│   │   ├── phobert.py clap.py mert.py clip.py
│   │   └── lyrics_router.py      #    Pillar B routing (nối vào inference)
│   │
│   ├── data/                     # 💾 Ports & Adapters cho nguồn dữ liệu (Hexagonal)
│   │   ├── source.py             #    interface DataSource (load_songs/embeddings/emotions)
│   │   ├── csv_source.py         #    adapter CSV (dev/offline)
│   │   ├── db_source.py          #    adapter PostgreSQL/pgvector
│   │   ├── catalog.py            #    Catalog: dataframe + matrices precomputed (lazy)
│   │   └── feature_engineer.py   #    normalize + precompute (testable độc lập)
│   │
│   ├── services/                 # 🧩 Tầng nghiệp vụ (orchestration)
│   │   ├── recommender.py        #    RecommenderService: gọi signals+fusion+rerank
│   │   ├── music_service.py      #    browse/search/featured/time-of-day
│   │   └── system_service.py     #    health/stats/moods
│   │
│   ├── repositories/             # 🗄 Truy cập dữ liệu (DataFrame/DB) — tách khỏi API
│   │   ├── song_repository.py
│   │   └── media_repository.py   #    resolve path mp3/album_art/artist_images
│   │
│   ├── api/                      # 🌐 HTTP layer mỏng (chỉ I/O HTTP)
│   │   ├── app.py                #    FastAPI factory + lifespan
│   │   ├── dependencies.py       #    Depends() providers (thay module-globals)
│   │   ├── schemas/              #    Pydantic request/response cho MỌI endpoint
│   │   │   ├── music.py recommend.py system.py common.py  # {success,error} envelope
│   │   ├── routers/              #    router mỏng theo domain
│   │   │   ├── music.py recommend.py system.py
│   │   ├── middleware/           #    rate_limit.py  cache.py
│   │   └── errors.py             #    exception handlers + status map chuẩn hoá
│   │
│   ├── db/                       # ORM + engine + migrations runtime
│   │   ├── engine.py
│   │   └── models/               #    tách Song God-table → core/features/lyrics/media
│   │
│   └── observability/            # logging_config + metrics hooks
│
├── pipelines/                    # 🏭 Data pipeline (thay tools/ monolith) — Kedro-style nodes
│   ├── orchestrator.py           #    7-phase gate (từ pipeline.py)
│   ├── collect/                  #    spotify_client.py ytmusic.py lyrics_fetcher.py
│   ├── nlp/language_detect.py    #    VietnameseDetector (SSoT, import được từ domain)
│   ├── audio/                    #    essentia_extractor.py tf_models.py librosa_fallback.py
│   ├── embeddings/               #    phobert_embed.py mert_embed.py kg_build.py
│   ├── labeling/                 #    relabel_emotions.py relabel_llm.py (gọi domain.emotion)
│   └── seed.py                   #    CSV→PostgreSQL (idempotent, transactional)
│
├── evaluation/                   # = backtest_v2 (giữ nguyên cấu trúc, đổi tên rõ)
│   └── {baselines,metrics,ground_truth,improve,reporters}/
│
├── frontend/                     # static/ tổ chức lại
│   ├── index.html
│   ├── css/{tokens,base,components/,pages/}.css   # tách styles.css 3241 dòng
│   └── js/
│       ├── api.js                # giữ (client sạch)
│       ├── core/{router,state,events}.js
│       ├── player/{engine,visualizer,queue,crossfade}.js  # tách player.js 1426 dòng
│       └── pages/*.js
│
├── data/                         # 📦 DVC-managed, theo Cookiecutter DS
│   ├── raw/                      #    nguồn gốc (collect/download)
│   ├── interim/                  #    checkpoints phase 1–5
│   ├── processed/                #    *.csv, *.npy active (đã versioned)
│   ├── external/                 #    pmemo, datasets ngoài
│   ├── archive/                  #    *.bak.npy, version cũ
│   └── MANIFEST.yaml             #    SSoT: artifact active + version + lineage + ngày
│
├── models_cache/  music_files/  album_art/  artist_images/   # binary lớn (gitignore/DVC)
├── var/                          # runtime/secrets/volumes/backups/logs (giữ)
├── tests/                        # unit + integration + e2e (mirror src/)
│   ├── unit/  integration/  e2e/  conftest.py (fixtures + mock DataSource)
├── alembic/                      # migrations (bổ sung down() đầy đủ)
└── docs/                         # tài liệu (gồm file này)
```

### 3.3 Luồng phụ thuộc mục tiêu (Dependency Rule)

```
api/routers → api/schemas
            → services → repositories → data(adapters) → db | csv
                       → domain(signals, fusion, retrieval, diversity)
                       → ml(ports → phobert/clap/mert/clip)
config ← (mọi layer đọc, không ai ghi runtime)
```

Quy tắc: **mũi tên chỉ đi xuống**. `domain/` & `config/` không import `api/`, `services/`, `db/`. Đây là điều kiện để test `domain` không cần FastAPI/DB.

---

## 4. Lộ trình Migration (Phased Roadmap)

> Chiến lược: **strangler-fig** — dựng cấu trúc mới song song, chuyển dần từng phần sau lớp adapter/shim, mỗi bước giữ test xanh + backtest không tụt. **Không big-bang rewrite.**

### Phase 0 — Nền móng an toàn (1 tuần) · 🔴 P0 bắt buộc trước
- [ ] Thêm `pyproject.toml`, chuyển sang `src/`-layout, `pip install -e .` → bỏ phụ thuộc cwd; cập nhật Dockerfile/Makefile/imports.
- [ ] Cài `ruff` + `mypy` + `pytest-cov`; thiết lập **CI (GitHub Actions)**: lint + type + `pytest` + smoke backtest trên PR.
- [ ] **Baseline đóng băng:** chạy `tools/backtest_v2` lưu `evaluation/reports/iter_0_prerefactor/` làm mốc regression cho mọi phase sau.
- [ ] Thêm `data/MANIFEST.yaml` + di chuyển `*.bak`/checkpoint mồ côi vào `data/archive/`. Khởi tạo DVC (`dvc init`), track `data/processed/*` + `models_cache/`.
- **Gate:** CI xanh; backtest = baseline; app khởi động bình thường.

### Phase 1 — Config hoá (3–4 ngày) · 🔴 P0
- [ ] Tạo package `config/` (Pydantic `BaseSettings`) gom toàn bộ `config.py`; giữ `config.py` thành shim re-export để không gãy import cũ.
- [ ] **Gom mọi magic number** từ `core/` vào `config/recommendation.py` (cap màu, RBF sigma, `0.40/0.30/0.30`, quadrant penalties…).
- [ ] **Hợp nhất Russell V-A** về một bảng duy nhất trong `config/color.py` (giải quyết lệch 0.90/0.88 — chọn giá trị đúng, ghi chú nguồn); `core` đọc từ đó.
- **Gate:** backtest = baseline (giá trị weight không đổi, chỉ đổi nơi khai báo).

### Phase 2 — Tách Core God Object (2–3 tuần) · 🔴 P0 (giá trị cao nhất)
- [ ] Trích `DataSource` interface + `CsvSource` (giữ hành vi hiện tại) + `Catalog` + `FeatureEngineer` từ `__init__`/`_precompute_all_features`.
- [ ] Trích từng **Signal** thành strategy (`domain/signals/*`); `FusionEngine` đọc weight từ config; `recommend_by_song` dùng RRF + fusion qua strategies.
- [ ] Dùng RRF **nhất quán** cho cả color query (bỏ hardcode fusion).
- [ ] `RecommenderService` thay phần public-API của God Object; `MusicRecommender` thành facade mỏng (backward-compat) trong giai đoạn chuyển.
- [ ] Thêm DI: `set_recommender()`/factory cho test; viết **unit test signal** với mock `DataSource` (không cần full dataset).
- [ ] Dọn dead code: `recommend_by_audio` (route hoá hoặc xoá), `_sentiment_vec`, hợp nhất 2 đường lyrics-encode thành 1 util.
- **Gate:** backtest từng pillar = baseline (ablation qua strategy phải khớp số cũ); test coverage signals > 70%.

### Phase 3 — Service/Repository/Schema cho API (1.5–2 tuần) · 🔴 P0
- [ ] Tạo `repositories/` (song/media) — chuyển toàn bộ thao tác DataFrame & file-resolve khỏi `music.py`.
- [ ] Tạo `services/music_service.py`, `system_service.py`; router chỉ còn parse request → gọi service → trả schema.
- [ ] Thêm `schemas/` Pydantic cho **mọi** endpoint (request + response, `response_model=`), envelope `{success,error}` chuẩn hoá.
- [ ] Thay `init(recommender,…)` + module-global bằng `Depends()` providers; chuyển DB-query startup & health vào service.
- [ ] `errors.py`: map exception → status code nhất quán; thêm `max_length` cho input.
- **Gate:** hợp đồng API không đổi (so OpenAPI schema cũ/mới + e2e smoke test); frontend chạy nguyên.

### Phase 4 — Pipeline & Data versioning (1.5–2 tuần) · 🟠 P1
- [ ] Tách `collect_data.py` → `pipelines/collect/*`; `VietnameseDetector` → `pipelines/nlp/language_detect.py` (SSoT, `filter_data` import lại).
- [ ] Tách `extract_audio_features.py` → `pipelines/audio/*`; `MODEL_REGISTRY` ra `config/models.py`/YAML.
- [ ] Phase script thành CLI mỏng gọi module; mỗi file mục tiêu < 300–400 dòng.
- [ ] Khai báo `dvc.yaml` stages (collect→…→seed) để `dvc repro` chỉ chạy lại stage đổi.
- [ ] Gắn **experiment tracking** (MLflow nhẹ hoặc JSONL registry) vào `backtest_v2` + relabel/weight-opt; ngừng sửa `config.py` tại chỗ → ghi `evaluation/runs/<id>/config_snapshot.yaml`.
- **Gate:** chạy lại 1 phase end-to-end cho ra artifact tương đương; manifest cập nhật tự động.

### Phase 5 — Database normalization (1–1.5 tuần) · 🟠 P1
- [ ] Tách `Song` → `SongCore` + `SongAudioFeatures` + `SongMLFeatures` + `SongLyrics` + `SongMedia` (hoặc view/hybrid_property giữ tương thích query).
- [ ] `seed.py` idempotent + transactional (rollback khi lỗi giữa chừng).
- [ ] Bổ sung `down()` cho migration; thêm test migration up/down trên DB tạm.
- **Gate:** seed lại ra cùng số bản ghi; query reco/browse không đổi kết quả.

### Phase 6 — Frontend & Infra (1–1.5 tuần) · 🟡 P2
- [ ] Tách `player.js` → `player/{engine,visualizer,queue,crossfade}.js`; `styles.css` → `tokens/base/components/pages`.
- [ ] Thêm tooling tối thiểu: ESLint + Prettier (có thể esbuild bundle, vẫn giữ vanilla).
- [ ] Hợp nhất compose: 1 base + overrides; thêm script validate env bắt buộc trước `make dev`; thêm security headers nginx.
- **Gate:** UI hồi quy thủ công các luồng chính (play, color reco, journey, search); compose dev/prod lên được.

### Tổng thời lượng ước tính: **~9–12 tuần** (1 kỹ sư) — có thể song song Phase 4–6 nếu nhiều người.

---

## 5. Cross-cutting concerns

| Khía cạnh | Hiện tại | Mục tiêu |
|---|---|---|
| **Testing** | Test rời rạc ở `test/`, không mock được core | `tests/{unit,integration,e2e}` mirror `src/`; `conftest` cấp mock `DataSource`; unit test domain không cần DB/model; coverage gate ≥ 70% core |
| **CI/CD** | Không có | GitHub Actions: ruff + mypy + pytest + smoke backtest; build image; (tuỳ) deploy staging |
| **Reproducibility** | JSON/CSV/NPY thủ công, checkpoint bị xoá | DVC pipeline + remote storage; `MANIFEST.yaml` lineage; config snapshot/run |
| **Experiment tracking** | Đặt tên iter thủ công | MLflow/JSONL registry: param↔metric↔artifact, so sánh run |
| **Observability** | loguru tốt | + Prometheus metrics (latency reco, cache hit), `/metrics` endpoint, Sentry (DSN đã có chỗ) |
| **Secrets/Config** | env + docker secret tốt | Pydantic Settings validate khi boot; fail-fast nếu thiếu biến bắt buộc |
| **Docs** | 26 file, nhiều trùng/cũ | Gộp về `docs/` có index; archive báo cáo cũ; file này là master kiến trúc |

---

## 6. Quản trị rủi ro (Risk Register) & Non-goals

**Rủi ro & giảm thiểu:**
1. *Tụt chất lượng reco khi tách signal* → mỗi phase chốt bằng `backtest_v2` so baseline iter_0; chỉ refactor (không đổi thuật toán/số).
2. *Gãy hợp đồng API* → snapshot OpenAPI + e2e smoke; giữ facade/shim chuyển tiếp.
3. *Đứt import do đổi layout* → shim re-export (`config.py`, `core/recommendation_engine.py`) trong suốt giai đoạn chuyển; xoá ở cuối.
4. *Phình phạm vi* → tuân thủ thứ tự phase P0→P2; không trộn refactor với feature mới.
5. *Migration DB hỏng dữ liệu* → làm trên bản backup; bắt buộc `down()` + test up/down.

**Non-goals (KHÔNG làm trong V13):**
- Không đổi mô hình AI/trọng số/thuật toán (đó là việc của các PLAN feature riêng).
- Không thêm tính năng người dùng mới.
- Không đổi tech stack lõi (FastAPI/Postgres/vanilla JS giữ nguyên).
- Không rewrite frontend sang framework (chỉ modular hoá vanilla).

---

## 7. Tiêu chí nghiệm thu (Definition of Done)

- [ ] `pip install -e .` chạy; không còn import phụ thuộc cwd.
- [ ] `core/`/`domain/` test được **không cần** DB hay nạp full model (mock `DataSource`).
- [ ] Không file nguồn nào > ~600 dòng (trừ data/migration); God Object bị tách.
- [ ] Mọi endpoint có Pydantic request+response; router không chạm DataFrame/DB/FS.
- [ ] Mọi weight/threshold/path/magic-number nằm trong `config/` (validated); Russell V-A SSoT.
- [ ] `data/MANIFEST.yaml` + DVC quản lý artifact; không `.bak` rải rác; experiment có tracker.
- [ ] CI xanh (lint+type+test+smoke backtest) trên mọi PR.
- [ ] Backtest cuối ≥ baseline iter_0 trên mọi pillar (không hồi quy chất lượng).
- [ ] Bảng `Song` được chuẩn hoá; migration có `down()`.
- [ ] Frontend `player.js`/`styles.css` đã tách; có lint.

---

## 8. Phụ lục — Bản đồ "trước → sau" (Quick Reference)

| Hiện tại | Sau V13 |
|---|---|
| `config.py` (332 dòng) | `src/brightify/config/` (package validated) |
| `core/recommendation_engine.py` (1990) | `domain/signals/*` + `domain/retrieval,diversity,reranker` + `services/recommender.py` + `data/catalog.py` |
| `api/music.py` (798, fat) | `api/routers/music.py` (mỏng) + `services/music_service.py` + `repositories/song_repository.py` + `api/schemas/music.py` |
| `init(recommender,…)` + globals | `api/dependencies.py` (`Depends()`) |
| `tools/collect_data.py` (4964) | `pipelines/collect/*` + `pipelines/nlp/language_detect.py` |
| `tools/extract_audio_features.py` (1264) | `pipelines/audio/*` + `config/models.py` |
| `tools/backtest_v2/` | `evaluation/` (giữ — đã chuẩn) |
| `data/*.npy,*.csv,*_v2/v3.json,*.bak` | `data/{raw,interim,processed,archive}` + DVC + `MANIFEST.yaml` |
| Bảng `Song` 180 cột | `SongCore/AudioFeatures/MLFeatures/Lyrics/Media` |
| `static/` (player.js 1426, styles.css 3241) | `frontend/js/player/*`, `frontend/css/{tokens,components,pages}` |
| 4 compose drift | `compose/` base + overrides |
| (không có) | CI/CD, DVC, MLflow tracking, `pyproject.toml`, ruff/mypy |

---

*Hết. Đề nghị review Mục 3 (cấu trúc mục tiêu) và Mục 4 (lộ trình) trước; sau khi chốt sẽ mở các PR theo từng phase với gate test+backtest.*
