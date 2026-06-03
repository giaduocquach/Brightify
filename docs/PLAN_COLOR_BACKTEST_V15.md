# Color-Recommendation Backtest — Rigorous, Non-Circular Design (V15)

**Status:** built 2026-06-02. Replaces the circular `color_emotion_gt` / `color_va_gt`.

## 1. The problem with the old backtest

The old color ground truth defined a song as *relevant to a colour* iff its `song_va`
was within θ=0.25 (Euclidean) of the colour's V-A — where the colour's V-A came from the
engine's own `hsl_to_va()`, and the ranker scores songs by **that same** V-A distance.

```
colour --hsl_to_va()--> (V,A) --rank by Euclid dist to song_va--> songs
GT: "relevant" = song_va within θ of the SAME (V,A)      ← same quantity
```

Consequences (confirmed in `iter_10_color_accuracy`):
- **Tautology** — optimising V-A trivially maximises a score *made of* V-A → NDCG/P/mAP = **1.0000**.
- **Saturation** — θ=0.25 marks **3,386/5,548 (61%)** of the catalog "relevant" per colour.
- The code itself tagged this GT `engine-derived` / "tautology risk"; `PLAN_BACKTEST_METRICS.md`
  already ruled "NDCG/P/R with V-A as GT → ❌ tautology."

**Tightening θ does not fix it** — it only reduces saturation; the answer key is still the
ranker's own signal. The fix is a ground truth from **outside** the ranker's V-A pipeline
(`song_va`, `song_emotion_vec` from album-art colour, `hsl_to_va`).

## 2. Design principle

> A signal must never grade itself. Every ground truth here comes from a source the ranker
> does not use, so agreement is evidence, not arithmetic.

We decompose the pipeline `colour → mood → songs` and validate each link with the
appropriate external standard, plus an end-to-end and a discriminant test.

## 3. Three layers

### L1 — Bridge fidelity (`tools/color_bridge_metrics.py`)
*Does `colour → emotion` match humans?*
- **GT (external):** International Colour-Emotion Association Survey (ICEAS / Jonauskaite
  et al. 2020, *Psychological Science*; OSF `2w6gh`, CC-BY 4.0). 8,615 participants/colour,
  37 nations, 12 colour terms × 20 Geneva-Emotion-Wheel concepts.
  Aggregated in `ground_truth/color_norms.py` to a per-colour human V-A (GEW emotion
  ratings × circumplex coords) and a distinctive 8-emotion profile.
- **Metric:** Pearson/Spearman + RMSE between engine `hsl_to_va()` and human V-A
  (valence & arousal separately), bootstrap-CI over the 12 colours; 8-emotion cosine; mood top-1.
- **Why non-circular:** the answer key is human ratings collected with zero knowledge of Brightify.

### L2 — End-to-end retrieval (`tools/color_retrieval_metrics.py`)
*Given the colour's true (human) mood, does retrieval return mood-appropriate songs?*
Two independent GTs, reported separately and for consensus:
- **L2a editorial** (`color_editorial_gt.py`, validity=**external**): crawl YouTube Music
  MOOD playlists (buồn/vui/sôi động/chill/lãng mạn…), assign each catalog song the mood(s)
  of the playlists it appears in (human curation). A colour's relevant set = songs whose
  mood-set contains the colour's human `target_mood`. Sparse → recall is conservative.
- **L2b LLM-judge** (`color_llm_gt.py`, validity=**semi-independent**): qwen3:8b rates each
  pooled song's fit to the colour's human mood (0–3) from **lyrics only** — never the
  engine's colour math. TREC-pooled (production top-20 ∪ random negatives); P@10 is the
  honest headline, recall/NDCG pool-limited.
- **Metric:** NDCG@10 / P@10 / Recall@10 / mAP@10 / MRR + bootstrap-CI over colours, vs a
  baseline (random-over-catalog for editorial; random-within-pool for LLM). **Scores can and
  should be < 1** — that's the point.

### L3 — Discriminant validity (`tools/color_discriminant_metrics.py`)
*Do OPPOSITE colours recommend mood-separated songs?* (hardest to game)
- Antonym colour pairs chosen by **human** V-A separation (`discriminant_pairs()`).
- Production top-K for each colour; each recommended song scored on an independent common
  mood axis: `judge(song, mood_A) − judge(song, mood_B)` (qwen3, lyrics only).
