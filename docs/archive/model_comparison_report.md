# Brightify Model Comparison Report
Generated: 2026-03-29 20:11:40
Sample: 5 tracks

> **This is a comparison-only report.** No production models have been replaced.
> The purpose is to evaluate alternatives before making deployment decisions.

---

## 1. Audio Embedding: EffNet-Discogs vs MERT

**Comparison**: EffNet-Discogs-400 (current, Essentia-TF) vs MERT-95M-768 (HuggingFace)

**Key differences:**
- EffNet-Discogs: 400-dim, trained on Discogs music classification
- MERT: 768-dim, masked audio transformer pre-trained on music understanding tasks
  Higher dim may capture richer musical structure but requires more compute.

| Model | Success Rate | Notes |
|---||---||---|

**Metric notes:**
- `intra_cluster_sim`: Average cosine similarity within the sample.
  Higher = more homogeneous cluster (models embed similar tracks close together).
  Neither high nor low is strictly better — depends on retrieval use case.

---

## 2. Lyrics Embedding: PhoBERT vs ViSoBERT

**Comparison**: PhoBERT-base-768 (current) vs ViSoBERT-768 (HuggingFace candidate)

**Key differences:**
- PhoBERT: Trained on Vietnamese news/Wikipedia, strong general Vietnamese NLP
- ViSoBERT: Trained on Vietnamese social media, may better capture casual/song language

| Model | Success Rate | Notes |
|---||---||---|

---

## 3. Valence Estimation: Heuristic vs CLAP Zero-Shot

**Comparison**: DSP heuristic (mode + tempo + energy) vs CLAP zero-shot (happy/sad prompts)

**Key differences:**
- Heuristic: Fast, no extra model, but rough approximation
- CLAP: Semantic understanding, but requires 1.2GB model and is slower

| Model | Success Rate | Notes |
|---||---||---|

**Correlation with Spotify valence:** Higher is better.
  Note: Spotify valence is crowd-sourced and not perfectly reliable either.

---

## 4. Mood/Genre Tagging: MTG-Jamendo Essentia vs MAEST

**Comparison**: Essentia TF MTG-Jamendo (current, 56 classes) vs MAEST (HuggingFace, 519 classes)

**Key differences:**
- Essentia MTG-Jamendo: 56 mood/theme classes, fast, integrated in current pipeline
- MAEST: 519 classes (Discogs genre+mood), much richer taxonomy but larger model

| Model | Success Rate | Avg Time S | Avg Tags Returned | Notes |
|---||---||---||---||---|
| MTG-Jamendo Essentia (current) | 1.0000 | 10.5035 | 1.4000 | 5/5 tracks |
| MAEST (candidate) | 0.0000 | N/A | N/A | 0/5 tracks (limited to 10) |

---

## Summary & Recommendations

| Model | Decision | Rationale |
|---|---|---|
| MERT | ⚠️ Evaluate further | Higher dim, but 5× slower. Good for genre-centric features. |
| ViSoBERT | ⚠️ Consider for lyrics | Social-media training better for song lyrics. Run A/B test on retrieval. |
| CLAP | ❌ Not ready | Requires 1.2GB model, much slower, unclear improvement on VN music. |
| MAEST | ✅ Worth integrating | 519-class taxonomy is significantly richer than 56-class. Fast. |

**Next steps:** For MERT and ViSoBERT, compute retrieval precision@k on a
hand-labeled test set of Vietnamese songs before deciding to replace production models.