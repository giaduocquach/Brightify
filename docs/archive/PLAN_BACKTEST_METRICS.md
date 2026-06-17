# PLAN 2 — BACKTEST + CẢI THIỆN HỆ THỐNG (vòng lặp)

**Ngày viết lại:** 2026-05-27 (v3 — tích hợp improvement loop)
**Thay thế:** bản v2 (2026-05-27) chỉ đo, không có vòng cải thiện.
**Phạm vi:** Framework backtest offline cho hệ thống **không có user** → đo → tìm điểm yếu → cải thiện → đo lại → báo cáo. Một chu kỳ khép kín.

> **3 thay đổi lớn so với bản v2:**
> 1. **Không có user → chọn metric phù hợp thật sự** — loại hẳn mọi metric cần interaction history, chỉ giữ offline-valid.
> 2. **Vòng lặp Measure → Identify → Tune → Re-measure** — không chỉ gate mà còn dùng kết quả để cải thiện weights và thứ tự nâng cấp pillar.
> 3. **Final report template** — định nghĩa trước báo cáo cuối sẽ trình bày gì, kết quả thế nào, cải thiện như nào, lý do.

---

## MỤC LỤC

1. [Mục tiêu & nguyên tắc](#1-mục-tiêu--nguyên-tắc)
2. [Data reality — đối chiếu DB thật](#2-data-reality--đối-chiếu-db-thật)
3. [Offline-only metric selection — tại sao chọn cái này](#3-offline-only-metric-selection)
4. [Validity threats & cách xử lý](#4-validity-threats--cách-xử-lý)
5. [Decommission legacy backtest](#5-decommission-legacy-backtest)
6. [Kiến trúc framework — Measure + Improve loop](#6-kiến-trúc-framework)
7. [Ground truth strategy](#7-ground-truth-strategy)
8. [Bộ metric — phân nhóm đầy đủ](#8-bộ-metric)
9. [Baseline systems](#9-baseline-systems)
10. [Scenarios — map 1:1 với 6 method thật](#10-scenarios)
11. [Vòng lặp cải thiện — Weight Opt + Pillar Priority](#11-vòng-lặp-cải-thiện)
12. [Statistical methodology](#12-statistical-methodology)
13. [Implementation roadmap (iterative)](#13-implementation-roadmap)
14. [Final Report Template](#14-final-report-template)
15. [Backlog — data blocked](#15-backlog)
16. [Tài liệu tham khảo](#16-tài-liệu-tham-khảo)

---

## 1. MỤC TIÊU & NGUYÊN TẮC

### 1.1 Mục tiêu

Hệ thống hiện tại **không có user, không có interaction history**. Mọi đánh giá phải offline-valid. Mục tiêu:

1. **Đo trạng thái hiện tại** (v7.2) bằng metric offline hợp lệ.
2. **Tìm điểm yếu cụ thể** qua ablation và discriminativeness check.
3. **Cải thiện có căn cứ** — weight optimization + upgrade pillar theo thứ tự ablation chỉ ra.
4. **Đo lại sau mỗi cải thiện** — so sánh delta có CI.
5. **Xuất báo cáo cuối** — trình bày toàn bộ chu kỳ: đo gì, kết quả, cải thiện thế nào, lý do.

### 1.2 Nguyên tắc

1. **Offline-first** — không tự nhét metric cần user history vào, không giả vờ chạy được.
2. **Validity-first** — ground truth phải gắn nhãn `external` / `semi-independent` / `engine-derived`. Chỉ 2 nhãn đầu được dùng để kết luận "tốt hơn".
3. **No tautology** — không đo engine bằng chính input của nó (V-A/quadrant/emotion là input → không làm relevance label).
4. **Improvement-driven** — mỗi số đo phải dẫn đến hành động cụ thể (tune weight, upgrade pillar, hoặc "không cần làm gì").
5. **Reproducible** — seed=42, lock version, catalog đồng nhất với engine.
6. **Report-ready** — mọi số đo kèm CI 95%, support N, nhãn validity.

---

## 2. DATA REALITY — ĐỐI CHIẾU DB THẬT

Truy vấn DB Docker (`brightify_db`, 5,548 songs) ngày 2026-05-27:

| Trường | Trạng thái | Dùng được cho |
|---|---|---|
| `valence`, `energy`, `arousal` | ✅ 5548/5548 | MoodCoherence, V-A, Calibration |
| `tempo` | ✅ 5548/5548 | TempoCoherence |
| `color_hex` | ✅ 5548/5548 | ColorCoherence (CIEDE2000) |
| PhoBERT 768-dim embeddings | ✅ 5548/5548 | ILD_lyrics, lyrics search |
| Essentia audio features (timbral/rhythmic/tonal) | ✅ 5548/5548 | ILD_audio, ablation |
| `fused_emotion` (13 lớp, runtime) | ✅ | Calibration error |
| `mood_quadrant` | ✅ nhưng **lệch nặng** | Stratify sampling (không làm relevance label) |
| `mood_tags` (MTG-Jamendo JSON) | ⚠️ chất lượng thấp | Semi-independent GT — phải qua discriminativeness check trước |
| `genres` / `artist_genres` | ❌ **0 rows** | → Backlog §15 |
| `popularity` | ❌ **toàn bộ = 0** | → Backlog §15 |
| `release_year` | ❌ **rỗng** | → Backlog §15 |
| user interactions | ❌ **dropped** | → Backlog §15 |

### 2.1 Phân bố mood_quadrant (mất cân bằng nghiêm trọng)

```
Q3 Sad/Depressed : 3459  (62.3%)
Q4 Calm/Peaceful : 1991  (35.9%)
Q1 Happy/Excited :   84  ( 1.5%)
Q2 Angry/Tense   :   14  ( 0.25%)
```

Q2 (n=14): **exempt khỏi pass/fail per-quadrant** — chỉ 14 bài, statistically vô nghĩa. Gộp Q1+Q2 = "high-energy" khi cần phân tích.
Quadrant **chỉ dùng để stratify sampling**, không bao giờ làm relevance label.

---

## 3. OFFLINE-ONLY METRIC SELECTION

### Tại sao không dùng metric cần user?

Hệ thống không có user, không có play history, không có ratings. Các metric phổ biến như RMSE, CTR, dwell time, serendipity user-based, CF precision — **đều cần interaction data**. Cố tình implement chúng = tạo số vô nghĩa.

### Metric hợp lệ cho hệ thống offline content-based:

```
Câu hỏi đặt ra → Metric trả lời

"Recommendations có đa dạng không?"
    → ILD (Inter-List Diversity) trong 4 không gian

"Catalog có được phơi bày đều không?"
    → Coverage, Artist Gini

"Recommendations có giữ mood nhất quán không?"
    → MoodCoherence, TempoCoherence, ColorCoherence

"Phân bố cảm xúc trong recs có khớp với seed không?"
    → Calibration error (KL divergence, 13 emotion)

"Nếu A gợi ý B thì B có gợi ý lại A không?"
    → Similar-song symmetry (consistency)

"Recommendations có bất ngờ / không quá gần seed không?"
    → Content-serendipity proxy (1 − sim(item, seed))

"Engine chạy nhanh không?"
    → Latency p50/p95/p99

"Có đúng với playlist người thật tạo không?" (cần crawl)
    → NDCG@K, Precision@K, Recall@K với editorial playlists
```

**Bảng quyết định metric — giữ hay bỏ:**

| Metric | Giữ? | Lý do |
|---|---|---|
| ILD (4 không gian) | ✅ GIỮ | Hoàn toàn offline, đo diversity recs |
| Coverage, Artist Gini | ✅ GIỮ | Catalog-level, không cần user |
| MoodCoherence, TempoCoherence, ColorCoherence | ✅ GIỮ | Brightify-specific, dùng ngay |
| Calibration error (KL/13 emotion) | ✅ GIỮ | Offline, diagnose emotion distribution |
| Similar-song symmetry | ✅ GIỮ | Offline consistency check |
| Content-serendipity proxy | ✅ GIỮ | Proxy hợp lệ khi không có user |
| Latency p50/p95/p99 | ✅ GIỮ | Operational, không cần data |
| NDCG/P/R với editorial playlists | ✅ GIỮ (Phase 2+) | External GT, valid |
| NDCG/P/R với V-A/quadrant làm GT | ❌ BỎ | Tautology — input của engine |
| Novelty/EFD/AvgPopRank | ❌ BỎ | popularity=0, không có data |
| GenreCoherence | ❌ BỎ | genres=0, không có data |
| Serendipity user-based | ❌ BỎ | Cần interaction history |
| CF baselines | ❌ BỎ | Cần interaction history |
| Temporal split | ❌ BỎ | release_year rỗng |

---

## 4. VALIDITY THREATS & CÁCH XỬ LÝ

### 4.1 Tautology (mối đe dọa số 1)

Engine `recommend_by_song` fuse 7 signal trong đó có V-A, emotion, mood_quadrant. Nếu ground truth xây từ các trường này thì đo engine bằng chính input của nó → **không phân biệt được v7.2 vs v8.0**.

**Xử lý:** Mọi GT phải gắn nhãn:
- `external` — editorial playlists từ nguồn ngoài (xếp hạng được)
- `semi-independent` — mood_tags MTG-Jamendo (không trong fusion, nhưng cần check)
- `engine-derived` — V-A/quadrant/emotion (chỉ sanity floor, không xếp hạng)

### 4.2 Mất cân bằng quadrant

Q3 = 62.3% → nếu stratify không đúng, mọi số micro sẽ bị Q3 áp đảo. **Bắt buộc stratified sampling** + báo cáo macro (trung bình per-quadrant) lẫn micro.

### 4.3 mood_tags chất lượng thấp

Sample: `{"corporate": 0.179, "slow": 0.116}` — confidence thấp, tag lặp lại. Phải chạy **discriminativeness check** trước khi tin làm semi-independent GT (xem §7.3).

### 4.4 Framework reproducibility

- `seed=42` cho mọi sampling.
- Catalog đồng nhất: backtest wrap **chính instance `MusicRecommender` đang chạy** (cùng CSV, cùng 5548 hàng).
- Lock numpy/scikit-learn/scipy version trong report.

---

## 5. DECOMMISSION LEGACY BACKTEST

Làm trước tiên. Legacy `tools/backtest.py` (898 dòng) dùng lazy import — xóa không làm chết app lúc startup.

| File/dòng | Hành động |
|---|---|
| `tools/backtest.py` | **Xóa** toàn bộ |
| `api/system.py` L50 `BacktestRequest` | Xóa model |
| `api/system.py` L55 `WeightTestRequest` | Xóa model |
| `api/system.py` L165 `POST /api/backtest/run` | Xóa (wire lại Phase 3) |
| `api/system.py` L214 `POST /api/backtest/test-weights` | Xóa |
| `api/system.py` L249 `GET /api/backtest/dataset-stats` | Giữ, rewire sang `backtest_v2.dataset_stats` |
| Lazy import `from tools.backtest import ...` (L160,169,236,280) | Xóa |

**Salvage ý tưởng** (reimplement sạch, không copy code):
- Similar-song symmetry/consistency → `metrics/property.py`
- Color→emotion alignment test → `metrics/property.py`
- `response_time` tracking → `metrics/operational.py`

---

## 6. KIẾN TRÚC FRAMEWORK

### 6.1 Vòng lặp tổng thể

```
┌─────────────────────────────────────────────────────────┐
│  MEASURE (v7.2 baseline)                                │
│  → Group A: ILD, Coverage, Gini, Coherence, Calibration │
│  → Group B: NDCG/P/R vs editorial (Phase 2+)            │
└───────────────┬─────────────────────────────────────────┘
                │ Kết quả: số baseline + điểm yếu
                ▼
┌─────────────────────────────────────────────────────────┐
│  IDENTIFY WEAK SPOTS                                     │
│  → Ablation: drop từng signal → delta NDCG/ILD          │
│  → Signal yếu nhất → pillar upgrade đó trước            │
└───────────────┬─────────────────────────────────────────┘
                │ Quyết định: tune weights trước, pillar sau
                ▼
┌─────────────────────────────────────────────────────────┐
│  IMPROVE                                                 │
│  → Bước 1: Weight optimization (nhanh, không code nhiều)│
│  → Bước 2: Pillar upgrade (theo thứ tự ablation)        │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  RE-MEASURE                                              │
│  → Chạy lại full backtest                               │
│  → Paired bootstrap: delta vs LOCKED v7.2               │
│  → CI không chứa 0 → kết luận có ý nghĩa                │
└───────────────┬─────────────────────────────────────────┘
                │ Nếu đủ tốt → Final Report
                │ Nếu chưa → quay lại IDENTIFY
                ▼
        FINAL REPORT (§14)
```

### 6.2 Storage layout

```
var/runtime/backtest/
├── ground_truth/
│   ├── editorial_playlists_v1.json   # PRIMARY — external
│   ├── mood_tags_weak_v1.json        # SECONDARY — semi-independent (sau check)
│   ├── va_sanity_v1.json             # SANITY-ONLY — engine-derived
│   └── manifest.json                 # version + checksum + nhãn validity
├── test_sets/
│   └── test_set_v1.json              # 500 queries, stratified seed=42
├── baselines/
│   └── brightify_v7.2.json           # LOCKED — reference cho gating
├── reports/
│   ├── iter_0_baseline/              # đo trạng thái gốc
│   ├── iter_1_weight_opt/            # sau weight optimization
│   ├── iter_2_pillar_<X>/            # sau mỗi pillar upgrade
│   └── final/                        # báo cáo tổng kết
└── weight_search/
    ├── grid_results.csv
    └── optimal_weights.yaml          # weights tốt nhất tìm được
```

### 6.3 Module structure

```
tools/backtest_v2/
├── __init__.py
├── core.py            # BacktestConfig, BacktestRunner, BacktestReport
├── catalog.py         # wrap MusicRecommender, index mapping
├── metrics/
│   ├── property.py    # Group A: ILD(4), Coverage, Gini, Coherence(3), Calibration, symmetry, serendipity_proxy
│   ├── operational.py # Group A+: Latency p50/p95/p99
│   └── accuracy.py    # Group B: NDCG, P, R, MAP, MRR, Hit@K
├── ground_truth/
│   ├── editorial.py   # crawl + fuzzy-match VN playlists
│   ├── mood_tags_weak.py
│   └── va_sanity.py   # sanity floor (tagged engine-derived)
├── improve/
│   ├── weight_opt.py  # scipy.optimize, grid search, constraint: ILD không giảm
│   └── ablation.py    # drop-one-signal, compute delta, rank signals by importance
├── baselines/
│   ├── random_b.py  audio_only.py  lyrics_only.py  va_only.py
│   └── brightify.py   # wrap full engine (inject weights)
├── stats.py           # stratified sampler, paired bootstrap, CI
├── reporters/
│   ├── markdown.py
│   └── json_export.py
└── cli.py             # python -m tools.backtest_v2 ...
```

### 6.4 CLI

```bash
# Đo baseline
python -m tools.backtest_v2 run --config configs/backtest_v0.yaml

# Đo với external GT
python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1

# Ablation (sau khi refactor weights→config)
python -m tools.backtest_v2 ablation --signals timbral,rhythmic,tonal,lyrics,va,emotion,mood

# Weight optimization
python -m tools.backtest_v2 optimize-weights --ground-truth editorial_playlists_v1 \
    --method recommend_by_song --constraint "ild_lyrics >= baseline * 0.95"

# So sánh 2 iteration
python -m tools.backtest_v2 compare iter_0_baseline iter_1_weight_opt

# Sinh báo cáo cuối
python -m tools.backtest_v2 final-report --iterations iter_0,iter_1,iter_2
```

---

## 7. GROUND TRUTH STRATEGY

| # | Nguồn | Nhãn validity | Vai trò | Effort |
|---|---|---|---|---|
| 1 | Editorial VN playlists (crawl 50–100) | `external` | **PRIMARY** — xếp hạng version, weight opt | Cao |
| 2 | mood_tags MTG-Jamendo | `semi-independent` | SECONDARY (sau khi qua §7.3) | Thấp |
| 3 | V-A / quadrant / emotion | `engine-derived` | **SANITY-ONLY** — phát hiện hỏng nặng | Rất thấp |

### 7.1 Editorial playlists (PRIMARY, Phase 2)

**Nguồn crawl: YouTube Music qua `ytmusicapi`** — đã có sẵn trong codebase (`tools/collect_data.py`), không cần auth, có `get_playlist(playlistId, limit=None)` và `search(query, filter="playlists")`.

**Protocol crawl:**

```python
# tools/backtest_v2/ground_truth/editorial.py
from ytmusicapi import YTMusic

PLAYLIST_QUERIES = [
    "nhạc buồn tâm trạng", "nhạc chill việt nam", "nhạc tập trung học bài",
    "nhạc tan làm thư giãn", "nhạc đôi lứa couple", "nhạc tết vui",
    "nhạc gym tập thể dục", "nhạc indie việt", "v-pop ballad hay nhất",
    "nhạc acoustic việt nam", "nhạc rap việt", "nhạc trữ tình",
]

def crawl_editorial_playlists(n_queries=50):
    yt = YTMusic()
    playlists = []
    for q in PLAYLIST_QUERIES:
        results = yt.search(q, filter="playlists", limit=5)
        for r in results:
            pl = yt.get_playlist(r["playlistId"], limit=None)
            playlists.append({"intent": q, "tracks": pl["tracks"]})
    return playlists

def fuzzy_match_to_catalog(playlists, catalog_df):
    # normalize diacritics (unicodedata.normalize NFKD)
    # match bằng track_name + artist, threshold cosine ≥ 0.85
    # trả về: {playlist_intent: [catalog_idx, ...]}
    ...
```

**Filter sau crawl:**
- Bỏ playlist < 10 hit trong catalog.
- Bỏ playlist > 70% catalog coverage (quá chung, không discriminative).
- Target: 50–100 playlist sau filter, mỗi playlist ≥ 10 matched tracks.

**Lưu ý:**
- Chỉ lưu `track_name + artist + catalog_idx mapping` — không lưu audio (ToS).
- `ytmusicapi` không cần auth để search/get public playlists.
- Rate limit nhẹ: thêm `time.sleep(0.1)` giữa request (pattern từ `collect_data.py:YTMUSIC_DELAY`).

### 7.2 KHÔNG dùng quadrant-membership làm relevance

Tautology (engine dùng quadrant làm input) + mất cân bằng (Q3=62.3% → precision giả cao). Quadrant chỉ dùng **stratify sampling** và **báo cáo per-segment**.

### 7.3 mood_tags discriminativeness check (gate cho nguồn #2)

Chạy trước khi tin:
```
- Entropy phân bố top-tag toàn catalog: nếu >80% bài có cùng 1–2 tag → loại.
- Số distinct top-tag: nếu <5 distinct → loại.
- Correlation mood_tags ↔ V-A của engine: nếu r > 0.7 → hạ xuống engine-derived.
```
Chỉ promote lên `semi-independent` nếu qua đủ 3 điều kiện.

---

## 8. BỘ METRIC

### Group A — Property metrics (không cần ground truth) → v0

| Metric | Không gian / công thức | Ghi chú |
|---|---|---|
| **ILD_lyrics** | mean pairwise cosine dist, PhoBERT 768 | ✅ |
| **ILD_audio** | Essentia audio_matrix (~timbral+rhythmic+tonal) | ✅ |
| **ILD_va** | V-A 2-dim Euclidean | ✅ |
| **ILD_color** | CIE Lab 3-dim từ `color_hex`, CIEDE2000 | ✅ |
| **Coverage** | `|unique recs| / 5548` | ✅ |
| **Artist Gini** | Gini coefficient phơi bày artist | ✅ |
| **MoodCoherence** | `1 − mean pairwise V-A dist / √2` | Brightify-specific |
| **TempoCoherence** | `1 − CV(BPM)` trong top-K | ✅ |
| **ColorCoherence** | CIEDE2000 mean pairwise trong top-K | Brightify-specific |
| **Calibration error** | `KL(p_seed_emotion ‖ q_recs_emotion)` trên 13 lớp, α=0.01 | Steck 2018 |
| **Similar-song symmetry** | B∈rec(A) ⇒ A∈rec(B)? (Jaccard overlap) | Offline consistency |
| **Content-serendipity proxy** | `mean(1 − sim(rec_i, seed))` | Thay serendipity user-based |

**Calibration — lý do thêm:** MoodCoherence đo recs chụm quanh V-A trung bình của seed; Calibration đo phân bố 13 emotion trong recs có khớp phân bố 13 emotion của seed hay không. Hai metric bổ sung nhau: MoodCoherence bắt trường hợp drift V-A, Calibration bắt trường hợp mất đa dạng emotion.

### Group A+ — Operational (đo được ngay)

| Metric | Đo gì |
|---|---|
| **Latency p50/p95/p99** | ms per method, N=200 lần lặp, seed cố định |
| **Throughput** (tùy chọn) | query/s khi concurrent |

### Group B — Accuracy (cần external/semi GT) → Phase 2+

| Metric | Công thức |
|---|---|
| **NDCG@K** | graded gain, `(2^rel − 1)/log2(i+2)` — **Primary ranking metric** |
| Precision@K | `|pred[:k] ∩ rel| / k` |
| Recall@K | `|pred[:k] ∩ rel| / |rel|` |
| MAP@K | mean average precision |
| MRR | `1 / rank(first hit)` |
| Hit@K | binary |

K = {5, 10, 20}. **NDCG@10 là số chính** cho mọi so sánh version.

### Nhãn validity bắt buộc trong report JSON

```json
{
  "ndcg_at_10": {
    "value": 0.61, "ci95": [0.58, 0.64],
    "ground_truth": "editorial_playlists_v1",
    "validity": "external",
    "support_by_quadrant": {"Q1": 84, "Q2": 14, "Q3": 3459, "Q4": 1991}
  },
  "ild_lyrics": {
    "value": 0.42, "ci95": [0.40, 0.44],
    "ground_truth": null,
    "validity": "property"
  }
}
```

---

## 9. BASELINE SYSTEMS

| Baseline | Trạng thái | Vai trò |
|---|---|---|
| Random | ✅ | Sàn dưới tuyệt đối |
| Audio-only (Essentia cosine) | ✅ | Ablate về 1 signal |
| Lyrics-only (PhoBERT cosine) | ✅ | Ablate về 1 signal |
| V-A only | ✅ | Ablate về 1 signal |
| **Brightify v7.2 (full engine)** | ✅ **LOCKED** | Reference gating — không thay đổi |
| mood_tags-NN | ⚠️ optional | Chỉ khi mood_tags qua §7.3 |
| ~~Popularity baseline~~ | ❌ BỎ | popularity=0 |

---

## 10. SCENARIOS — MAP 1:1 VỚI 6 METHOD

| # | Method | Weights nguồn | Metric chính | Ground truth phù hợp |
|---|---|---|---|---|
| 1 | `recommend_by_colors` | `config.WEIGHTS_COLOR_QUERY_WITH_LYRICS` | ColorCoherence, MoodCoherence | color→emotion editorial |
| 2 | `recommend_by_song` | **HARDCODE** → cần refactor→`config.RECO_SONG_WEIGHTS` | NDCG@10 (ext), ILD, symmetry | editorial "similar songs" |
| 3 | `recommend_by_mood` | `config.WEIGHTS_MOOD_QUERY` | Precision@10 (ext), MoodCoherence | editorial mood playlists |
| 4 | `recommend_by_image` | `config.WEIGHTS_IMAGE_QUERY_WITH_LYRICS` | MoodCoherence, Calibration | annotated image→mood |
| 5 | `recommend_by_lyrics_keywords` | `config.WEIGHTS_LYRICS_QUERY` | Recall@50, MAP@10 | lyrics + emotion editorial |
| 6 | `generate_emotion_journey` | n/a (interpolation) | SequentialSmoothness, MoodCoherence/step | synthetic Bézier waypoint |

### 10.1 Prerequisite bắt buộc: refactor weights recommend_by_song

`recommend_by_song` hardcode `[0.12, 0.10, 0.08, 0.28, 0.17, 0.15, 0.10]` tại `core/recommendation_engine.py:522`. Vi phạm rule "config-only". **Phải chuyển vào `config.RECO_SONG_WEIGHTS`** để:
- Ablation có thể inject `weights=0` cho từng signal.
- Weight optimizer có thể search trên không gian weights.
- Đúng rule dự án.

Đây là task Phase 0, làm trước khi chạy bất kỳ ablation nào.

---

## 11. VÒNG LẶP CẢI THIỆN

### 11.1 Weight Optimization (sau khi có external GT)

**Mục tiêu:** Tìm `config.RECO_SONG_WEIGHTS` tốt hơn weights tay hiện tại mà không cần đoán.

**Điều kiện tiên quyết:** Có editorial_playlists_v1 (external GT, Phase 2).

**Protocol:**

```python
# tools/backtest_v2/improve/weight_opt.py
from scipy.optimize import minimize

def optimize_weights(runner, ground_truth, baseline_ild):
    """
    Tối ưu signal weights cho recommend_by_song.
    Objective: maximize NDCG@10 (external).
    Constraint: ILD_lyrics >= baseline_ild * 0.95 (không collapse diversity).
    """
    def objective(w):
        w_norm = w / w.sum()
        report = runner.run(override_weights={"recommend_by_song": w_norm})
        return -report.metrics["ndcg_at_10"]["value"]

    constraints = [
        {"type": "ineq", "fun": lambda w: run_ild(w) - baseline_ild * 0.95},
        {"type": "eq",   "fun": lambda w: w.sum() - 1.0},
    ]
    bounds = [(0.0, 0.5)] * 7  # không signal nào vượt 50%

    result = minimize(
        objective,
        x0=config.RECO_SONG_WEIGHTS,  # khởi đầu từ weights hiện tại
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200}
    )
    return result.x
```

**Output:** `weight_search/optimal_weights.yaml` → sau khi verify thủ công → cập nhật `config.RECO_SONG_WEIGHTS`.

**Lưu ý overfitting:** Chia editorial playlists thành 80% optimize / 20% validate. Không bao giờ optimize trên toàn bộ GT.

### 11.2 Ablation → Pillar Priority

**Mục tiêu:** Dùng kết quả ablation để quyết định nâng cấp pillar nào trước, thay vì đoán.

**Protocol:**

```
Với mỗi signal s ∈ {timbral, rhythmic, tonal, lyrics, va, emotion, mood}:
    Chạy backtest với weights[s] = 0, normalize phần còn lại.
    Ghi lại: ΔNDCG@10, ΔILD_lyrics, ΔMoodCoherence.

Signal có |ΔNDCG@10| lớn nhất = signal quan trọng nhất.
Signal đang yếu nhất (abs score thấp) = ứng viên upgrade đầu tiên.
```

**Ví dụ mapping ablation → pillar:**

| Signal yếu / quan trọng | Pillar cần upgrade | Từ PLAN_SYSTEM_UPGRADE |
|---|---|---|
| lyrics (PhoBERT) | Pillar B — ViDeBERTa/ViSoBERT | Thay embedding model |
| timbral/rhythmic/tonal | Pillar A — MERT/CLAP | Thay audio embedding |
| va / emotion | Pillar E — MLP emotion combiner | Cải thiện V-A estimation |
| Diversity thấp | Pillar D — MMR/DPP | Cải thiện diversity post-processing |

**Output:** `reports/ablation/signal_importance.json` + khuyến nghị thứ tự pillar.

### 11.3 Iteration protocol

Mỗi lần cải thiện (weight tune hoặc pillar upgrade):

```
1. Commit code + config mới.
2. Chạy: python -m tools.backtest_v2 run --output iter_N_<tên>
3. Chạy: python -m tools.backtest_v2 compare iter_{N-1} iter_N
4. Kiểm tra:
   - NDCG@10 (ext): CI không chứa 0 và dương → cải thiện thật
   - ILD_lyrics: không giảm > 5% so với iter_0 (không collapse diversity)
   - Latency p95: không tăng > 30%
5. Nếu pass → giữ, tiếp tục iteration tiếp.
   Nếu fail → revert config/code, ghi lý do vào report.
```

---

## 12. STATISTICAL METHODOLOGY

### 12.1 Sampling

- Stratified theo `mood_quadrant`, seed=42, ~500 queries.
- Báo cáo `N` per quadrant. **Q2 (n=14): exempt pass/fail**.

### 12.2 So sánh A vs B

- **Paired bootstrap** (10,000 resample) trên per-query metric → 95% CI cho delta.
- Kết luận "B tốt hơn A" khi **CI của delta không chứa 0** trên `external`/`semi-independent`.

### 12.3 Macro vs Micro

- **Macro**: trung bình trên 4 quadrant (chống Q3 áp đảo).
- **Micro**: trung bình toàn query.
- Nếu macro ↔ micro khác lớn → dấu hiệu bias theo quadrant, cần investigate.

---

## 13. IMPLEMENTATION ROADMAP

### Phase 0 — Prerequisites (làm trước mọi thứ)

- [ ] **Decommission legacy** (§5): xóa `tools/backtest.py`, gỡ 2 model + 3 route trong `api/system.py`.
- [ ] **Refactor weights → config** (§10.1): `recommend_by_song` hardcode → `config.RECO_SONG_WEIGHTS`.
- [ ] **mood_tags discriminativeness check** (§7.3): quyết định dùng được không.
- [ ] Skeleton `tools/backtest_v2/` + `BacktestConfig` + `BacktestRunner` rỗng + CLI.
- [ ] **Pin scipy explicit** trong `requirements-app.txt` (`scipy>=1.11`). Hiện scipy 1.17.1 đã cài transitively qua scikit-learn, nhưng `improve/weight_opt.py` import trực tiếp `scipy.optimize` → phải khai báo explicit để không vỡ khi scikit-learn đổi dependency.

**Output Phase 0:** Code sạch, không legacy, weights có thể inject, dependency rõ ràng.

---

### Phase 1 — Đo baseline v7.2 (Group A, không cần GT)

- [ ] `catalog.py`: wrap `MusicRecommender`, map `original_index`.
- [ ] `stats.py`: stratified sampler + paired bootstrap + CI.
- [ ] `metrics/property.py`: ILD(4), Coverage, Artist Gini, MoodCoherence, TempoCoherence, ColorCoherence, Calibration, symmetry, serendipity_proxy.
- [ ] `metrics/operational.py`: Latency p50/p95/p99 per method.
- [ ] Baselines: random, audio_only, lyrics_only, va_only, brightify_v7.2 (locked).
- [ ] `reporters/`: markdown + JSON với nhãn validity.
- [ ] Chạy → lưu vào `reports/iter_0_baseline/`.

**Output Phase 1:** Số baseline đầy đủ cho 5 system × 11 property metric. Có thể gate PR ngay ("ILD không được giảm, MoodCoherence không được giảm").

---

### Phase 2 — Ground truth ngoài (mở khóa Group B)

- [ ] `ground_truth/editorial.py`: crawl 50–100 VN playlist + fuzzy-match.
- [ ] `metrics/accuracy.py`: NDCG/P/R/MAP/MRR/Hit.
- [ ] Chạy accuracy trên external GT → `reports/iter_0_baseline/accuracy_ext.json`.
- [ ] (nếu mood_tags pass §7.3) thêm semi-independent source.

**Output Phase 2:** Số NDCG@10 đầu tiên với `external` label. Có thể so sánh version.

---

### Phase 3 — Ablation + identify weak spots

- [ ] `improve/ablation.py`: drop-one-signal, compute delta NDCG + ILD per signal.
- [ ] Chạy ablation đầy đủ → `reports/iter_0_baseline/ablation/signal_importance.json`.
- [ ] Sinh khuyến nghị: "Signal X yếu nhất → upgrade Pillar Y trước".
- [ ] `va_sanity.py`: engine-derived sanity floor (labeled).
- [ ] GitHub Actions: quick backtest (Group A) mỗi PR `core/**`.

**Output Phase 3:** Thứ tự ưu tiên upgrade pillar có căn cứ, không phải đoán.

---

### Phase 4 — Weight optimization (quick win trước pillar)

- [ ] `improve/weight_opt.py`: scipy SLSQP, optimize NDCG@10 (ext), constraint ILD.
- [ ] Split editorial GT: 80% optimize / 20% validate.
- [ ] Chạy optimizer → `weight_search/optimal_weights.yaml`.
- [ ] Review thủ công → update `config.RECO_SONG_WEIGHTS`.
- [ ] Chạy backtest → `reports/iter_1_weight_opt/`.
- [ ] Compare iter_0 vs iter_1 → delta + CI.

**Output Phase 4:** Weights tốt hơn với CI, hoặc "weights hiện tại đã gần optimal, không cần đổi nhiều".

---

### Phase 5 — Pillar upgrades (theo thứ tự ablation)

Mỗi pillar = 1 iteration. Ví dụ nếu ablation cho "lyrics yếu nhất":

- [ ] Implement Pillar B (ViDeBERTa/ViSoBERT routing).
- [ ] Chạy backtest → `reports/iter_2_pillar_B/`.
- [ ] Compare iter_1 vs iter_2 → delta.
- [ ] Nếu pass gate → giữ. Nếu fail → revert, ghi lý do.

Lặp lại cho từng pillar theo thứ tự ablation đã chỉ ra.

---

### Phase 6 — Final Report

- [ ] `python -m tools.backtest_v2 final-report --iterations iter_0,iter_1,iter_2,...`
- [ ] Wire lại `/api/backtest/*` vào framework mới.
- [ ] Sinh báo cáo tổng kết theo template §14.

---

## 14. FINAL REPORT TEMPLATE

Đây là cấu trúc báo cáo cuối sau khi hoàn thành toàn bộ vòng lặp.

---

### `reports/final/REPORT.md`

```markdown
# Brightify Recommendation Engine — Evaluation & Improvement Report
**Ngày:** {date}
**Catalog:** 5,548 songs
**Engine baseline:** v7.2 | **Engine sau cải thiện:** v{X.Y}
**Ground truth primary:** editorial_playlists_v1 ({N} playlists, {M} matched songs)

---

## 1. TÓM TẮT (Executive Summary)

| Metric | v7.2 baseline | v{X.Y} cuối | Delta | Ý nghĩa |
|---|---|---|---|---|
| NDCG@10 ✅ (ext) | 0.XX | 0.YY | +Z% (p<0.05) | Khớp editorial playlists tốt hơn |
| ILD_lyrics | 0.XX | 0.YY | ±Z% | Diversity nhạc tương tự |
| MoodCoherence | 0.XX | 0.YY | ±Z% | Độ nhất quán mood |
| Latency p95 | XX ms | YY ms | ±Z% | Tốc độ phản hồi |
| Coverage | X% | Y% | ±Z% | Phơi bày catalog |

**Kết luận 1 câu:** [ví dụ: "Sau weight optimization và nâng cấp Pillar B, NDCG@10 tăng 12% với CI [+8%, +16%], diversity giữ nguyên."]

---

## 2. PHƯƠNG PHÁP ĐÁNH GIÁ

### 2.1 Metric được chọn và lý do

**Hệ thống không có user** → không dùng click-through, dwell time, CF metrics.
Chỉ dùng:
- **Property metrics** (Group A): đo tính chất output, không cần ground truth.
- **Accuracy metrics** (Group B): đo với editorial playlists người thật tạo.

**Metric bị loại và lý do:**

| Metric | Lý do loại |
|---|---|
| Novelty/EFD | popularity=0 toàn catalog |
| GenreCoherence | genres=0 toàn catalog |
| Serendipity user-based | Không có interaction history |
| NDCG với V-A/quadrant làm GT | Tautology — engine dùng V-A làm input |
| Temporal split | release_year rỗng |

### 2.2 Ground truth và nhãn validity

| Nguồn | Nhãn | Dùng cho |
|---|---|---|
| Editorial VN playlists ({N} playlists) | `external ✅` | Xếp hạng version, weight optimization |
| mood_tags MTG-Jamendo | `semi-independent ⚠️` / loại (tuỳ kết quả check §7.3) | SECONDARY hoặc không dùng |
| V-A/quadrant | `engine-derived 🚫` | Sanity floor only |

### 2.3 Test set

- 500 queries, stratified theo mood_quadrant, seed=42.
- Split: 80% cho optimization, 20% hold-out validation.
- Q2 (n=14) exempt khỏi pass/fail per-quadrant.

---

## 3. TRẠNG THÁI BASELINE (v7.2)

### 3.1 Property metrics

| Metric | Random | Audio-only | Lyrics-only | V-A only | Brightify v7.2 |
|---|---|---|---|---|---|
| ILD_lyrics | X.XX | X.XX | X.XX | X.XX | **X.XX** |
| ILD_audio | ... | | | | |
| MoodCoherence | ... | | | | |
| TempoCoherence | ... | | | | |
| ColorCoherence | ... | | | | |
| Calibration err | ... | | | | |
| Coverage | ... | | | | |
| Artist Gini | ... | | | | |
| Symmetry (Jaccard) | ... | | | | |
| Serendipity proxy | ... | | | | |

### 3.2 Accuracy metrics (external GT)

| Metric | Random | Lyrics-only | Brightify v7.2 |
|---|---|---|---|
| NDCG@5 ✅ | X.XX | X.XX | **X.XX** |
| NDCG@10 ✅ | ... | | |
| NDCG@20 ✅ | ... | | |
| Precision@10 | ... | | |
| Recall@10 | ... | | |
| MRR | ... | | |

### 3.3 Per-quadrant (Brightify v7.2)

| Quadrant | N | NDCG@10 | MoodCoherence | 95% CI NDCG |
|---|---|---|---|---|
| Q1 Happy | 84 | X.XX | X.XX | [X, X] |
| Q3 Sad | 3459 | X.XX | X.XX | [X, X] |
| Q4 Calm | 1991 | X.XX | X.XX | [X, X] |
| Q2 (n=14) | 14 | — | — | EXEMPT |

### 3.4 Latency baseline

| Method | p50 | p95 | p99 |
|---|---|---|---|
| recommend_by_song | XX ms | XX ms | XX ms |
| recommend_by_mood | ... | | |
| recommend_by_colors | ... | | |
| recommend_by_image | ... | | |
| recommend_by_lyrics_keywords | ... | | |
| generate_emotion_journey | ... | | |

---

## 4. ABLATION — TÌM ĐIỂM YẾU

### 4.1 Tầm quan trọng từng signal (recommend_by_song)

| Signal bị drop | ΔNDCG@10 | ΔILD_lyrics | ΔMoodCoherence | Kết luận |
|---|---|---|---|---|
| lyrics | −X.XX | +X.XX | −X.XX | Signal quan trọng nhất |
| va | −X.XX | ... | | |
| emotion | ... | | | |
| timbral | ... | | | |
| rhythmic | ... | | | |
| tonal | ... | | | |
| mood | ... | | | |

### 4.2 Thứ tự upgrade pillar theo ablation

1. Pillar {X} — {tên} (signal yếu nhất: {signal}, ΔNDCG = −X.XX)
2. Pillar {Y} — ...
3. ...

**Lý do:** [giải thích ngắn tại sao thứ tự này]

---

## 5. CẢI THIỆN — TỪNG ITERATION

### Iteration 1: Weight Optimization

**Vấn đề phát hiện:** [ví dụ: "Lyrics weight hiện tại 0.28 quá thấp; ablation cho thấy nó chiếm 35% tầm quan trọng."]
**Hành động:** Chạy scipy SLSQP optimize NDCG@10 (ext), constraint ILD ≥ 95% baseline.
**Weights mới:** `[X.XX, X.XX, X.XX, X.XX, X.XX, X.XX, X.XX]` (tổng = 1.0)
**Kết quả:**

| Metric | iter_0 | iter_1 | Delta | CI 95% | Kết luận |
|---|---|---|---|---|---|
| NDCG@10 ✅ | X.XX | X.XX | +X.XX | [+a, +b] | ✅ Cải thiện |
| ILD_lyrics | X.XX | X.XX | ±X.XX | [a, b] | ✅ Giữ được |
| Latency p95 | XX ms | XX ms | ±X% | — | ✅ OK |

**Lý do cải thiện:** [ví dụ: "Tăng lyrics weight từ 0.28→0.35 khớp với tầm quan trọng thật trong ablation."]

---

### Iteration 2: Pillar {X} Upgrade

**Vấn đề phát hiện:** [ví dụ: "PhoBERT lyrics embedding chưa tốt cho nhạc Việt; cosine similarity thấp với bài có lyrics tương nghĩa."]
**Hành động:** [ví dụ: "Thay PhoBERT → ViDeBERTa-base, re-extract embedding 5548 bài."]
**Kết quả:**

| Metric | iter_1 | iter_2 | Delta | CI 95% | Kết luận |
|---|---|---|---|---|---|
| NDCG@10 ✅ | X.XX | X.XX | +X.XX | [a, b] | ✅ / ❌ |
| ILD_lyrics | ... | | | | |
| Latency p95 | ... | | | | |

**Lý do cải thiện / không cải thiện:** [giải thích cụ thể]

*[Lặp lại cho mỗi iteration]*

---

## 6. TỔNG KẾT SO SÁNH (v7.2 → v{X.Y})

| Metric | v7.2 | v{X.Y} | Delta tổng | Significant? |
|---|---|---|---|---|
| NDCG@10 ✅ | X.XX | X.XX | +X.XX | p<0.05 ✅ |
| ILD_lyrics | ... | | | |
| MoodCoherence | ... | | | |
| Latency p95 | ... | | | |

**Kết luận tổng:** [2–3 câu tóm tắt những gì đã cải thiện, cải thiện nhiều nhất nhờ cái gì, và những gì không cải thiện được + lý do.]

---

## 7. HẠN CHẾ & ĐIỀU KHÔNG ĐO ĐƯỢC

| Hạn chế | Tác động | Cần làm để giải quyết |
|---|---|---|
| Không có user → không có implicit feedback | Không biết người dùng thật có hài lòng không | Thu thập play history khi có user |
| popularity=0 → không đo được novelty | Không biết engine có thiên vị bài nổi tiếng không | Backfill youtube_view_count |
| genres=0 → không đo GenreCoherence | Không biết recs có đồng thể loại không | Backfill genres |
| Editorial playlists: {N} playlists, {M} matched tracks | Coverage thấp → precision/recall bị ảnh hưởng | Thêm playlist, backfill thiếu |
| Q2 chỉ 14 bài | Không đánh giá được high-energy segment | Thu thập thêm nhạc Q2 |
| Offline ↔ Online gap | Số offline có thể không predict user satisfaction | A/B test khi có user |

---

## 8. KHUYẾN NGHỊ TIẾP THEO

1. **Backfill data** (ưu tiên): youtube_view_count (mở novelty), genres (mở genre metrics).
2. **Tiếp tục iteration pillar** theo thứ tự ablation đã xác định.
3. **Khi có user**: thêm implicit feedback (play ratio, skip rate) → upgrade sang hybrid metric.
4. **Editorial playlist**: mở rộng lên 200+ playlist để tăng coverage GT.
```

---

## 15. BACKLOG — DATA BLOCKED

Các hạng mục dưới đây **không thể làm** do data không tồn tại. Không implement để tránh tạo số giả.

| Hạng mục | Bị chặn bởi | Cần làm để mở khóa |
|---|---|---|
| Novelty (EFD, AvgPopRank), Popularity baseline | `popularity=0` toàn bộ | Thêm `youtube_view_count` migration + re-crawl |
| GenreCoherence, per-genre segment | `genres=0` | Backfill genres từ metadata / auto-classifier |
| Temporal split | `release_year` rỗng | Backfill release_date trong pipeline |
| Serendipity user-based, CF baselines | Không có interaction history | Thu thập play events (cần feature user auth) |
| Hand-annotated VN mood gold | Budget annotation | ~$500–1000, 500 bài × 5 annotator |
| User study qualitative | Recruit | 30–50 listener VN |

---

## 16. TÀI LIỆU THAM KHẢO

- McNee, Riedl, Konstan 2006 — "Being Accurate is Not Enough" — CHI 2006.
- Garcin et al. 2014 — Offline/Online eval gap — RecSys 2014.
- Steck 2018 — "Calibrated Recommendations" — RecSys 2018.
- Kaminskas & Bridge 2016 — Diversity/Serendipity/Novelty/Coverage — ACM TiiS.
- Critical Reexamination ILD 2023 — arXiv 2305.13801.
- itemKNN deviation 2024 — arXiv 2407.13531 (lock framework version).

**Internal:**
- `docs/PLAN_SYSTEM_UPGRADE.md` — 7 pillar upgrade (Pillar A–G), roadmap 6 tháng.
- `docs/PLAN_DOCKERIZATION.md §7` — data layout, artifact tiers.
- `core/recommendation_engine.py` — 6 method + 7-signal fusion.
- ~~`tools/backtest.py`~~ — **đã xóa (Phase 0)**.

---

**Hết Plan 2 (v3 — 2026-05-27). Vòng lặp: Measure → Identify → Tune → Re-measure → Report.**
