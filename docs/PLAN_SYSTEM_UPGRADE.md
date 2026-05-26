# PLAN 1 — NÂNG CẤP HỆ THỐNG BRIGHTIFY

**Ngày tạo:** 2026-05-26
**Phiên bản hiện tại:** v7.1/v7.2
**Đích phiên bản:** v8.0
**Phạm vi:** Nâng cấp AI/ML stack, retrieval architecture, NLP tiếng Việt, cold-start, diversity. Tập trung vào những phần **chưa** được đề xuất trong các báo cáo cũ (SCIENTIFIC_RESEARCH_UPGRADE, AI_FEATURE_EVALUATION, MARKET_ANALYSIS, PIPELINE_REDESIGN_PROPOSAL).

> **Phạm vi loại trừ** (đã có plan riêng): Backtest & metrics → xem [PLAN_BACKTEST_METRICS.md]. Docker → xem [PLAN_DOCKERIZATION.md].

---

## MỤC LỤC

1. [Nguyên tắc chỉ đạo](#1-nguyên-tắc-chỉ-đạo)
2. [Tổng quan upgrade matrix](#2-tổng-quan-upgrade-matrix)
3. [Pillar A — Audio embedding upgrade (MERT/CLAP)](#3-pillar-a--audio-embedding-upgrade-mertclap)
4. [Pillar B — Vietnamese NLP upgrade (ViDeBERTa/ViSoBERT)](#4-pillar-b--vietnamese-nlp-upgrade-videbertavisobert)
5. [Pillar C — Hybrid retrieval & re-ranking](#5-pillar-c--hybrid-retrieval--re-ranking)
6. [Pillar D — Diversity & serendipity (MMR → DPP)](#6-pillar-d--diversity--serendipity-mmr--dpp)
7. [Pillar E — Emotion/mood recognition nâng cao](#7-pillar-e--emotionmood-recognition-nâng-cao)
8. [Pillar F — Cold-start solutions](#8-pillar-f--cold-start-solutions)
9. [Pillar G — Backend & DevX improvements](#9-pillar-g--backend--devx-improvements)
10. [Roadmap 6-tháng](#10-roadmap-6-tháng)
11. [Effort estimation & risks](#11-effort-estimation--risks)
12. [Tài liệu tham khảo](#12-tài-liệu-tham-khảo)

---

## 1. NGUYÊN TẮC CHỈ ĐẠO

1. **Differentiation qua multimodal** — Spotify/Zing/NCT không có color/image/Vietnamese-NLP đồng thời. Mục tiêu giữ vững và đào sâu lợi thế này.
2. **Vietnamese-first** — Mọi model upgrade phải so sánh hiệu năng trên catalog Việt (không chỉ benchmark Anh).
3. **No regression** — Mọi thay đổi phải pass backtest hiện có (xem PLAN_BACKTEST_METRICS).
4. **Backward compatible** — API contract giữ nguyên; thay model ở core layer.
5. **Incremental** — Mỗi pillar có thể ship độc lập, có flag enable/disable trong `config.py`.
6. **Khoa học** — Mỗi quyết định dựa trên A/B benchmark hoặc paper được trích dẫn.

---

## 2. TỔNG QUAN UPGRADE MATRIX

| Pillar | Hiện tại | Đề xuất | Ưu tiên | Effort |
|---|---|---|---|---|
| A. Audio embedding | Essentia EffNet-Discogs (1280-dim) | + MERT-95M (768-dim) hoặc CLAP-music | **Cao** | 2-3 tuần |
| B. Vietnamese NLP | PhoBERT-base-v2 | + ViDeBERTa-base hoặc ViSoBERT (tùy genre) | Cao | 1-2 tuần |
| C. Retrieval | Heuristic 7-signal fusion | RRF (BM25 + dense) → cross-encoder re-rank | **Cao** | 3-4 tuần |
| D. Diversity | Artist diversity penalty (greedy) | MMR (λ=0.7) → DPP (kernel-based) | TB | 1 tuần |
| E. Emotion | Heuristic combiner | MLP/transformer combiner train trên MTG-Jamendo + Vietnamese subset | TB | 2-3 tuần |
| F. Cold-start | Pure content-based | + Weather/time context API + KG embeddings | Thấp | 1-2 tuần |
| G. Backend | Sync SQLAlchemy, in-memory rate limiter | async SQLAlchemy + Redis cache + Redis rate limiter | TB | 2-3 tuần |

### 2.1 Artifact storage map (mọi pillar)

> Tham chiếu [PLAN_DOCKERIZATION.md §7 Data Layout & Persistence](PLAN_DOCKERIZATION.md#7-data-layout--persistence-master-guide). Mọi artifact mới TUÂN THỦ tier T1-T4.

| Pillar | Artifact | Tier | Path canonical | DB table | Backup |
|---|---|---|---|---|---|
| **A** | MERT-95M model weights | T3 | `var/volumes/hf_cache/` (HF auto) | — | Re-downloadable |
| **A** | MERT embeddings (4,300 × 768) | T2 | `var/runtime/processed/mert_embeddings.npy` | `song_embeddings.mert_embedding Vector(768)` | Weekly snapshot |
| **A** | CLAP model | T3 | `var/volumes/hf_cache/` | — | Re-downloadable |
| **A** | CLAP zero-shot prompts (VN+EN) | T1 | `app/core/clap_prompts.py` | — | Git |
| **B** | ViDeBERTa model | T3 | `var/volumes/hf_cache/` | — | Re-downloadable |
| **B** | ViSoBERT model | T3 | `var/volumes/hf_cache/` | — | Re-downloadable |
| **B** | Lyrics style classifier rules | T1 | `app/core/lyrics_router.py` | — | Git |
| **B** | ViDeBERTa embeddings (alt) | T2 | `var/runtime/processed/videberta_embeddings.npy` | `song_embeddings.videberta_embedding Vector(768)` (nếu A/B chuyển sang) | Snapshot |
| **C** | RRF fusion logic | T1 | `app/core/retrieval.py` | — | Git |
| **C** | Cross-encoder model | T3 | `var/volumes/hf_cache/` | — | Re-downloadable |
| **C** | Cross-encoder fine-tuned (optional) | T2 | `var/runtime/trained_models/reranker_v1/` | — | Per-version backup |
| **C** | Training pairs cho rerank | T2 | `var/runtime/annotations/rerank_pairs.jsonl` | — | Git LFS hoặc snapshot |
| **D** | MMR/DPP code | T1 | `app/core/diversity.py` | — | Git |
| **D** | Similarity matrix cache (optional) | T3 (Redis) | Redis key `sim_matrix:*` | — | Ephemeral |
| **E** | VN mood annotations (500 songs × 5 raters) | T2 | `var/runtime/annotations/vn_mood_500.csv` | `vn_mood_annotations` (tùy chọn) | Snapshot + Git LFS |
| **E** | MLP combiner weights | T2 | `var/runtime/trained_models/emotion_combiner_v1.onnx` | — | Per-version backup |
| **E** | Training logs/metrics | T2 | `var/runtime/trained_models/emotion_combiner_v1/training_log.json` | — | Snapshot |
| **E** | MTG-Jamendo subset (download once) | T2 | `var/runtime/datasets/mtg_jamendo/` | — | Local only (large) |
| **F** | KG triples export | T2 | `var/runtime/datasets/kg_triples.tsv` | (derived from DB) | Regenerable |
| **F** | KG embeddings (TransE/RotatE) | T2 | `var/runtime/processed/kg_song_embeddings.npy` | `song_embeddings.kg_embedding Vector(64)` | Snapshot |
| **F** | Weather API cache | T3 (Redis) | Redis key `weather:lat:lon` | — | Ephemeral, TTL 30 phút |
| **F** | VN holiday calendar | T1 | `app/config/vn_holidays.yaml` | — | Git |
| **G** | Async DB engine config | T1 | `app/db/engine.py` | — | Git |
| **G** | Redis cache entries | T3 | `var/volumes/redis_data/` | — | Ephemeral |
| **G** | Rate limit counters | T3 | Redis | — | Ephemeral |
| **G** | Structured logs | T2 | `var/logs/app/` | — | Local rotate, off-site optional |

### 2.2 Versioning artifacts (per-version trong T2)

Mọi artifact T2 lớn (embeddings, trained models) PHẢI version qua naming convention:

```
var/runtime/processed/
├── current → 2026-05-26_v8.0/     # symlink (production reading)
├── 2026-05-26_v8.0/
│   ├── vietnamese_music_embeddings_full.npy   # PhoBERT
│   ├── mert_embeddings.npy                    # Pillar A
│   ├── kg_song_embeddings.npy                 # Pillar F
│   ├── embeddings_metadata.json
│   └── manifest.sha256                        # hash để verify
└── 2026-04-15_v7.2/                # giữ rollback
    └── ...
```

App load qua env var `PROCESSED_VERSION=current` (default) → symlink, hoặc bind explicit version cho A/B test.

### 2.3 Database schema additions (Plan 1 → Alembic migrations)

| Migration | Mô tả | Pillar |
|---|---|---|
| `012_add_mert_embedding` | `ALTER TABLE song_embeddings ADD COLUMN mert_embedding Vector(768)` + HNSW index | A |
| `013_add_videberta_embedding` (optional) | Tương tự cho ViDeBERTa | B |
| `014_add_kg_embedding` | `Vector(64)` cho KG | F |
| `015_add_vn_mood_annotations` (optional) | `vn_mood_annotations(track_id, annotator_id, valence, arousal, emotions JSONB, agreement_score)` | E |
| `016_add_emotion_combiner_version` | `songs.emotion_combiner_version VARCHAR(16)` để track model dùng | E |
| `017_add_rerank_training_pairs` (optional) | `rerank_training_pairs(query_text, positive_track_id, negative_track_id, source)` | C |

Mỗi migration phải kèm **rollback** (`downgrade()`) — tham chiếu pattern hiện có ở `alembic/versions/`.

---

## 3. PILLAR A — AUDIO EMBEDDING UPGRADE (MERT/CLAP)

### 3.1 Vấn đề

- Essentia EffNet-Discogs là CNN-based feature extractor; không phải foundation model.
- 1280-dim không đồng nhất với PhoBERT 768-dim → khó concat trực tiếp.
- Không hỗ trợ cross-modal retrieval (text → music).
- Không có VN music trong training set → bias về Western pop/rock.

### 3.2 Quyết định kỹ thuật

**Khuyến nghị: tích hợp MERT-95M-768 song song với Essentia (không thay thế).**

**So sánh ứng viên:**

| Model | Size | Dim | Strength | Weakness |
|---|---|---|---|---|
| **MERT-95M** | ~340 MB | 768 | RVQ+CQT dual teacher, SOTA MIR | Trained chủ yếu Western music |
| **MusicFM** | ~600 MB | 1024 | Conformer + BEST-RQ | Larger, slower |
| **CLAP (LAION music)** | ~700 MB | 512 | Audio-text dual encoder, zero-shot | 512-dim, không tốt cho tonal/rhythmic |
| **AST** | ~340 MB | 768 | Pure attention spectrogram | General audio (không chuyên music) |

**Lý do chọn MERT-95M:**
- 768-dim **đồng nhất với PhoBERT** → có thể concat hoặc fusion qua MLP layer.
- Explicit tonal teacher (CQT) — quan trọng cho nhạc Việt pentatonic.
- Manageable size cho CPU inference (~340 MB).
- HuggingFace có sẵn checkpoint: `m-a-p/MERT-v1-95M`.

**Bổ sung CLAP cho zero-shot mood tagging:**
- `laion/larger_clap_music` cho mood prompts ("vui tươi", "buồn man mác") → bổ sung emotion classifier hiện tại.

### 3.3 Implementation plan

**Bước 1: Add MERT inference module** (~1 tuần)

```
tools/extract_audio_features.py:
  + def extract_mert_embedding(mp3_path: str) -> np.ndarray:
      """Returns 768-dim embedding from MERT-v1-95M."""
      # Sample at 24kHz, chunk 5s segments, mean-pool layer 8
```

- Add column `mert_embedding` (Vector(768)) vào `songs` hoặc bảng riêng `audio_embeddings`.
- Alembic migration `012_add_mert_embedding`.
- Phase 5 pipeline: extract MERT cho mỗi MP3 (~2-3s/track CPU, ~0.3s/track GPU).

**Bước 2: Add CLAP zero-shot mood module** (~1 tuần)

```
core/clap_mood_classifier.py:
  class CLAPMoodClassifier:
      def __init__(self):
          self.model = ClapModel.from_pretrained("laion/larger_clap_music")
          self.prompts_vi = ["bài hát vui tươi", "bài hát buồn man mác", ...]  # 13 emotion VN prompts
          self.prompts_en = ["a happy upbeat song", ...]
          self._precompute_text_embeddings()

      def classify(self, audio_path) -> Dict[str, float]:
          # Returns 13-dim emotion distribution
```

- Pre-compute text embeddings cho 13 emotion Việt + Anh.
- Single audio forward pass → cosine với 13 prompts → softmax.

**Bước 3: Fusion với recommendation engine** (~1 tuần)

Trong `core/recommendation_engine.py`:

```python
# Trong __init__():
self.mert_matrix = load_mert_embeddings()   # (n_songs, 768) L2-normalized

# Trong recommend_by_song(): thêm signal #8
mert_sim = self.mert_matrix @ self.mert_matrix[song_idx]  # (n_songs,)
mert_sim = (mert_sim + 1) / 2

# Reweight 8 signals (giảm timbral/rhythmic vì có overlap với MERT)
NEW_WEIGHTS = {
    'timbral':  0.08,   # was 0.12
    'rhythmic': 0.07,   # was 0.10
    'tonal':    0.05,   # was 0.08
    'lyrics':   0.25,   # was 0.28
    'va':       0.15,   # was 0.17
    'emotion':  0.13,   # was 0.15
    'mood':     0.10,   # unchanged
    'mert':     0.17,   # NEW
}
# Σ = 1.00
```

Thêm vào `config.py` flag `ENABLE_MERT = True`.

### 3.4 Success criteria

- MERT embedding extract thành công cho ≥ 99% catalog (4,300+ tracks).
- NDCG@10 trên backtest tăng ≥ 5% so với baseline 7-signal.
- Latency thêm < 50ms cho recommend endpoint (vectorized).
- Disk: thêm ~13 MB cho embeddings (4,300 × 768 × 4 bytes).

### 3.5 Tài liệu tham khảo

- [MERT paper (arXiv 2306.00107)](https://arxiv.org/abs/2306.00107)
- [LAION CLAP](https://github.com/LAION-AI/CLAP)
- [Foundation Models for Music Survey 2024](https://arxiv.org/html/2408.14340v1)
- [Towards Leveraging Contrastively Pretrained Embeddings for Recsys](https://arxiv.org/html/2409.09026)

---

## 4. PILLAR B — VIETNAMESE NLP UPGRADE (VIDEBERTA/VISOBERT)

### 4.1 Vấn đề

- PhoBERT-base-v2 là SOTA năm 2020, nay đã 5 năm.
- Không xử lý tốt teencode, viết tắt, emoji — phổ biến trong V-pop/rap Việt 2024-2026.
- Không có model alternative để A/B test.

### 4.2 Quyết định kỹ thuật

**Khuyến nghị: dual-encoder routing — PhoBERT cho lyrics chuẩn, ViSoBERT cho social/teen content.**

**So sánh:**

| Model | Năm | Strength | Khi dùng |
|---|---|---|---|
| **PhoBERT-base-v2** (đang dùng) | 2020 | Vietnamese Wiki + news 20GB | Lyrics chuẩn, nhạc truyền thống |
| **ViDeBERTa-base** | 2023 | DeBERTa arch, +0.4% NER vs XLM-R | Lyrics chuẩn (drop-in upgrade) |
| **ViSoBERT** | 2023 EMNLP | Trained social media (teencode, emoji) | V-pop trẻ, rap Việt, indie |
| **BARTpho** | 2022 VinAI | Seq2seq | Sinh mô tả tự động (audio captioning) |

### 4.3 Implementation plan

**Bước 1: Add ViDeBERTa support** (~3 ngày)

```python
# config.py
LYRICS_ENCODER = os.environ.get("LYRICS_ENCODER", "phobert")  # phobert | videberta | visobert
LYRICS_MODEL_MAP = {
    "phobert":    "vinai/phobert-base-v2",
    "videberta":  "Fsoft-AIC/videberta-base",
    "visobert":   "uitnlp/visobert",
}
```

**Bước 2: Lyrics classifier để route** (~3 ngày)

Heuristic đơn giản:

```python
def detect_lyrics_style(text: str) -> str:
    teen_indicators = ['ko', 'k', 'r', 'dc', 'oki', 'ny', 'fan', '<3', 'huhu', 'hihi', '😂', '💔']
    teen_count = sum(text.lower().count(t) for t in teen_indicators)
    if teen_count > 3 or has_emoji(text):
        return "social"
    return "standard"
```

```python
# Phase 6 process_data.py
encoder = "visobert" if detect_lyrics_style(lyrics) == "social" else "videberta"
embedding = encode_with(encoder, lyrics)
```

**Bước 3: A/B test** (~1 tuần)

- Split catalog: 70% encoded với PhoBERT (control), 30% với ViDeBERTa+ViSoBERT routing (treatment).
- Run backtest framework (xem PLAN_BACKTEST_METRICS).
- Decision: nếu treatment NDCG@10 tăng ≥ 3% và MoodCoherence tăng ≥ 5% → roll out 100%.

**Bước 4: BARTpho audio captioning** (~1 tuần, optional)

Sinh natural-language description cho mỗi bài để bổ sung text channel:

```
Input: audio features + Vietnamese mood
Output: "Bài hát ballad buồn với giai điệu acoustic nhẹ nhàng, giọng nam ấm áp, tốc độ chậm 75 BPM, phù hợp nghe vào buổi tối khi cô đơn."
```

Description này được embed vào PhoBERT/ViDeBERTa → bổ sung lyrics embedding.

### 4.4 Success criteria

- Coverage ViSoBERT routing: 25-35% catalog (V-pop trẻ, rap).
- Treatment vs control: NDCG@10 +3%, MoodCoherence +5%.
- Không tăng latency (embeddings pre-computed offline).

### 4.5 Tài liệu tham khảo

- [ViDeBERTa (arXiv 2301.10439)](https://arxiv.org/abs/2301.10439)
- [ViSoBERT (EMNLP 2023)](https://arxiv.org/html/2310.11166v1)
- [BARTpho VinAI](https://research.vinai.io/bartpho-pre-trained-sequence-to-sequence-models-for-vietnamese/)

---

## 5. PILLAR C — HYBRID RETRIEVAL & RE-RANKING

### 5.1 Vấn đề

Brightify hiện tại:
- Đã có `pg_trgm` (lexical, gần BM25) trong `artists.name`, `songs.track_name`.
- Đã có pgvector HNSW trên `song_embeddings.embedding`.
- **NHƯNG**: hai cơ chế chạy độc lập, không fusion. Mood/color query bỏ qua trigram; search query bỏ qua dense.
- Không có re-ranking stage — chỉ heuristic weighted sum.

### 5.2 Quyết định kỹ thuật

**Two-stage retrieval pipeline:**

```
Stage 1: Candidate Generation (recall focused)
  ├── Lexical: pg_trgm trên track_name, artist, lyrics_cleaned  → top 200
  ├── Dense: pgvector HNSW trên PhoBERT embedding              → top 200
  ├── Dense: pgvector HNSW trên MERT audio embedding (Pillar A) → top 200
  └── Fusion: RRF (k=60) → top 100 candidates

Stage 2: Re-ranking (precision focused)
  └── Cross-encoder hoặc heuristic 7-signal fusion → top 10
```

### 5.3 Implementation plan

**Bước 1: Implement RRF fusion** (~3 ngày)

```python
# core/retrieval.py (NEW FILE)

def reciprocal_rank_fusion(
    ranked_lists: List[List[int]],
    k: int = 60,
    weights: Optional[List[float]] = None,
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion (Cormack et al. 2009).
    score(d) = Σ w_i / (k + rank_i(d))
    """
    scores: Dict[int, float] = defaultdict(float)
    weights = weights or [1.0] * len(ranked_lists)
    for ranked_list, w in zip(ranked_lists, weights):
        for rank, item_id in enumerate(ranked_list, start=1):
            scores[item_id] += w / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])
```

**Bước 2: Multi-source candidate generation** (~1 tuần)

```python
# core/recommendation_engine.py
def _retrieve_candidates(self, query: QueryContext, top_n: int = 200) -> List[int]:
    sources = []

    # Lexical: nếu có text query
    if query.text:
        lex_ids = self._pgtrgm_search(query.text, limit=top_n)
        sources.append(lex_ids)

    # Dense lyrics
    if query.lyrics_embedding is not None:
        dense_lyr = self._pgvector_search('embedding', query.lyrics_embedding, limit=top_n)
        sources.append(dense_lyr)

    # Dense audio (MERT - khi Pillar A xong)
    if query.audio_embedding is not None:
        dense_aud = self._pgvector_search('mert_embedding', query.audio_embedding, limit=top_n)
        sources.append(dense_aud)

    # V-A proximity (NumPy in-memory)
    if query.va is not None:
        va_ids = self._va_proximity_search(query.va, top_n=top_n)
        sources.append(va_ids)

    return reciprocal_rank_fusion(sources, k=60)[:100]
```

**Bước 3: Cross-encoder re-rank** (~1-2 tuần)

```python
# core/reranker.py (NEW FILE)
from sentence_transformers import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: List[Tuple[int, str]], top_k: int = 20):
        pairs = [(query, doc) for _, doc in candidates]
        scores = self.model.predict(pairs)  # batch
        ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])
        return [c for (c, _) in ranked[:top_k]]
```

**Lưu ý:**
- Cross-encoder Vietnamese: cần fine-tune trên `(query, lyrics)` pairs với hard negatives. Nếu chưa có data, dùng zero-shot multilingual cross-encoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`).
- Latency: cross-encoder rerank 100 candidates ~100-300ms CPU. Acceptable cho recommendation endpoint không real-time.

**Bước 4: Two-stage pipeline integration** (~3 ngày)

Trong `recommend_by_colors()`, `recommend_by_song()`, etc.:

```python
candidates = self._retrieve_candidates(query, top_n=200)
fused_scores = self._fusion_scores(candidates, query)  # 7-signal hiện tại
if query.has_text:
    reranked = self.reranker.rerank(query.text, candidate_docs, top_k=20)
    final = self._fast_rank(reranked + fused_scores, top_k=10)
else:
    final = self._fast_rank(fused_scores, top_k=10)
```

### 5.4 Success criteria

- Recall@100 stage 1 ≥ 0.85 (so với ground truth từ ablation).
- Precision@10 stage 2 (after rerank) ≥ baseline + 8%.
- p95 latency ≤ 500ms với rerank, ≤ 200ms không rerank.

### 5.5 Tài liệu tham khảo

- [RRF (Cormack 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Hybrid BM25 + Dense (Tian Pan 2026)](https://tianpan.co/blog/2026-04-12-hybrid-search-production-bm25-dense-embeddings)
- [Sentence-transformers retrieve & rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)

---

## 6. PILLAR D — DIVERSITY & SERENDIPITY (MMR → DPP)

### 6.1 Vấn đề

Brightify hiện tại chỉ có **artist diversity penalty** (greedy multiplicative). Không xét:
- Genre diversity
- Mood quadrant balance
- Lyrics semantic diversity

→ Top-K có thể bị "skew" về cùng quadrant Q1 dù catalog đa dạng.

### 6.2 Quyết định kỹ thuật

**Phase 1: MMR (Maximal Marginal Relevance)** — đơn giản, dễ tích hợp.

```
MMR = arg max_i [ λ · rel(i) - (1-λ) · max_{j∈selected} sim(i, j) ]
```

- `λ = 0.7` (relevance:diversity = 70:30).
- `sim(i, j)`: cosine của MERT embedding (audio diversity) hoặc concat[lyrics_emb || va_vec || color_hsl].

**Phase 2: DPP (Determinantal Point Process)** — Chen et al. 2018 Fast Greedy MAP.

DPP gán probability cao cho subsets có cả relevance lẫn diversity.

```
P(S) ∝ det(L_S)
L_{ij} = relevance_i · relevance_j · K_{ij}
K_{ij} = cosine_sim(embedding_i, embedding_j)
```

Fast Greedy MAP: O(K · N²) cho N=100, K=10 ≈ 100,000 ops → ms-scale.

### 6.3 Implementation plan

**Bước 1: MMR module** (~3 ngày)

```python
# core/diversity.py (NEW FILE)
def mmr_rerank(
    candidates: List[int],
    relevance: np.ndarray,         # (N,)
    similarity_matrix: np.ndarray, # (N, N)
    top_k: int = 10,
    lambda_: float = 0.7,
) -> List[int]:
    selected = []
    remaining = set(range(len(candidates)))

    while len(selected) < top_k and remaining:
        if not selected:
            best = max(remaining, key=lambda i: relevance[i])
        else:
            best = max(remaining, key=lambda i:
                lambda_ * relevance[i] -
                (1 - lambda_) * max(similarity_matrix[i, j] for j in selected)
            )
        selected.append(best)
        remaining.remove(best)

    return [candidates[i] for i in selected]
```

**Bước 2: DPP Fast Greedy MAP** (~1 tuần)

```python
# core/diversity.py
def dpp_greedy_map(
    relevance: np.ndarray,
    similarity_matrix: np.ndarray,
    top_k: int = 10,
) -> List[int]:
    """Chen et al. 2018 - Fast Greedy MAP for DPP."""
    N = len(relevance)
    L = np.outer(relevance, relevance) * similarity_matrix

    selected = []
    di2s = np.diag(L).copy()
    # ... implementation (40 LOC)
    return selected
```

**Bước 3: Serendipity slots** (~2 ngày)

Inject 10-20% slots cho "wild card" — bài hát có audio_sim cao nhưng:
- Khác genre primary của query
- Khác mood quadrant
- Artist không xuất hiện trong top recent plays

```python
def inject_serendipity(top_k: List[int], pool: List[int], ratio: float = 0.15):
    n_serendip = max(1, int(top_k * ratio))
    # ...
```

**Bước 4: Config & A/B** (~1 ngày)

```python
# config.py
DIVERSITY_METHOD = os.environ.get("DIVERSITY_METHOD", "mmr")  # greedy | mmr | dpp
DIVERSITY_LAMBDA = 0.7
SERENDIPITY_RATIO = 0.15
```

### 6.4 Success criteria

- ILD@10 (Intra-List Diversity) tăng ≥ 20% vs baseline greedy.
- Artist Gini coefficient ≤ 0.4 (baseline ~0.6).
- Genre coverage trong top-10 ≥ 4 (baseline ~2).
- NDCG@10 không giảm quá 3%.
- User study qualitative: "đa dạng nhưng vẫn hợp lý" score ≥ 4/5.

### 6.5 Tài liệu tham khảo

- [MMR (Carbonell & Goldstein 1998)](https://dl.acm.org/doi/10.1145/290941.291025)
- [DPP Fast Greedy MAP (Chen et al. 2018)](https://arxiv.org/pdf/1709.05135)
- [SMMR 2025](https://www.researchgate.net/publication/393657796_SMMR)

---

## 7. PILLAR E — EMOTION/MOOD RECOGNITION NÂNG CAO

### 7.1 Vấn đề

- Lexicon Việt 500-730 từ → recall hạn chế (không bắt được paraphrase, metaphor, sarcasm).
- Heuristic combiner audio (60%) + lyrics (40%) chưa learn, có thể không tối ưu.
- 13 emotion categories có thể overlap (love vs romantic; nostalgic vs melancholic).

### 7.2 Quyết định kỹ thuật

**A. Learned combiner thay heuristic** — MLP 3 layers trên top of features.

```
Input: [audio_va (2) || lyrics_va (2) || phobert_emb (768) || mert_emb (768) || color_va (2)]
       = 1542-dim
MLP: 1542 → 512 → 256 → 26  (13 emotion × {valence, arousal})
Output: final V-A coordinates
```

**B. Train trên multi-source:**
- MTG-Jamendo Mood (56 tags) — base.
- DEAM dataset (1,802 songs V-A continuous).
- **Vietnamese subset hand-labeled** (~500 songs, 5-10 annotators per song).

**C. CLAP zero-shot bổ sung** (Pillar A overlap):
- Prompt tiếng Việt: "bài hát {emotion}" → 13 categories.
- Ensemble với lexicon: `prob = 0.5 * lexicon + 0.3 * mlp + 0.2 * clap`.

### 7.3 Implementation plan

**Bước 1: Vietnamese mood annotation crowdsourcing** (~3 tuần)

- Setup task: 500 songs × 5 annotators × {valence, arousal, top-3 emotions}.
- Platform: Google Forms hoặc Label Studio self-hosted.
- Quality control: cohen's kappa ≥ 0.6 inter-annotator agreement.
- Budget: ~$500-1000 (50K-100K VND/song × 5 annotators).

**Bước 2: MLP combiner training** (~1 tuần)

```python
# tools/train_emotion_combiner.py
class EmotionCombiner(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(1542, 512), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(256, 26),
        )
    def forward(self, x):
        return self.net(x)

# Loss: MSE cho V-A regression + CrossEntropy cho 13-class emotion
```

- Train trên DEAM (V-A) + MTG-Jamendo (multi-label) + VN subset.
- 80/10/10 train/val/test split.
- Early stopping trên val loss.
- Export to ONNX để CPU inference nhanh.

**Bước 3: CLAP zero-shot integration** (~3 ngày)

```python
# core/emotion_analysis.py
class CLAPEmotionPredictor:
    PROMPTS_VI = {
        'happy':       ["bài hát vui tươi", "một bài hát hạnh phúc"],
        'sad':         ["bài hát buồn", "bài hát man mác"],
        # ... 13 categories
    }
    def predict(self, audio_path) -> Dict[str, float]:
        # ...
```

**Bước 4: Multi-task fine-tuning ViDeBERTa** (~1 tuần, optional)

Fine-tune ViDeBERTa head cho:
- Task 1: 13-class emotion classification
- Task 2: V-A regression (continuous)
- Task 3: Genre tagging

Multi-task sharing → tăng generalization.

### 7.4 Success criteria

- Inter-annotator agreement (Cohen's κ) ≥ 0.6 trên VN subset.
- MLP combiner CCC (Concordance Correlation Coefficient) ≥ 0.75 valence, ≥ 0.65 arousal trên VN test set.
- MoodCoherence metric trong playlist tăng ≥ 10%.
- 13 emotion overlap reduced (cluster purity ≥ 0.7).

### 7.5 Tài liệu tham khảo

- [MTG-Jamendo Mood](https://mtg.github.io/mtg-jamendo-dataset/)
- [Music Emotion Recognition Survey 2025](https://link.springer.com/article/10.1007/s00530-025-01871-w)
- [Multi-task MER (arXiv 2110.04765)](https://arxiv.org/pdf/2110.04765)

---

## 8. PILLAR F — COLD-START SOLUTIONS

### 8.1 Vấn đề

- Bài mới thêm → có thể bị penalized do không có user signal (Brightify content-based nên vấn đề này nhẹ hơn các platform khác).
- Tuy nhiên: nếu lyrics ngắn hoặc instrumental → V-A từ audio mạnh hơn, nhưng emotion vector yếu.
- Không có context awareness ngoài color/image/mood (thiếu weather, location).

### 8.2 Quyết định kỹ thuật

**A. Multi-task feature learning với Knowledge Graph** — bù khi modality yếu.

Tận dụng star schema hiện có: build KG embedding với:
- Nodes: Artist, Album, Genre, Era, Region
- Edges: performs(Artist, Song), collaborated(Artist, Artist), genre_of(Song, Genre)

Embedding qua TransE hoặc RotatE (~64-dim), thêm signal vào fusion.

**B. Weather/Time context API**:
- OpenWeatherMap API → current weather.
- Time-of-day, day-of-week (sẵn có).
- Holiday calendar (Tết, Trung Thu, Giáng Sinh → mood-specific Vietnamese).

**C. Audio-only fallback strengthening**:
- Nếu `has_lyrics=False`: weights re-distribute với audio_signal weight +0.15.
- Đã có trong code, nhưng cần refine.

### 8.3 Implementation plan

**Bước 1: KG embedding pipeline** (~1 tuần)

```python
# tools/train_kg_embeddings.py
import torch
from pykeen.models import TransE, RotatE

# Load triples từ DB:
# (artist, performs, song), (song, in_album, album), (artist, has_genre, genre), ...

triples = load_triples_from_db()
model = TransE(triples_factory=tf, embedding_dim=64)
trained = pipeline(training=tf, model=model, training_kwargs=dict(num_epochs=200))

# Export artist/album/song embeddings
np.save('data/kg_song_embeddings.npy', song_embs)
```

Add column `kg_embedding Vector(64)` to songs.

**Bước 2: Weather API integration** (~3 ngày)

```python
# api/context_provider.py (NEW FILE)
class ContextProvider:
    def get_current_context(self, lat: float, lon: float) -> Dict:
        weather = await fetch_openweather(lat, lon)
        return {
            'temperature': weather.temp,
            'condition': weather.main,  # Clear/Clouds/Rain/Snow/Thunderstorm
            'time_of_day': hour_to_period(datetime.now().hour),
            'is_holiday': check_vn_holiday(datetime.now()),
        }
```

Brightify `/api/recommend/context-mix` đã có nhưng nhận từ client. Bổ sung server-side resolution.

**Bước 3: Vietnamese holiday mood mapping** (~3 ngày)

```python
VN_HOLIDAY_MOODS = {
    'tet': {'valence_shift': 0.15, 'preferred_emotions': ['joyful', 'hopeful'], 'genres': ['nhac xuan']},
    'mid_autumn': {'valence_shift': 0.08, 'preferred_emotions': ['nostalgic']},
    'christmas': {'valence_shift': 0.10, 'preferred_emotions': ['romantic', 'peaceful']},
    'valentine': {'preferred_emotions': ['romantic', 'love']},
    # ...
}
```

### 8.4 Success criteria

- Cold-start (bài mới thêm 7 ngày qua): NDCG@10 ≥ 80% so với bài cũ.
- Context-aware recommend tăng CTR ≥ 5% vs context-less baseline.
- Holiday detection accuracy ≥ 95% với mapping VN-specific.

### 8.5 Tài liệu tham khảo

- [KG + Multi-task RecSys (Nature 2024)](https://www.nature.com/articles/s41598-024-52463-z)
- [Weather-Based Music Cold-Start](https://link.springer.com/chapter/10.1007/978-3-031-71773-4_38)
- [Awesome-Cold-Start-Recommendation](https://github.com/YuanchenBei/Awesome-Cold-Start-Recommendation)

---

## 9. PILLAR G — BACKEND & DEVX IMPROVEMENTS

### 9.1 Async SQLAlchemy migration

**Vấn đề:** FastAPI là async, nhưng SQLAlchemy 2.0 sync block event loop → throughput hạn chế.

**Plan:**
- Add `asyncpg` driver: `DATABASE_URL=postgresql+asyncpg://...`
- Convert `db/engine.py` → `AsyncEngine`, `AsyncSession`.
- Endpoint signatures: `async def` + `await session.execute(...)`.
- Effort: ~1-2 tuần (chủ yếu refactoring + test).
- Expected throughput: 3-5x vs sync.

### 9.2 Redis cache layer

**Hot queries cần cache:**
- `/api/songs/featured`, `/api/songs/new-releases`, `/api/genres`, `/api/moods`, `/api/statistics`.
- TTL 5-30 phút tùy endpoint.
- Cache key: pattern + query params hash.

```python
# api/cache.py (NEW)
import redis.asyncio as redis

cache = redis.Redis(host='redis', decode_responses=True)

async def cache_get_or_set(key, fn, ttl=300):
    val = await cache.get(key)
    if val:
        return json.loads(val)
    result = await fn()
    await cache.setex(key, ttl, json.dumps(result))
    return result
```

### 9.3 Redis-based rate limiter

**Vấn đề:** In-memory sliding window không scale ra nhiều worker/container.

**Plan:** Move to Redis với `redis-py` Lua script atomicity.

```python
# api/rate_limit.py (refactor)
RATE_LIMIT_SCRIPT = """
  local key = KEYS[1]
  local window = tonumber(ARGV[1])
  local limit = tonumber(ARGV[2])
  local now = tonumber(ARGV[3])
  redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
  local count = redis.call('ZCARD', key)
  if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return 1
  end
  return 0
"""
```

### 9.4 Structured logging

```python
# Migrate from print() → loguru with JSON serializer
from loguru import logger
logger.add(sys.stdout, serialize=True)  # JSON output

logger.info("recommendation_made", extra={
    "user_session": session_id,
    "rec_type": "color",
    "top_k": 10,
    "latency_ms": elapsed,
})
```

→ Integrate với log aggregator (Loki, Datadog, ...).

### 9.5 Background tasks via Celery (optional)

**Hiện tại:** Pipeline chạy CLI manual.
**Đề xuất:** Celery + Redis backend.

```python
# tools/celery_tasks.py
@celery_app.task
def run_pipeline_phase(phase: int):
    # ...
```

→ Frontend admin có thể trigger pipeline qua API.

### 9.6 Effort

- Async SQLAlchemy: 1-2 tuần
- Redis cache + rate limiter: 1 tuần
- Structured logging: 2 ngày
- Celery (optional): 1 tuần

---

## 10. ROADMAP 6 THÁNG

### Tháng 1: Foundation

- **Tuần 1-2**: Pillar A bước 1 — MERT embedding extraction (pipeline + migration).
- **Tuần 3-4**: Pillar A bước 2-3 — CLAP zero-shot + fusion integration.

### Tháng 2: Retrieval & NLP

- **Tuần 5-6**: Pillar C — RRF fusion + multi-source candidate generation.
- **Tuần 7**: Pillar B — ViDeBERTa/ViSoBERT routing.
- **Tuần 8**: Pillar D — MMR diversity.

### Tháng 3: Quality

- **Tuần 9-10**: Pillar E bước 1 — Vietnamese mood annotation start.
- **Tuần 11**: Pillar C bước 3 — Cross-encoder rerank.
- **Tuần 12**: Pillar D bước 2 — DPP implementation.

### Tháng 4: Backend

- **Tuần 13-14**: Pillar G — Async SQLAlchemy migration.
- **Tuần 15**: Pillar G — Redis cache + rate limiter.
- **Tuần 16**: Pillar G — Structured logging.

### Tháng 5: Polish

- **Tuần 17-18**: Pillar E bước 2 — MLP combiner training (sau khi data đủ).
- **Tuần 19**: Pillar F — KG embeddings + weather API.
- **Tuần 20**: Pillar E bước 3 — CLAP integration.

### Tháng 6: Validation & Launch

- **Tuần 21-22**: Backtest toàn diện (PLAN_BACKTEST_METRICS).
- **Tuần 23**: User study Vietnamese listeners (30-50 người).
- **Tuần 24**: v8.0 release + retrospective.

---

## 11. EFFORT ESTIMATION & RISKS

### 11.1 Effort tổng

| Pillar | Effort (person-week) |
|---|---|
| A. Audio embedding | 3 |
| B. Vietnamese NLP | 2 |
| C. Retrieval & rerank | 4 |
| D. Diversity | 1 |
| E. Emotion (ex annotation) | 3 |
| F. Cold-start | 2 |
| G. Backend | 4 |
| Annotation (E) | 3 (calendar) |
| Testing & launch | 4 |
| **TỔNG** | **26 person-week** |

Với 1 dev full-time: ~6 tháng. Với 2 dev parallel: ~3.5 tháng.

### 11.2 Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| MERT performance kém trên VN music | TB | Cao | A/B test sớm, fallback Essentia |
| Cross-encoder Vietnamese không có pre-trained | Cao | TB | Dùng multilingual mMiniLM; fine-tune sau |
| Vietnamese annotation chậm/kém quality | TB | Cao | Pilot 50 songs trước; cohen's κ gating |
| ViSoBERT routing heuristic không chính xác | Thấp | Thấp | Fallback ViDeBERTa nếu uncertain |
| Async migration regression bug | TB | Cao | Feature flag, gradual rollout |
| Backtest reveal v8.0 không tốt hơn v7.2 | Thấp | Cao | Revert flags, iterate per-pillar |
| Resource constraints (GPU) | TB | TB | Mọi inference CPU-friendly chọn |

### 11.3 Success metrics tổng

- Offline: NDCG@10 +15-20%, MoodCoherence +15%, ILD@10 +20%, Coverage +30%.
- Online (nếu có A/B): CTR +10%, session length +15%, skip rate -10%.
- Qualitative: NPS Vietnamese users ≥ 40.

---

## 12. TÀI LIỆU THAM KHẢO

### Papers (cited above)

- Li et al. 2023 — MERT — [arXiv 2306.00107](https://arxiv.org/abs/2306.00107)
- Wu et al. 2023 — LAION CLAP — [arXiv 2211.06687](https://arxiv.org/abs/2211.06687)
- Huang et al. 2022 — MuLan — [arXiv 2208.12415](https://arxiv.org/abs/2208.12415)
- Tran et al. 2023 — ViDeBERTa — [arXiv 2301.10439](https://arxiv.org/abs/2301.10439)
- Nguyen et al. 2023 — ViSoBERT — [arXiv 2310.11166](https://arxiv.org/html/2310.11166v1)
- Cormack et al. 2009 — RRF — [paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- Karpukhin et al. 2020 — DPR
- Reimers & Gurevych — sentence-transformers — [sbert.net](https://www.sbert.net/)
- Khattab & Zaharia 2020 — ColBERT
- Chen et al. 2018 — DPP Fast Greedy MAP — [arXiv 1709.05135](https://arxiv.org/pdf/1709.05135)
- Carbonell & Goldstein 1998 — MMR
- Russell 1980 — Circumplex Model
- Jonauskaite et al. 2020 — Color-emotion universal patterns
- Aljanaki et al. 2017 — DEAM dataset

### Competitor analysis

- [Spotify Newsroom 2025](https://newsroom.spotify.com/2025-12-29/year-in-features/)
- [Music-Tomorrow Spotify Guide](https://www.music-tomorrow.com/blog/how-spotify-recommendation-system-works-complete-guide)
- [YouTube Transformers Recommendation](https://research.google/blog/transformers-in-music-recommendation/)
- [Amazon Music Personalization](https://www.amazon.science/publications/beyond-collaborative-filtering-using-transformers-for-personalized-music-recommendation)
- [Vietnam Music Streaming Q1 2024](https://www.decisionlab.co/blog/vietnam-music-streaming-industry-q1-2024)

### Internal docs

- `docs/SCIENTIFIC_RESEARCH_UPGRADE_REPORT.md` — đã đề xuất PhoBERT v2, DEAM (đã làm).
- `docs/AI_FEATURE_EVALUATION.md` — v7.2 evaluation.
- `docs/MARKET_ANALYSIS_REPORT.md` — 10 features A-J đã đề xuất.
- `docs/PIPELINE_REDESIGN_PROPOSAL.md` — Essentia replacement plan.
- `docs/PLAN_BACKTEST_METRICS.md` — Backtest framework (companion plan).
- `docs/PLAN_DOCKERIZATION.md` — Deployment (companion plan).

---

**Hết Plan 1.**
