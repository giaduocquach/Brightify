# PLAN 2 — BACKTEST FRAMEWORK & METRICS ĐÁNH GIÁ

**Ngày tạo:** 2026-05-26
**Phạm vi:** Xây dựng framework backtest offline + metrics đánh giá toàn diện cho recommendation engine của Brightify. Mục tiêu: đo lường có khoa học mọi thay đổi trong [PLAN_SYSTEM_UPGRADE.md].

> **Trạng thái hiện tại:** Đã có endpoint admin `/api/backtest/run`, `/api/backtest/test-weights`, `/api/backtest/dataset-stats` nhưng **chưa có metrics implementation cụ thể**, không có ground truth, không có baseline comparison framework.

---

## MỤC LỤC

1. [Mục tiêu & nguyên tắc](#1-mục-tiêu--nguyên-tắc)
2. [Lý thuyết & lựa chọn metric](#2-lý-thuyết--lựa-chọn-metric)
3. [Kiến trúc backtest framework](#3-kiến-trúc-backtest-framework)
4. [Ground truth & test set construction](#4-ground-truth--test-set-construction)
5. [Bộ metric đầy đủ](#5-bộ-metric-đầy-đủ)
6. [Baseline systems](#6-baseline-systems)
7. [Backtest scenarios](#7-backtest-scenarios)
8. [Implementation roadmap](#8-implementation-roadmap)
9. [Reporting & dashboard](#9-reporting--dashboard)
10. [User study (qualitative)](#10-user-study-qualitative)
11. [Continuous evaluation (CI gate)](#11-continuous-evaluation-ci-gate)
12. [Tài liệu tham khảo](#12-tài-liệu-tham-khảo)

---

## 1. MỤC TIÊU & NGUYÊN TẮC

### 1.1 Mục tiêu

1. **Đo lường khách quan** mọi thay đổi engine (gating mọi PR upgrade).
2. **So sánh** với baselines (popularity, content-only, alternatives).
3. **Beyond-accuracy** — không chỉ NDCG/MAP mà còn diversity, novelty, mood-coherence, fairness.
4. **Reproducible** — bộ test, seed, framework version đều fixed.
5. **CI-integrated** — pipeline tự động chạy mỗi PR.

### 1.2 Nguyên tắc

1. **No accuracy-only** — McNee 2006 critique: "being accurate is not enough".
2. **No offline-online overclaim** — Garcin 2014 cảnh báo correlation offline/online yếu. Mọi kết luận "v8 tốt hơn v7" phải pair offline + user study.
3. **Temporal correctness** — không train trên future, không test trên past (Time-to-Split, RecSys 2025).
4. **Reproducibility** — seed mọi sampling, version-lock libraries.
5. **Per-segment analysis** — báo cáo per-quadrant Q1-Q4, per-genre, per-popularity-bucket.

---

## 2. LÝ THUYẾT & LỰA CHỌN METRIC

### 2.1 Bài học từ literature

| Source | Key takeaway |
|---|---|
| **McNee, Riedl, Konstan (CHI 2006)** | Accuracy CAN HURT recsys. Must measure beyond. |
| **Garcin et al. (RecSys 2014)** | Offline-online correlation weak. Validate online. |
| **Castells (AI Magazine 2022)** | Offline evaluation challenges: bias, sparsity. |
| **Time-to-Split (RecSys 2025)** | Leave-one-out có temporal leakage. Dùng global timeline split. |
| **Critical Reexamination ILD (2023)** | ILD bị bias bởi distance metric. Phải report multiple distance functions. |
| **itemKNN deviation (arXiv 2407.13531)** | Cùng algo, khác framework → khác kết quả. Phải lock framework version. |
| **Kaminskas & Bridge (TiiS 2016)** | Diversity, novelty, serendipity, coverage = beyond-accuracy core. |
| **Vargas & Castells 2011** | EFD (Expected Free Discovery), rank-aware novelty. |

### 2.2 Đặc thù Brightify ảnh hưởng metric chọn

| Đặc thù | Implication |
|---|---|
| **Content-based, no user accounts** | Cannot use classic user-CF metrics. Phải dùng synthetic users / item-item / session-based. |
| **Multimodal (audio + lyrics + color + image)** | Cần per-modality ablation. ILD trên nhiều spaces. |
| **Vietnamese-specific** | Mood labels phải validated bởi annotators Việt. |
| **Mood quadrant explicit** | Direct MoodCoherence — unique advantage. |
| **Catalog ~4,300 songs** | Small enough for full evaluation; lớn enough cho statistical significance. |

---

## 3. KIẾN TRÚC BACKTEST FRAMEWORK

### 3.0 Storage layout cho backtest artifacts

> Tham chiếu [PLAN_DOCKERIZATION.md §7](PLAN_DOCKERIZATION.md#7-data-layout--persistence-master-guide). Backtest artifacts đặt trong T2 (`var/runtime/backtest/`) để versionable, backupable, không trộn với code.

```
var/runtime/backtest/
├── ground_truth/                          # T2, weekly snapshot
│   ├── mood_based_v1.json                 # Mood/genre/era-based labels (Phương pháp 1)
│   ├── playlist_editorial_v1.json         # Crawled editorial playlists (Phương pháp 2)
│   ├── synthetic_users_v1.json            # 500 virtual users + sessions (Phương pháp 3)
│   ├── vn_mood_gold_v1.json               # Hand-annotated gold standard (Plan 1 Pillar E)
│   └── manifest.json                      # version info + checksums
│
├── test_sets/                             # T2, versioned
│   ├── backtest_test_set_v1.json          # Combined test set (queries + expected results)
│   └── backtest_test_set_v2.json          # ... (khi có version mới)
│
├── baselines/                             # T2, gold reference
│   ├── popularity_v1.json
│   ├── random_v1.json
│   ├── lyrics_only_v1.json
│   ├── audio_only_v1.json
│   ├── va_only_v1.json
│   ├── brightify_v7.2.json                # LOCKED baseline cho CI gating
│   └── brightify_v8.0.json                # New baseline sau Plan 1 (per pillar)
│
├── reports/                               # T2, archival, off-site backup
│   └── 2026-05-26_full/                   # Per-run timestamped folder
│       ├── config.yaml                    # Run config snapshot
│       ├── report.md                      # Human-readable
│       ├── report.json                    # Machine-readable (CI gating)
│       ├── dashboard.html                 # Plotly interactive
│       ├── per_segment/                   # Per-quadrant, per-genre breakdowns
│       │   ├── by_quadrant.json
│       │   ├── by_genre.json
│       │   └── by_popularity.json
│       └── raw_predictions/               # For deep debugging (large)
│           └── brightify_v7.2_predictions.jsonl
│
└── ci_artifacts/                          # T2, short retention (last 30 PRs)
    └── pr_1234/
        ├── report.json
        └── delta_vs_baseline.json         # CI gate output
```

**Path env vars** (từ Plan 3 §7.4):

```bash
BACKTEST_PATH=/opt/brightify/var/runtime/backtest   # prod
BACKTEST_PATH=./var/runtime/backtest                 # dev
```

App đọc qua `BACKTEST_PATH` env var để cùng code chạy được cả dev và prod.

### 3.1 Module structure

```
tools/backtest/
├── __init__.py
├── core.py                  # BacktestRunner main class
├── metrics/
│   ├── __init__.py
│   ├── accuracy.py          # Precision@K, Recall@K, NDCG@K, MAP@K, MRR, Hit@K
│   ├── diversity.py         # ILD, Coverage, Gini
│   ├── novelty.py           # EFD, AvgPopularityRank
│   ├── serendipity.py       # Kaminskas serendipity
│   ├── music_specific.py    # MoodCoherence, TempoCoherence, GenreCoherence
│   └── fairness.py          # ArtistGini, ArtistExposure
├── datasets/
│   ├── __init__.py
│   ├── builder.py           # Test set construction
│   ├── synthetic_users.py   # Virtual user generator
│   └── ground_truth.py      # Ground truth labeling
├── baselines/
│   ├── popularity.py
│   ├── random_baseline.py
│   ├── content_lyrics_only.py
│   ├── content_audio_only.py
│   └── multimodal_full.py   # Brightify engine reference
├── runners/
│   ├── full_evaluation.py
│   ├── ablation.py
│   ├── sensitivity.py       # Weight sweep
│   └── per_segment.py       # Per quadrant/genre/popularity
├── reporters/
│   ├── markdown.py
│   ├── json_export.py
│   └── dashboard_html.py
└── cli.py                   # CLI entry: python -m tools.backtest run
```

### 3.2 Core API

```python
# tools/backtest/core.py

@dataclass
class BacktestConfig:
    catalog_path: Path
    embeddings_path: Path
    test_set_path: Path
    ground_truth_path: Path
    metrics: List[str] = field(default_factory=lambda: ["all"])
    k_values: List[int] = field(default_factory=lambda: [5, 10, 20, 50])
    baselines: List[str] = field(default_factory=lambda: ["popularity", "random", "content_lyrics", "content_audio", "brightify"])
    output_dir: Path = Path("logs/backtest")
    seed: int = 42

class BacktestRunner:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.dataset = TestSet.load(config.test_set_path)
        self.ground_truth = GroundTruth.load(config.ground_truth_path)
        self.systems = {name: build_baseline(name) for name in config.baselines}

    def run(self) -> BacktestReport:
        results = {}
        for system_name, system in self.systems.items():
            predictions = system.predict_all(self.dataset)
            results[system_name] = self._compute_all_metrics(predictions)
        return BacktestReport(results)

    def _compute_all_metrics(self, predictions):
        return {
            "accuracy": compute_accuracy(predictions, self.ground_truth, self.config.k_values),
            "diversity": compute_diversity(predictions, self.dataset.embeddings),
            "novelty": compute_novelty(predictions, self.dataset.popularity),
            "music_specific": compute_music_metrics(predictions, self.dataset.catalog),
            "fairness": compute_fairness(predictions, self.dataset.catalog),
        }
```

### 3.3 CLI

```bash
# Full evaluation
python -m tools.backtest run --config configs/backtest_full.yaml

# Ablation: remove one signal at a time
python -m tools.backtest ablation --signals timbral,rhythmic,tonal,lyrics,va,emotion,mood

# Weight sweep
python -m tools.backtest sensitivity --weight lyrics --range 0.15,0.35,0.05

# Per-segment
python -m tools.backtest segment --by mood_quadrant
python -m tools.backtest segment --by genre
python -m tools.backtest segment --by popularity_bucket
```

---

## 4. GROUND TRUTH & TEST SET CONSTRUCTION

### 4.1 Vấn đề

Brightify không có user history → không có "real" ground truth từ implicit feedback. Phải tạo ground truth synthetic.

### 4.2 Phương pháp 1: Mood/Genre/Era-based ground truth

**Cho mỗi seed song, "relevant items" là:**
- Cùng mood_quadrant (Q1-Q4) ⇒ relevance = 0.5
- Cùng top-3 emotion tags ⇒ relevance += 0.3
- Cùng genre primary ⇒ relevance += 0.2
- Cùng era (5-year window) ⇒ relevance += 0.1
- Cosine V-A distance < 0.2 ⇒ relevance += 0.2

Cap relevance at 1.0. Tracks with relevance ≥ 0.5 → relevant set.

**Pros:** Deterministic, reproducible, scalable.
**Cons:** Tautological — engine training trên cùng features sẽ tự động "đúng".

### 4.3 Phương pháp 2: Editorial playlist labels

**Sử dụng playlists thực tế từ YTMusic/Spotify VN làm ground truth:**

- Crawl 100-200 editorial Vietnamese playlists ("Top Hits V-pop", "Buồn man mác", "Nhạc Tết 2026", ...)
- Mỗi playlist = một "query intent".
- Tracks trong playlist = relevant items.
- Tracks ngoài = irrelevant.

**Workflow:**

```
tools/backtest/datasets/playlist_crawler.py:
  - Crawl playlist với keyword search (mood, theme, genre)
  - Lưu: {playlist_id, name, description, tracks: [track_ids]}
  - Map track_ids → Brightify catalog (fuzzy match name+artist)

Filter:
  - Drop playlists < 10 tracks Brightify catalog hit
  - Drop playlists > 70% catalog coverage (too general)
  - Keep ~100 high-quality playlists
```

**Pros:** External validation; matches real-world Vietnamese taste.
**Cons:** Editorial biased toward popular; ToS compliance.

### 4.4 Phương pháp 3: Synthetic users (BPR-style)

Tạo "virtual users" với taste profile rõ ràng:

```python
# tools/backtest/datasets/synthetic_users.py

@dataclass
class SyntheticUser:
    user_id: str
    favorite_quadrant: str           # Q1-Q4
    favorite_genres: List[str]
    favorite_emotions: List[str]
    preferred_era: Tuple[int, int]   # year range
    diversity_preference: float       # 0=consistent, 1=eclectic

def generate_users(n=500, seed=42) -> List[SyntheticUser]:
    # ...

def simulate_listening_history(user: SyntheticUser, catalog, n_listens=50):
    """Sample songs từ catalog theo preference; weighted random."""
    # ...
```

**Mỗi virtual user → leave-N-out evaluation:** mask N% history, dùng engine predict, đo accuracy.

### 4.5 Phương pháp 4: Hand-annotated VN test set

Như đã đề xuất trong [PLAN_SYSTEM_UPGRADE.md] Pillar E:
- 500 songs × 5 annotators × {valence, arousal, top-3 emotions}.
- Cohen's κ ≥ 0.6 inter-rater agreement.
- Budget ~$500-1000.

Dùng làm **gold standard** cho MoodCoherence, V-A regression accuracy.

### 4.6 Khuyến nghị

**Kết hợp cả 4 phương pháp:**
- Synthetic mood-based: 70% test set (scale + reproducibility).
- Editorial playlists: 20% (external validation).
- Synthetic users: 10% (session simulation).
- Hand-annotated VN: gold standard cho mood-specific metrics.

### 4.7 Temporal split

```python
# Item-temporal split (Brightify không có user interactions)
train_end = "2024-12-31"
test_start = "2025-01-01"

train_songs = catalog[catalog.release_date < train_end]
test_songs = catalog[catalog.release_date >= test_start]

# Train engine artifacts (embeddings, normalization stats) chỉ trên train_songs
# Evaluate trên test_songs
```

Hoặc nếu engine không cần training (pure content-based): random 80/10/10 split với fixed seed.

---

## 5. BỘ METRIC ĐẦY ĐỦ

### 5.1 Accuracy metrics

#### **Precision@K**

```python
def precision_at_k(predicted: List[int], relevant: Set[int], k: int) -> float:
    return len(set(predicted[:k]) & relevant) / k
```

K values: 5, 10, 20, 50.

#### **Recall@K**

```python
def recall_at_k(predicted: List[int], relevant: Set[int], k: int) -> float:
    return len(set(predicted[:k]) & relevant) / len(relevant) if relevant else 0
```

#### **NDCG@K (rank-aware, graded)**

```python
def ndcg_at_k(predicted: List[int], relevance_scores: Dict[int, float], k: int) -> float:
    dcg = sum((2**relevance_scores.get(item, 0) - 1) / np.log2(idx + 2)
              for idx, item in enumerate(predicted[:k]))
    ideal = sorted(relevance_scores.values(), reverse=True)[:k]
    idcg = sum((2**r - 1) / np.log2(idx + 2) for idx, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0
```

**Brightify-specific:** relevance_score = graded (0.0 - 1.0) từ mood/genre/V-A blend.

#### **MAP@K**

```python
def average_precision_at_k(predicted: List[int], relevant: Set[int], k: int) -> float:
    score = 0.0
    hits = 0
    for i, item in enumerate(predicted[:k]):
        if item in relevant:
            hits += 1
            score += hits / (i + 1)
    return score / min(len(relevant), k) if relevant else 0
```

#### **MRR (Mean Reciprocal Rank)**

```python
def reciprocal_rank(predicted: List[int], relevant: Set[int]) -> float:
    for i, item in enumerate(predicted, 1):
        if item in relevant:
            return 1.0 / i
    return 0.0
```

#### **Hit@K**

```python
def hit_at_k(predicted: List[int], relevant: Set[int], k: int) -> int:
    return 1 if (set(predicted[:k]) & relevant) else 0
```

### 5.2 Diversity metrics

#### **Intra-List Diversity (ILD)**

```python
def ild(predicted: List[int], embeddings: np.ndarray, distance="cosine") -> float:
    n = len(predicted)
    if n < 2:
        return 0
    dist_fn = cosine_distance if distance == "cosine" else euclidean_distance
    total = sum(dist_fn(embeddings[predicted[i]], embeddings[predicted[j]])
                for i in range(n) for j in range(i+1, n))
    return total / (n * (n-1) / 2)
```

**Report on multiple embedding spaces:**
- ILD_lyrics (PhoBERT 768-dim)
- ILD_audio (MERT 768-dim after Pillar A) hoặc Essentia features
- ILD_va (Valence-Arousal 2-dim)
- ILD_color (CIE Lab 3-dim)

#### **Coverage (Catalog Coverage)**

```python
def coverage(all_recommendations: List[List[int]], catalog_size: int) -> float:
    unique_items = set()
    for rec in all_recommendations:
        unique_items.update(rec)
    return len(unique_items) / catalog_size
```

#### **Artist Gini**

```python
def artist_gini(all_recommendations: List[List[int]], song_to_artist: Dict[int, str]) -> float:
    artist_counts = Counter()
    for rec in all_recommendations:
        for song in rec:
            artist_counts[song_to_artist[song]] += 1

    counts = sorted(artist_counts.values())
    n = len(counts)
    cumsum = np.cumsum(counts)
    return (2 * np.sum((np.arange(1, n+1)) * counts) - (n+1) * cumsum[-1]) / (n * cumsum[-1])
```

### 5.3 Novelty metrics

#### **Expected Free Discovery (EFD, Vargas & Castells 2011)**

```python
def efd(predicted: List[int], popularity: Dict[int, float], k: int) -> float:
    """Higher = more novel. Use log2(1/p)."""
    return np.mean([-np.log2(popularity.get(item, 1e-9)) for item in predicted[:k]])
```

Popularity = play_count / total_plays. Nếu không có user log: dùng popularity từ Spotify/YouTube external data.

#### **Average Popularity Rank**

```python
def avg_popularity_rank(predicted: List[int], popularity_ranks: Dict[int, int], k: int) -> float:
    """Lower = more novel."""
    return np.mean([popularity_ranks.get(item, len(popularity_ranks)) for item in predicted[:k]])
```

### 5.4 Serendipity (Kaminskas & Bridge 2016)

```python
def serendipity(predicted: List[int],
                relevant: Set[int],
                user_history: Set[int],
                embeddings: np.ndarray,
                k: int) -> float:
    """
    Serendipity = unexpectedness × relevance
    Unexpectedness = 1 - max similarity với user history
    """
    history_emb = embeddings[list(user_history)].mean(axis=0) if user_history else None
    scores = []
    for item in predicted[:k]:
        if history_emb is not None:
            unexp = 1 - cosine_similarity(embeddings[item], history_emb)
        else:
            unexp = 1.0
        rel = 1.0 if item in relevant else 0.0
        scores.append(unexp * rel)
    return np.mean(scores)
```

### 5.5 Music-specific metrics (Brightify unique)

#### **MoodCoherence**

```python
def mood_coherence(predicted: List[int], song_va: np.ndarray, k: int) -> float:
    """1 - mean pairwise V-A distance, normalized to [0, 1]."""
    n = min(k, len(predicted))
    if n < 2:
        return 1.0
    va_subset = song_va[predicted[:n]]
    distances = []
    for i in range(n):
        for j in range(i+1, n):
            distances.append(np.linalg.norm(va_subset[i] - va_subset[j]))
    mean_dist = np.mean(distances)
    max_dist = np.sqrt(2)  # max V-A distance trong [0,1]²
    return 1 - (mean_dist / max_dist)
```

#### **TempoCoherence**

```python
def tempo_coherence(predicted: List[int], tempos: np.ndarray, k: int) -> float:
    """Lower CV = more coherent."""
    bpm = tempos[predicted[:k]]
    cv = np.std(bpm) / np.mean(bpm) if np.mean(bpm) > 0 else 1
    return max(0, 1 - cv)
```

#### **GenreCoherence**

```python
def genre_coherence(predicted: List[int], genres: List[List[str]], k: int) -> float:
    """Entropy-based: 1 - normalized entropy của genre distribution."""
    all_genres = []
    for item in predicted[:k]:
        all_genres.extend(genres[item])
    counts = Counter(all_genres)
    total = sum(counts.values())
    entropy = -sum((c/total) * np.log2(c/total) for c in counts.values() if c > 0)
    max_entropy = np.log2(len(counts)) if len(counts) > 1 else 1
    return 1 - (entropy / max_entropy)
```

#### **SequentialSmoothness (cho playlist)**

```python
def sequential_smoothness(predicted: List[int],
                          va: np.ndarray,
                          tempos: np.ndarray) -> float:
    """Mean adjacent transition distance."""
    transitions = []
    for i in range(len(predicted) - 1):
        va_diff = np.linalg.norm(va[predicted[i]] - va[predicted[i+1]])
        bpm_diff = abs(tempos[predicted[i]] - tempos[predicted[i+1]]) / 200
        transitions.append(0.7 * va_diff + 0.3 * bpm_diff)
    return 1 - np.mean(transitions)
```

#### **ColorCoherence (Brightify unique)**

```python
def color_coherence(predicted: List[int], colors_lab: np.ndarray, k: int) -> float:
    """CIEDE2000 pairwise distance."""
    # ...
```

### 5.6 Fairness metrics

#### **Artist Exposure Equity**

Đã ở 5.2 (Artist Gini).

#### **Long-tail Coverage**

```python
def longtail_coverage(all_recommendations: List[List[int]],
                       popularity_ranks: Dict[int, int],
                       longtail_threshold: int = 100) -> float:
    """% of recommended items in long-tail (rank > threshold)."""
    longtail_items = {i for i, rank in popularity_ranks.items() if rank > longtail_threshold}
    all_recs = [item for rec in all_recommendations for item in rec]
    return sum(1 for item in all_recs if item in longtail_items) / len(all_recs)
```

### 5.7 Tóm tắt bảng metric

| Category | Metric | Formula sigil | Brightify priority |
|---|---|---|---|
| Accuracy | Precision@10 | `\|R∩T\|/10` | Core |
| Accuracy | Recall@50 | `\|R∩T\|/\|R\|` | Core |
| Accuracy | **NDCG@10** | rank-aware graded | **Primary** |
| Accuracy | MAP@10 | mean AP | Core |
| Accuracy | MRR | 1/rank first hit | Aux |
| Accuracy | Hit@10 | binary | Aux |
| Diversity | **ILD@10** (4 spaces) | mean pair dist | **Primary** |
| Diversity | Coverage | `\|unique\|/\|catalog\|` | Core |
| Diversity | Artist Gini | inequality | Core |
| Novelty | EFD | `mean -log2 popularity` | Core |
| Novelty | AvgPopRank | mean rank | Aux |
| Serendipity | Kaminskas | unexp × rel | Aux |
| Music | **MoodCoherence** | 1 - mean V-A dist | **Brightify-unique** |
| Music | TempoCoherence | 1 - CV(BPM) | Core |
| Music | GenreCoherence | 1 - genre entropy | Core |
| Music | **ColorCoherence** | CIEDE2000 mean | **Brightify-unique** |
| Music | SequentialSmoothness | trans dist | Aux (playlist) |
| Fairness | Artist Gini | (cùng diversity) | Core |
| Fairness | LongtailCoverage | % rank > threshold | Aux |

**Primary**: phải report mọi run.
**Core**: report standard runs.
**Aux**: deep-dive runs.

---

## 6. BASELINE SYSTEMS

Để biết Brightify "tốt hơn baseline bao nhiêu":

### 6.1 Random baseline

```python
class RandomBaseline:
    def predict(self, query, top_k=10):
        return np.random.choice(self.catalog_ids, size=top_k, replace=False)
```

### 6.2 Popularity baseline

```python
class PopularityBaseline:
    def predict(self, query, top_k=10):
        # Always returns top-K by popularity (ignore query).
        return self.popularity_sorted[:top_k]
```

### 6.3 Content-only baselines

```python
class LyricsOnlyBaseline:
    """Cosine similarity on PhoBERT embedding only."""
    def predict(self, query, top_k=10):
        emb = self.encode(query.text)
        sims = cosine_similarity(self.embeddings, emb)
        return np.argsort(-sims)[:top_k]

class AudioOnlyBaseline:
    """Cosine similarity on audio feature vector only."""
    # ...
```

### 6.4 V-A only baseline

```python
class VABaseline:
    """Nearest neighbors trong V-A space."""
    # ...
```

### 6.5 Brightify v7.2 (current)

```python
class BrightifyV72:
    """Full 7-signal fusion (production engine)."""
    # Wrap core.recommendation_engine.MusicRecommender
```

### 6.6 Brightify v8.0 (target)

```python
class BrightifyV80:
    """Upgraded engine with MERT + RRF + MMR (after PLAN_SYSTEM_UPGRADE)."""
    # ...
```

### 6.7 External baselines (optional)

**RecBole standardized models:**
- BPR (collaborative filtering pure, requires synthetic users)
- ItemKNN (content-based using audio features)
- LightGCN (graph-based, synthetic interactions)

**Cornac multimodal models:**
- VBPR (Visual BPR)
- AMR (Adversarial Multimedia Recsys)
- ConvMF (Convolutional Matrix Factorization)

---

## 7. BACKTEST SCENARIOS

### 7.1 Scenario 1: Cold-start (item-level)

**Query:** seed song mới release < 30 ngày.
**Ground truth:** mood/genre/era-based.
**Metric:** NDCG@10, Coverage.
**Pass:** NDCG@10 ≥ 0.4, Coverage ≥ 70%.

### 7.2 Scenario 2: Mood-based query

**Query:** mood keyword ("buồn", "happy", "chill").
**Ground truth:** editorial playlists tagged với mood đó.
**Metric:** Precision@10, MoodCoherence.
**Pass:** Precision@10 ≥ 0.7, MoodCoherence ≥ 0.85.

### 7.3 Scenario 3: Color query

**Query:** hex color list.
**Ground truth:** songs có color_hex predicted gần (CIEDE2000 < 20).
**Metric:** Precision@10, ColorCoherence.
**Pass:** Precision@10 ≥ 0.6, ColorCoherence ≥ 0.80.

### 7.4 Scenario 4: Lyrics search (semantic)

**Query:** Vietnamese keyword phrase ("yêu thương buồn", "nhớ nhung").
**Ground truth:** songs có lyrics chứa keywords + cùng emotion.
**Metric:** Recall@50, MAP@10.
**Pass:** Recall@50 ≥ 0.7, MAP@10 ≥ 0.5.

### 7.5 Scenario 5: Song-to-song similar

**Query:** seed track_id.
**Ground truth:** editorial "similar songs" hoặc same-mood-quadrant + same-genre.
**Metric:** NDCG@10, ArtistGini (avoid same-artist bias).
**Pass:** NDCG@10 ≥ 0.5, ArtistGini ≤ 0.4.

### 7.6 Scenario 6: Image query

**Query:** sample images (sunset, party, nature, ...).
**Ground truth:** annotated mood mapping (e.g., sunset → calm/romantic Q4).
**Metric:** Precision@10, MoodCoherence.

### 7.7 Scenario 7: Emotion journey

**Query:** start V-A → end V-A.
**Ground truth:** synthetic Bézier waypoint với mood gradient.
**Metric:** SequentialSmoothness, MoodCoherence per-step.
**Pass:** SequentialSmoothness ≥ 0.7, no step jump > 0.3 V-A.

### 7.8 Scenario 8: Diversity stress test

**Query:** 100 random seed songs, top-10 each.
**Metric:** Coverage, Artist Gini, LongtailCoverage.
**Pass:** Coverage ≥ 60%, Artist Gini ≤ 0.4.

### 7.9 Scenario 9: Per-quadrant balance

Split test set by mood_quadrant (Q1/Q2/Q3/Q4). Run all metrics per quadrant.
**Pass:** Performance không lệch quá 15% giữa quadrants.

### 7.10 Scenario 10: Ablation per signal

Drop 1 signal at a time (timbral, rhythmic, tonal, lyrics, va, emotion, mood). Measure NDCG@10 delta.

**Expected:** Lyrics drop = -8% (biggest impact). Other = -2-5%.

---

## 8. IMPLEMENTATION ROADMAP

### Tuần 1: Foundation

- [ ] Create `tools/backtest/` module structure.
- [ ] Implement `BacktestConfig`, `BacktestRunner`.
- [ ] Migrate existing `tools/backtest.py` logic vào `runners/full_evaluation.py`.
- [ ] Add CLI `python -m tools.backtest`.

### Tuần 2: Metrics implementation

- [ ] `metrics/accuracy.py`: Precision/Recall/NDCG/MAP/MRR/Hit.
- [ ] `metrics/diversity.py`: ILD (4 spaces), Coverage, ArtistGini.
- [ ] `metrics/novelty.py`: EFD, AvgPopRank.
- [ ] `metrics/music_specific.py`: MoodCoherence, TempoCoherence, GenreCoherence, ColorCoherence, SequentialSmoothness.
- [ ] `metrics/fairness.py`: LongtailCoverage.
- [ ] Unit tests cho mỗi metric.

### Tuần 3: Ground truth

- [ ] `datasets/ground_truth.py`: Mood/genre/era-based labeling.
- [ ] `datasets/playlist_crawler.py`: External editorial playlists crawler.
- [ ] `datasets/synthetic_users.py`: 500 virtual users + listening simulation.
- [ ] Generate test set v1: save to `data/backtest_test_set_v1.json`.

### Tuần 4: Baselines

- [ ] Implement 6 baselines (random, popularity, lyrics-only, audio-only, va-only, brightify-v72).
- [ ] Run full evaluation comparison.
- [ ] Generate baseline report.

### Tuần 5: Scenarios

- [ ] Implement 10 backtest scenarios.
- [ ] Per-segment runners (per quadrant, per genre).

### Tuần 6: Reporting

- [ ] `reporters/markdown.py`: detailed text report.
- [ ] `reporters/json_export.py`: machine-readable.
- [ ] `reporters/dashboard_html.py`: interactive HTML dashboard với plotly.

### Tuần 7: User study setup

- [ ] Design survey (NPS, perceived diversity/novelty, preference vs alternatives).
- [ ] Recruit 30-50 Vietnamese listeners.
- [ ] Pilot study với 5 users.

### Tuần 8: Integration

- [ ] CI integration (run reduced backtest mỗi PR; full weekly).
- [ ] Admin endpoint refactor: `/api/backtest/run` → call new framework.
- [ ] Documentation + onboarding.

---

## 9. REPORTING & DASHBOARD

### 9.1 Markdown report template

```markdown
# Backtest Report — {date}

## Configuration
- Engine version: v7.2
- Test set: backtest_test_set_v1
- N queries: 1,000
- K values: 5, 10, 20, 50
- Seed: 42

## Summary

| System | NDCG@10 | Precision@10 | Recall@50 | ILD@10 | Coverage | MoodCoherence |
|---|---|---|---|---|---|---|
| Random | 0.05 | 0.04 | 0.20 | 0.85 | 0.95 | 0.20 |
| Popularity | 0.32 | 0.30 | 0.45 | 0.35 | 0.05 | 0.40 |
| Lyrics-only | 0.48 | 0.45 | 0.60 | 0.45 | 0.65 | 0.65 |
| Audio-only | 0.42 | 0.40 | 0.55 | 0.55 | 0.70 | 0.70 |
| **Brightify v7.2** | **0.65** | **0.62** | **0.78** | **0.60** | **0.72** | **0.85** |

## Per-scenario breakdown
...

## Per-quadrant breakdown
...

## Ablation (per signal drop)
...

## Observations & Recommendations
...
```

### 9.2 HTML dashboard

- Interactive plotly charts:
  - Line chart: each metric at K=5,10,20,50.
  - Bar chart: system comparison per metric.
  - Heatmap: per-segment performance.
  - Scatter: NDCG vs ILD (trade-off).

### 9.3 JSON export

```json
{
  "metadata": {
    "timestamp": "2026-05-26T10:00:00Z",
    "engine_version": "v7.2",
    "config_hash": "abc123",
    "test_set_id": "v1"
  },
  "systems": {
    "brightify_v72": {
      "accuracy": {
        "precision_at_10": 0.62,
        "ndcg_at_10": 0.65,
        ...
      },
      "diversity": { ... },
      "per_quadrant": { ... }
    }
  }
}
```

---

## 10. USER STUDY (QUALITATIVE)

### 10.1 Mục tiêu

Validate offline metrics với perceived quality từ Vietnamese listeners.

### 10.2 Setup

- **N**: 30-50 participants (target Gen Z & Millennials).
- **Recruitment**: Facebook groups, Discord servers V-pop, music school students.
- **Compensation**: ~$10-20 per session (60 phút).

### 10.3 Protocol

**Session 1 (30 min): Blind comparison**

Hiển thị 3 playlist ẩn danh A/B/C cho cùng query (e.g., "buồn"):
- A = Brightify v7.2
- B = Random
- C = Popularity

User rate mỗi playlist (1-5 stars) trên 5 dimensions:
1. Relevance ("Có khớp với mood không?")
2. Diversity ("Có đa dạng không?")
3. Discovery ("Có bài hay mà chưa biết không?")
4. Coherence ("Các bài có nối liền nhau không?")
5. Overall ("Bạn có thích playlist này không?")

**Session 2 (30 min): Free exploration**

User dùng Brightify free với 5 task:
1. Tìm bài hợp tâm trạng hiện tại.
2. Tạo playlist tập gym.
3. Khám phá bài mới.
4. Tìm bài tương tự bài yêu thích.
5. Color/image query.

Sau mỗi task, NPS + open-ended feedback.

### 10.4 Metrics tổng hợp

- **NPS**: % Promoters (9-10) - % Detractors (0-6).
- **Top-line satisfaction**: avg rating across 5 dimensions.
- **Per-feature usage**: count uses of color/image/lyrics features.
- **Qualitative themes**: open coding của open-ended responses (top 5 strengths, top 5 weaknesses).

### 10.5 Validation

Correlation between offline metrics và user ratings:

| Offline metric | Expected user rating dimension | Min correlation |
|---|---|---|
| NDCG@10 | Relevance | ρ ≥ 0.5 |
| ILD@10 | Diversity | ρ ≥ 0.4 |
| EFD | Discovery | ρ ≥ 0.4 |
| MoodCoherence | Coherence | ρ ≥ 0.5 |

Nếu correlation thấp → offline metric không đại diện tốt → cần re-design.

---

## 11. CONTINUOUS EVALUATION (CI GATE)

### 11.1 GitHub Actions workflow

```yaml
# .github/workflows/backtest.yml
name: Backtest CI

on:
  pull_request:
    paths:
      - 'core/**'
      - 'config.py'
      - 'tools/backtest/**'

jobs:
  backtest-quick:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - name: Install
        run: pip install -r requirements.txt
      - name: Quick backtest
        run: python -m tools.backtest run --config configs/backtest_quick.yaml
      - name: Compare with baseline
        run: python -m tools.backtest compare --baseline data/baseline_metrics.json --tolerance 0.03
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: backtest-report
          path: logs/backtest/

  backtest-full:
    runs-on: ubuntu-latest
    timeout-minutes: 180
    if: github.event.pull_request.labels.*.name == 'full-backtest'
    steps:
      # ... full evaluation
```

### 11.2 Gating rules

**Auto-reject PR nếu:**
- NDCG@10 giảm > 3% so với baseline.
- MoodCoherence giảm > 5%.
- Coverage giảm > 10%.
- Latency p95 tăng > 30%.

**Require manual review nếu:**
- ILD trade-off với NDCG.
- Per-quadrant performance lệch > 15%.

### 11.3 Weekly full evaluation

Cron job mỗi Chủ nhật:
- Run full evaluation trên latest main.
- Generate dashboard.
- Post comment trong Slack/Discord channel #engineering.

---

## 12. TÀI LIỆU THAM KHẢO

### Papers (primary sources)

- McNee, Riedl, Konstan 2006 — "Being Accurate is Not Enough" — [CHI 2006](https://dl.acm.org/doi/abs/10.1145/1125451.1125659)
- Garcin et al. 2014 — "Offline and Online Evaluation of News Recommender Systems" — RecSys 2014
- Castells 2022 — "Offline Recommender System Evaluation: Challenges and New Directions" — [AI Magazine](https://onlinelibrary.wiley.com/doi/10.1002/aaai.12051)
- Time to Split 2025 — [arXiv 2507.16289](https://arxiv.org/abs/2507.16289)
- Critical Reexamination ILD 2023 — [arXiv 2305.13801](https://arxiv.org/pdf/2305.13801)
- Critical Study Data Leakage 2020 — [arXiv 2010.11060](https://arxiv.org/pdf/2010.11060)
- itemKNN deviation 2024 — [arXiv 2407.13531](https://arxiv.org/pdf/2407.13531)
- Kaminskas & Bridge 2016 — "Diversity, Serendipity, Novelty, Coverage" — [ACM TiiS](https://dl.acm.org/doi/10.1145/2926720)
- Vargas & Castells 2011 — "Rank and Relevance in Novelty and Diversity Metrics" — [paper](https://repositorio.uam.es/bitstream/handle/10486/12773/61509_Vargas_Sandoval_Saul.pdf)
- Unfair Artist Exposure 2020 — [arXiv 2003.11634](https://arxiv.org/pdf/2003.11634)
- Optimizing Generalized Gini 2022 — [arXiv 2204.06521](https://arxiv.org/abs/2204.06521)

### Frameworks

- [RecBole](https://recbole.io) — PyTorch, 100+ algorithms, unified API.
- [Cornac](https://cornac.preferred.ai) — Multimodal recsys focus (best for Brightify).
- [Microsoft Recommenders](https://github.com/microsoft/recommenders) — Notebook-driven.
- [LensKit](https://lkpy.lenskit.org) — Reproducibility focused.

### Evaluation guides

- [Evidently AI - 10 Metrics to Evaluate Recommender Systems](https://www.evidentlyai.com/ranking-metrics/evaluating-recommender-systems)
- [Aman's AI Journal - RecSys Metrics](https://aman.ai/recsys/metrics/)
- [Weaviate - Retrieval Evaluation Metrics](https://weaviate.io/blog/retrieval-evaluation-metrics)

### Internal docs

- `docs/PLAN_SYSTEM_UPGRADE.md` — companion upgrade plan.
- `docs/PLAN_DOCKERIZATION.md` — deployment.
- Current `tools/backtest.py` — legacy implementation, sẽ refactor.
- `api/system.py` — admin backtest endpoints, sẽ wire vào framework mới.

---

**Hết Plan 2.**
