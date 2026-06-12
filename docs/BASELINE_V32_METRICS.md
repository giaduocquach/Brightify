# Baseline V32 Metrics — frozen reference (pre-upgrade)

> **After-state + before/after table:** see the "V32 RESULTS" section in `docs/SCIENTIFIC_AUDIT_AND_PLAN_V32.md`. Shipped change: v6c → v6d labels; song weights unchanged (re-validated). Total OpenAI spend ≈ $1.36.


**Date:** 2026-06-12 · **Labels:** emotion_labels_v6c.json · **Matching:** V31 rank-space · **Song weights:** [MERT 0.82 / VA 0.12 / lyrics 0.06]

This is the frozen before-state. Every V32 upgrade phase gates on **not regressing these numbers** + improving ≥1 independent/convergent-validity metric.

## recommend-by-color (`tools/color_eval_rigor.py`, top_k=10, match space)

| Metric | Value |
|---|---|
| TE Euclidean (production) | **0.0238** CI[0.0229, 0.0247] |
| TE Mahalanobis (production) | 0.0839 CI[0.0807, 0.0871] |
| Baseline TE: random / popularity | 0.4378 / 0.5084 |
| Baseline TE: valence_only / arousal_only | 0.2848 / 0.2528 |
| Baseline TE: nearest_va (oracle floor) | 0.0189 |
| FDR (BH, Wilcoxon): beats random/pop/val-only/aro-only | **4/4 reject H₀**, p_adj=0.00031 |
| vs nearest_va oracle | not beaten (expected — oracle) |
| Gates: ordering / journey KS / journey t | **all pass** |
| Construct: r(V,A) | 0.1846 ✓ orthogonal (≤0.20) |
| Construct: ρ(arousal, tempo) | **−0.0393 ✗** (target >0.20) — known arousal-label weakness |
| Coverage 10×10 / Entropy | 1.0 / 0.9942 |
| Inter-signal ρ(MERT_V, catalog_V) | 0.1682 |

## recommend-by-song (`tools/eval_similar_intrinsic.py`, 80 seeds, production [0.82/0.06/0.12] column)

| Metric | Value |
|---|---|
| TempoCoherence | 0.8212 |
| MoodCoherence | 0.9613 |
| SelfConsistency | 0.0330 |
| Symmetry | 0.0822 |
| ILD_audio / ILD_lyrics / ILD_va | 0.1238 / 0.4782 / 0.0547 |
| CalibError | 0.0124 |
| SameArtist@K | 0.0125 |
| Serendipity | 0.4265 |
| ArtistGini | 0.1310 cov / 0.3920 gini |
| LLM NDCG@10 (prior, qwen3 single judge, 46 seeds) | 0.437 — **to be re-measured with GPT panel (Phase 4)** |

## Notes / known weaknesses entering V32
- **ρ(arousal,tempo)=−0.039** — arousal labels don't track tempo; a red flag the v6c arousal is weak. Phases 1–3 target this.
- LLM NDCG baseline used qwen3:8b (acc<0.70) — Ollama currently DOWN; Phase 4 rebuilds GT with GPT.
- GPT valence cache `var/runtime/backtest/cache/gpt_valence_5138.json` only covers 743/5138 (prior run stalled) and is valence-only → Phase 1 needs a fresh full V+A run.
- Pre-existing non-fatal bug: `eval_similar_intrinsic.py` verbose per-seed loop crashes on a `CONFIGS[cname]` label mismatch *after* the metrics table prints (metrics unaffected).