- **Stats:** Cohen's d, rank-AUC, permutation p. `separated` iff d>0.3 & p<0.05.
- **Why it matters:** V-A self-consistency cannot fake separation on an axis the ranker
  never sees. If red-recs and blue-recs are mood-indistinguishable, the feature is inert.

## 4. Query colours ↔ target moods

The 12 ICEAS colours, each anchored to a `target_mood` derived from the **human** distinctive
emotion profile (positivity baseline removed by per-emotion cross-colour normalisation —
otherwise every colour collapses to happy/excited). Derivation lives in `color_norms.py`;
moods are read live from the survey, never hand-typed.

## 5. Validity labels (carried into every report)
- `external` — human source outside any model (ICEAS norms, editorial playlists).
- `semi-independent` — independent model/annotator that shares a modality with the ranker
  (LLM judge reads lyrics; production v4 valence is also LLM-from-lyrics) → use for relative
  separation, not as absolute truth.
- `engine-derived` — V-A/quadrant. **Never** used for ranking here (that was the old bug).

## 6. Known caveats (state them at defense)
- ICEAS used colour *terms*, not patches → terms mapped to canonical sRGB hex.
- GEW→V-A coords and GEW→8-label grouping are literature-based choices (Russell/Scherer);
  documented in `color_norms.py`, affect absolute mood labels but not the V-A rank-correlation.
- LLM-judge & editorial share the lyrics modality with the ranker's valence signal → L2b/L3
  are `semi-independent`; L1 (vs ICEAS) and L2a (vs playlists) are the fully-external anchors.
- Editorial EDM/remix mood coverage is thin (catalog is vocal pop) → lean on LLM-judge there.

## 7. Reproduce
```bash
# data (once): ICEAS raw survey
curl -L https://osf.io/download/5urwh/ -o data/external/color_norms/jonauskaite_ICEAS_raw.csv

python -m tools.color_bridge_metrics                                   # L1
python -m tools.backtest_v2.ground_truth.color_editorial_gt           # L2a GT (network)
python -m tools.backtest_v2.ground_truth.color_llm_gt 20 20           # L2b GT (qwen3, offline)
python -m tools.color_retrieval_metrics                                # L2
python -m tools.color_discriminant_metrics 4 15                        # L3 (qwen3)
```
Reports → `var/runtime/backtest/reports/color_*_metrics.json`.

## 8. Applied improvements P1+P2 (2026-06-02)

The backtest above was used as the gate for two grounded fixes in
`core/advanced_color_mapping.py` (the colour→V-A→emotion bridge L1 flagged as weak):

- **P1 — valence recalibration.** Old `valence = 0.52·L + 0.48·yellowness` ignored chroma
  and made blue/purple too negative, grey too positive. Refit on the 12 ICEAS colours →
  chromatic `0.05 + 0.40·L + 0.55·S − 0.19·redness`, achromatic `0.20 + 0.41·L`. Arousal
  (already good, r=0.64) untouched.
- **P2 — empirical emotion.** Replaced the synthetic Russell-centroid Gaussian (matched
  humans only 1/12) with inverse-distance interpolation over an embedded 12-colour ICEAS
  distinctive-emotion table (`_ICEAS_EMOTION`).

| metric (GT) | before | after |
|---|---|---|
| L1 valence Pearson (LOO-CV, honest) | 0.26 | **0.77** |
| L1 valence Pearson (in-sample) | 0.26 | 0.92 |
| L2-LLM P@10 (independent judge) | 0.74 | **0.86** |
| L2-LLM graded relevance /3 | 2.16 | **2.52** |
| L3 discriminant Cohen's d range | 0.98–3.80 | **4.03–4.51** |
| smoke test | 21/21 | 21/21 |

**Methodological lesson (state at defense):** after changing the engine, the LLM-judge GT
pool was STALE — new recommendations fell outside the old judged pool and scored a false
P@10=0.05. The fix is to RE-JUDGE the new recommendations (the judge cache is keyed by
(colour, song), so only new songs are judged) before comparing. Relevance is intrinsic to
(colour, song), so judgements are reusable; only coverage must be refreshed.

**Honesty note:** because P1/P2 are fit to ICEAS, L1 is now in-sample (cite the LOO-CV 0.77,
and the emotion top-1=1.0 is a lookup, not evidence). The out-of-sample proof that the fix
helped is L2-LLM and L3, whose ground truths are independent of ICEAS — both improved.
