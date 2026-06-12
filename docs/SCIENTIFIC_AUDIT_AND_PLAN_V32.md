# Scientific Audit & Upgrade Plan V32 — recommend-by-color & recommend-by-song

**Date:** 2026-06-12
**Scope:** Audit every building block of the two core features against published science + check what is actually backtested with offline metrics. Then research the weak points and propose a constraint-respecting upgrade plan.
**Hard constraints (from product owner):** no user/behavioural data; no model fine-tuning; LLM allowed for *backtesting only*, never in the serving path.

> **Key framing — "no fine-tune" vs linear probe.** Everything served is from *frozen* pretrained models (MERT, VN-SBERT) + published coefficients (Oklab/Jonauskaite) + lexicons. The DEAM→V-A probes are **Ridge linear heads on frozen embeddings** — the representation is never trained, so this is within "no fine-tune" (it is the standard linear-probe protocol, MARBLE 2023). This plan keeps that invariant.

---

## 1. Verdict (one line each)

- **recommend-by-color:** Architecture is **scientifically sound and mostly grounded**. After V31 (rank-space matching) the matching layer is correct and beats all baselines 12/12 (FDR-sig). Two real gaps: the color→V-A fit rests on **n=12** centroids, and it inherits the **song-V-A label** weaknesses below.
- **recommend-by-song:** Audio core (MERT multilayer, 0.82 weight) is **well-grounded and intrinsically validated**, but the whole stack rests on **cross-corpus transfer (Western→Vietnamese) that is acknowledged but never measured**, and weight tuning is validated only by **self-consistency + a single sub-0.70-accuracy LLM judge**.

**Bottom line:** the *designs* are defensible and unusually careful (baselines, FDR, non-circular tests already exist). The gaps are about **external validation**, not wrong architecture. Four systemic weaknesses (§3) are the real work.

---

## 2. Building-block audit

### 2A. recommend-by-color

| Block | Scientific basis | Validated? | Backtest metric | Gap |
|---|---|---|---|---|
| color→V-A (Oklab ridge on ICEAS) | Ottosson 2020 (Oklab); Jonauskaite 2020 (n=4598, 30 nations) | LOO-CV r=0.873 (valence) **in-sample on 12 centroids** | `phase3_cielab_experiment.py`; Fisher-z CI in `color_eval_rigor` | **n=12** → wide CI; VN-specific not validated (acknowledged) |
| V31 rank-space matching | Quantile/CDF matching; Music2Palette 2025 (rank-aligned emotion space) | **Yes** — TE=0.024, beats random/pop/val-only/aro-only **12/12 FDR-sig**, within 26% of oracle | `color_eval_rigor.py` (match space) | TE is self-referential vs the same labels (Dacrema 2021: offline↔online r≈.28) |
| journey (Iso-Principle) | Starcke 2024 (d=0.52); Saari 2016 (10–15%/step) | Yes — KS≈0.18, mean_t≈0.50 | `color_eval_rigor` journey block | — |
| diversity (MMR in V-A) | Carbonell & Goldstein 1998 | Yes — ILD 0.032–0.039 all colors | `color_eval_rigor` ILD | now redundant w/ rank space (harmless) |
| **song V-A labels** | see §2C | **partial** | shared dependency | **inherits all §2C gaps** |

### 2B. recommend-by-song

| Signal | Weight | Basis | Validated? | Gap |
|---|---|---|---|---|
| MERT multilayer (mean L1–12, frozen `MERT-v1-95M`, 24kHz) | **0.82** | MERT (arXiv 2306.00107); MARBLE benchmark (2306.10548) | multilayer > single on 3 intrinsic metrics (Sym +0.040) | **Western-trained domain gap on VN unmeasured** (arXiv 2506.17055); mean-of-all-layers is a default, not task-optimal (MARBLE: per-task layers differ) |
| V-A RBF (σ_V=0.22, σ_A=0.14, heteroscedastic) | 0.12 | Delbouys 2018; Eerola 2026 (A r=.81>V r=.67) | gate-accepted (`e_va_split.py`) | depends on label quality (§2C) |
| Lyrics VN-SBERT cosine | 0.06 | `dangvantuan/vietnamese-embedding` (frozen) | anisotropy fixed (avg-cos 0.856→0.544) | weight in "dead zone"; effect marginal |
| timbral/rhythmic/tonal | 0 | Berenzweig 2004 | correctly **disabled** (Essentia 44.1kHz degenerate) | — |
| instrument-tag (slot 5) | 0 | MTG-Jamendo | failed experiment (redundant w/ MERT) | matrix built but never read (orphan) |
| mood one-hot (slot 6) | 0 | McFee 2011 | ablated (no discriminative power) | — |
| **weights [0.82/0.12/0.06]** | — | sensitivity + 5-fold CV + SLSQP | **near-optimal** (SLSQP Δ=+0.011, CI incl. 0) | tuned on **single LLM judge** GT (qwen3:8b, acc<0.70; PoLL 2nd judge degenerate) + self-consistency only |

### 2C. Shared V-A label pipeline (the critical shared dependency)

| Component | Basis | Validated against | Number | Gap severity |
|---|---|---|---|---|
| Arousal = 0.80·MERT-DEAM-probe + 0.20·NRC-VAD | DEAM (1802 Western); NRC-VAD | DEAM 5-fold CV | **R²≈0.58 (in-domain DEAM)** | 🔴 transfer to VN unmeasured; cited 40–60% drop risk |
| Valence (v6c) = VN emotion lexicon (rank) | Russell circumplex; hand-curated 500+ words | **Gemini v5d only** | ρ=0.475 | 🔴 reference is a single LLM; **circular** |
| Valence audio fallback = MERT-DEAM-probe (layer 9) | DEAM | DEAM CV + ρ≥0.40 vs Gemini | R²=0.502 | 🔴 gate vs Gemini = circular |
| VN lexicon category→V-A coordinates | Russell circumplex (manual) | **nothing** | hand-coded | 🟠 e.g. `angry=(0.3,0.8)` undocumented |

---

## 3. Four systemic weaknesses (the actual problems)

1. **🔴 Circular valence validation.** v6c valence is validated by agreement with Gemini v5d, and the MERT-valence gate is also "ρ≥0.40 vs Gemini". Gemini is a single LLM's opinion, not independent ground truth. There is currently **no validation signal independent of one LLM**.

2. **🔴 Cross-corpus transfer never measured.** Every probe is trained+CV'd on DEAM (Western). The literature warns transfer can collapse (EmoMusic→WCMED R²=−0.84, worse than random; `VA_NO_LLM_REDESIGN_V6.md:24`). The actual VN number is **"unknown"**, not "good".

3. **🔴 Single weak LLM judge.** The similar-song relevance GT (NDCG=0.437) and SLSQP weights depend on qwen3:8b (acc<0.70 in specialized domains, arXiv 2506.13639); the intended PoLL 2nd judge (gemma2:2b) was degenerate (κ≈0). Literature: a **jury of diverse judges** beats a single strong one when threshold reliability matters (PoLL).

4. **🟠 Hand-coded lexicon coordinates.** The 13 emotion-category V-A coordinates are assigned by hand with no cited source — and no published Vietnamese ANEW-equivalent (continuous VAD word norms) exists (confirmed by search). VnEmoLex (Zenodo 801610, 12,795 words) and NRC-VAD v2 (arXiv 2503.23547, 55k terms, multilingual) are the closest published anchors.

---

## 4. Research findings that unlock fixes

- **Convergent validity is the right tool when no ground truth exists.** With no user data and no VN gold set, the strongest scientific claim available is *triangulation*: if multiple **independent** signals agree, the construct is real. We currently have 2 signals (lexicon, MERT-audio) + 1 LLM reference. Adding independent signals turns "circular" into "convergent".
- **Multilingual V-A text regressor** ("Quantifying Valence and Arousal in Text with Multilingual Pre-trained Transformers", arXiv 2302.14021) — a *pretrained* (frozen, zero-shot) model that emits continuous V-A for text in many languages. An **independent** valence signal that is not Gemini and not the hand lexicon.
- **NRC-VAD v2** (arXiv 2503.23547) + **VnEmoLex** (Zenodo 801610) — published anchors to ground the lexicon coordinates with citable, reproducible values.
- **PoLL / jury judging** (panel of diverse LLMs, report Krippendorff α) — the fix for weakness #3; LLM-as-backtest only, fully within constraints.
- **MARBLE** (arXiv 2306.10548) — task-specific MERT layer selection beats mean-of-all-layers; supports re-checking the V-A probe layer (already saw layer 9 > all-layers).
- **MERT non-Western gap** (arXiv 2506.17055) — confirms domain gap is real and must be measured, not assumed.

Sources: [MERT](https://arxiv.org/pdf/2306.00107v2) · [MARBLE](https://arxiv.org/pdf/2306.10548) · [Multilingual V-A text](https://arxiv.org/pdf/2302.14021) · [NRC-VAD v2](https://arxiv.org/abs/2503.23547) · [VnEmoLex](https://zenodo.org/records/801610) · [LLM-judge design](https://arxiv.org/html/2506.13639v1) · [Music2Palette](https://arxiv.org/html/2507.04758v2) · [Chinese VAD norms](https://link.springer.com/article/10.3758/s13428-021-01607-4)

---

## 5. Upgrade plan (prioritized, constraint-respecting)

### Tier 0 — Lock the current baseline (do first)
- Commit V31 + v6c. Re-run `color_eval_rigor` + `eval_similar_intrinsic` + `similar_llm_metrics`; snapshot all numbers to `docs/BASELINE_V32_METRICS.md`. Nothing below is trustworthy without a frozen reference point.

### Tier 1 — Break circularity via convergent validity (highest scientific ROI) 🔴
- **P1.1 Independent valence signal.** Run the frozen multilingual V-A text transformer (arXiv 2302.14021) on VN lyrics → `data/mlva_valence.json`. Compute the **3-way convergent matrix**: VN-lexicon-V × multilingual-transformer-V × MERT-audio-V (pairwise ρ + 1-factor PARAFAC/PCA loading). **Gate:** ≥2 of 3 signals load >0.5 on a common factor → valence construct is corroborated *without any LLM*. Replaces "ρ vs Gemini" as the headline validity claim.
- **P1.2 Ground the lexicon coordinates (v6d).** Re-derive the 13 category V-A coordinates by aggregating NRC-VAD v2 / VnEmoLex word scores per category (citable, reproducible) instead of hand numbers. Backtest: does v6d move TE / convergent-ρ vs v6c? Ship only if non-regressing.

### Tier 2 — Measure cross-corpus transfer (kill the biggest "unknown") 🔴
- **P2.1 VN V-A silver set via LLM *panel*.** Use a **PoLL of ≥3 heterogeneous models** (e.g. Gemini + qwen3 + one more; Gemini allowed = backtest only) to rate ~200 stratified VN songs (balanced across V-A quadrants) on V-A from lyrics+metadata. Aggregate with median; report Krippendorff α; discard items with α below threshold. → `data/va_silver_vn_v1.json`.
- **P2.2 Finally compute transfer.** Measure DEAM-probe arousal/valence R²/ρ **against the VN silver set**. Replaces "unknown" with a real number + CI. If R² collapses, P1.1's convergent signals become the primary labels.

### Tier 3 — Fix the similar-song judge (weakness #3) 🔴
- **P3.1 Replace single judge with PoLL panel** in `similar_llm_metrics.py` / `tune_musical_weights.py`; report inter-judge Krippendorff α; recompute NDCG + bootstrap CI. Re-validate weights — keep only gates that survive panel agreement.
- **P3.2** Keep the existing non-circular discriminant test (`similar_discriminant_metrics.py`, Russell-opposite pairs) as a permanent regression gate.

### Tier 4 — Color bridge robustness (weakness in §2A) 🟠
- **P4.1** Report the n=12 limitation honestly; if Jonauskaite item-level data is reachable, refit Oklab→V-A on more points with bootstrap CI. Revisit the VN red-positivity overlay (gate-rejected before) using P1.2's grounded data.

### Tier 5 — Honesty layer
- Annotate each served component in `config.py` with `# VALIDATED: <metric>` vs `# PLAUSIBLE-UNVALIDATED`. Keep the "what is NOT validated" block current (it already exists — good practice).

### Explicitly NOT in scope (constraint compliance)
- ❌ Metric-learning head / fine-tuning MERT (needs labels → would put LLM/labels in serving).
- ❌ Collaborative filtering / click models (user data).
- ❌ Any LLM call in the request path.

---

## 6. Suggested order & gates

1. **Tier 0** (commit + snapshot) — 1 session.
2. **P1.1** (convergent valence) — highest ROI, no new data collection, frozen model only.
3. **P2.1 + P2.2** (VN silver set + transfer number) — the most important *honesty* fix.
4. **P3.1** (judge panel) — makes every similar-song weight claim trustworthy.
5. **P1.2 / P4.1** — refinements, ship only if non-regressing on the frozen baseline.

Every step gates on: **must not regress the Tier-0 baseline** (TE, intrinsic metrics) and **must improve at least one independent/convergent validity number**.

---

# V32 RESULTS (executed 2026-06-12) — OpenAI key enabled, all phases done

**Total OpenAI spend ≈ $1.36** (budget $4). Serving path remains LLM-free (verified — GPT used only offline). New tools: `build_va_reference_gpt.py`, `va_convergent_validity.py`, `build_v6d_labels.py`. GPT-judge + GT-file-override added to `similar_musical_gt.py` and `color_llm_gt.py`. Pre-existing stale-constant bug fixed in `color_baseline_eval.py` (`COLOR_SCORE_VA_SIGMA`→`_V`/`_A`).

## How each of the 4 weaknesses was resolved

### W1 — Circular valence validation → BROKEN via convergent + independent agreement
- Built GPT V-A reference (gpt-4o-mini, full catalog, $0.60). **Reliability: test-retest ICC valence 0.991 / arousal 0.965; cross-model vs gpt-4o ρ 0.92 / 0.77.** GPT↔Gemini agree ρ=0.838 → two independent vendors corroborate.
- Convergent validity (`va_convergent_validity.py`): valence signals VN-lex/MERT/GPT all load >0.5 on a common factor (3/3); VN-lex~GPT ρ=0.48.
- v6d valence (CV-tuned to GPT) agrees better with the **independent** Gemini reference (NOT the tuning target): **0.468 → 0.579**. The improvement generalizes → not overfit.

### W2 — Cross-corpus transfer unmeasured → MEASURED
DEAM-trained MERT probe vs GPT reference on Vietnamese songs:
- **Valence R² = 0.063** (r=0.25) — weak. Served valence rightly leans on the VN lexicon, not the audio probe.
- **Arousal R² = 0.209** (r=0.46) — moderate; arousal is more audio-universal. Arousal kept acoustic.

### W3 — Single weak judge (qwen3 acc<0.70) → replaced with GPT
Built GPT musical GT (50 seeds, 998 judgments). Re-validated weights via SLSQP + paired bootstrap: current `[MERT 0.82/VA 0.12/lyrics 0.06]` vs optimum `[0.826/0.119/0.056]`, **ΔNDCG=+0.008 CI95=[−0.0002, +0.018] → not significant → weights UNCHANGED, now confirmed near-optimal on a stronger judge.**

### W4 — Hand-coded lexicon coords → partially addressed
v6d re-tunes the valence *blend* (VN-lex vs MERT) against GPT via 5-fold CV. Re-deriving the 13 category coordinates from NRC-VAD remains a documented future ablation (the blend re-tune captured most of the available agreement gain).

## Shipped change: v6c → v6d labels (config.RELABELED_EMOTIONS_FILE)
- VALENCE = 0.7·rank(VN-lexicon) + 0.3·rank(MERT-valence) — 5-fold-CV-selected to maximize GPT agreement, then FROZEN. Serving LLM-free.
- AROUSAL = inherit v6a MERT-acoustic, UNCHANGED. **Rationale: GPT judges from lyrics only → strong valence ref, weak arousal ref (arousal is acoustic, r≈.81 audio). Do not pull arousal toward a lyrics-only signal.**

## Before/after (frozen baseline → v6d)
| Metric | v6c (baseline) | v6d (shipped) |
|---|---|---|
| Valence ρ vs GPT (tuning target) | 0.479 | 0.513 |
| Valence ρ vs Gemini (independent) | 0.468 | **0.579** |
| Color TE (Euclidean) | 0.0238 | 0.0236 |
| Color FDR vs baselines | 12/12 sig | 12/12 sig |
| Color Qprec (baseline_eval) | — | 0.92 |
| Negative-control Qprec gap (real−shuffled) | — | +0.67 (discriminative) |
| Color NDCG@10 vs independent GPT color-GT | — | 0.462 vs 0.363 random |
| Similar-song NDCG@10 (GPT musical GT) | — | 0.391 (near-optimal, weights unchanged) |
| Colours distinct (max pairwise Jaccard) | 0.00 | 0.00 |

## The r(V,A) finding (important nuance, documented honestly)
v6d r(V,A)=0.49 "fails" the construct-validity orthogonality target (≤0.20) — **but that target is wrong for this corpus.** GPT (0.515) AND Gemini (0.313) independently show a real positive V-A correlation in Vietnamese pop; v6c's 0.18 was an artifact of independently rank-calibrating each axis. Honest caveat: correlated V-A means off-diagonal colour quadrants (peaceful, intense) have thinner catalog support — a **catalog property + future data-collection target**, not a labeling bug. (Minor: GPT lyrics-only may slightly inflate its r(V,A); arousal kept acoustic to preserve the real sad-lyrics-but-energetic-music decoupling.)

## What is NOW validated vs still open
VALIDATED: GPT reference reliability (ICC 0.99); valence convergent + cross-independent-reference agreement; cross-corpus transfer quantified; similar-song weights near-optimal on a strong judge; color targeting beats baselines on TE + an independent GPT color-GT + negative control.
STILL OPEN (honest): cross-corpus valence transfer is genuinely weak (R²=0.06) — a corpus limitation, not fixable without VN-native audio labels; n=12 colour bridge CI wide; off-diagonal quadrant sparsity; no true human listening study (offline↔online r≈.28, Dacrema 2021).

---

# V6e (2026-06-12) — valence from a lyrics-dominant ensemble (B+C+D)

**Prompt:** product owner — "arousal from audio is fine, but valence should come from lyrics." Correct per Hu & Downie 2010 / Delbouys 2018. v6d's 0.3 audio weight was suspected to be compensating for a weak bag-of-words lexicon.

## What changed
- **Fixed the lexicon negation bug** (`core/emotion_analysis.py`): old `count *= -0.8` produced negative scores that corrupted normalization; now per-occurrence, clause-scoped negation that FLIPS valence to the opposite pole ("không buồn"→positive), plus adversative recency ("buồn **nhưng** hạnh phúc"→hạnh phúc dominates). Fast substring guard keeps it ~9s/catalog.
- **Added 2 independent context-aware lyrical signals**: a frozen pretrained VN-sentiment transformer (`wonrax/phobert-base-vietnamese-sentiment`, zero-shot, polarity→valence, `tools/extract_vn_sentiment.py`) and the EmoBank→XLM-R cross-lingual probe.
- **v6e valence** = NNLS blend of {vn_lex, vn_sent, emobank, mert} fit to the GPT reference, frozen (`tools/build_v6e_labels.py`). Serving stays LLM-free.

## Convergent validity (lyrical signals vs references)
| signal | ρ vs GPT | ρ vs Gemini |
|---|---|---|
| vn_lexicon (fixed) | 0.491 | 0.470 |
| VN-sentiment transformer | 0.549 | 0.455 |
| EmoBank→XLM-R probe | 0.575 | 0.441 |
| MERT-valence (audio) | 0.262 | **0.468** |
Pairwise lyrical ρ 0.34–0.43 → independent, not redundant.

## The decisive test (did audio→0?) — NO, and the data says why
NNLS weights: vn_lex 0.20 / vn_sent 0.28 / emobank 0.36 / **mert 0.16** / nrc 0.0. The pure-lyrical ablation (drop mert) **lowers independent-Gemini agreement 0.651→0.581** (≈ v6d). So audio (mode/brightness) carries **real complementary, variance-reducing valence signal** (MERT-valence ρ vs Gemini=0.468) — it is not overfitting (the loss is on the reference we did NOT tune to). **Conclusion: valence should be *primarily* lyrical (84%), not *purely* lyrical.** The product owner's intuition is right in direction; the data refines the magnitude.

## Result (v6e ADOPTED — beats v6d on every axis)
| Metric | v6d | v6e |
|---|---|---|
| valence ρ vs GPT | 0.513 | **0.718** |
| valence ρ vs Gemini (independent) | 0.579 | **0.651** |
| color TE | 0.0236 | **0.0232** |
| r(V,A) | 0.49 | **0.31** (matches Gemini's true 0.31) |
| color ordering_all_pass | False | **True** |
| FDR vs baselines | 12/12 | 12/12 |
| colours distinct (Jaccard) | 0 | 0 |

Arousal unchanged (v6a MERT-acoustic). A strict **pure-lyrical** variant exists (drop mert → Gemini 0.581 ≈ v6d) if methodological purity is preferred over the +0.07 independent-agreement gain.

---

# V6f (2026-06-12) — arousal validated/completed with the tempo facet (no humans)

**Goal:** validate AROUSAL — the axis no prior judge could test (GPT/Gemini are lyrics-only; arousal is acoustic). Done without a new human study by reusing **DEAM human V-A labels** to ground the model. Gemini-audio judge was planned but the **Gemini key is dead (401)** → degraded cleanly to fully-local references (the plan anticipated this).

## Diagnosis (the finding)
A clean librosa-downbeat BPM (`tools/extract_clean_bpm.py`, mean 121, ρ=0.55 vs Essentia tempo) revealed: v6e/MERT-arousal tracks **loudness (ρ=0.33) and energy (ρ=0.43)** but **tempo not at all (ρ=0.005)** — and in this catalog **tempo ⟂ loudness (ρ=−0.02)**. So arousal captured only the energy facet and missed the orthogonal **tempo** facet (Eerola: arousal = tempo + loudness + spectral energy). The old construct-gate failure ρ(A,tempo)=−0.03 was **both** a degenerate Essentia tempo column AND a genuinely tempo-blind arousal.

## Fix (DEAM-human-grounded, scale-free, transferable)
`tools/build_v6f_labels.py`: arousal = rank-space NNLS blend of **[MERT-arousal, clean-BPM, loudness]**, weights fit on **DEAM human arousal** (rank features → unit/scale-invariant cross-corpus transfer; MuQ dropped as redundant — it would also miss tempo). Weights: **MERT 0.67 / loudness 0.18 / tempo 0.15**. Valence = v6e UNCHANGED.

## Result (v6f ADOPTED)
| Metric | v6e | v6f |
|---|---|---|
| DEAM human-CV ρ (blend vs MERT-only) | 0.625 | **0.647** |
| ρ(arousal, clean-tempo) on VN | 0.005 | **0.180** |
| ρ(arousal, loudness) on VN | 0.33 | **0.52** |
| color TE | 0.0232 | **0.0227** |
| color ordering / FDR | pass / 12/12 | pass / 12/12 |
| colours distinct (Jaccard) | 0 | 0 |

Arousal now reflects **both** acoustic determinants. Honest caveat: ρ(A,tempo)=0.18 is just under the 0.20 construct heuristic — kept the DEAM-grounded weight rather than inflate tempo to game the metric.

## Arousal validation status — closed as far as possible without humans
- **Human-grounded**: model fit + CV'd on DEAM **human** arousal (ρ=0.647).
- **Construct**: now tracks tempo (0.18) AND loudness (0.52) — its two literature determinants.
- **Residual ceiling**: no VN-native human arousal labels; DEAM is Western (transfer honest via low-dim universal features). An *ears-on* multimodal judge (Gemini-audio) remains the next proxy if/when a working key exists — it would send copyrighted clips externally, so it stays optional.

## Current label lineage (active = v6f)
valence ← v6e lyrics-dominant ensemble (negation-fixed lexicon + VN-sentiment transformer + EmoBank probe + 16% MERT); arousal ← v6f DEAM-grounded [MERT + tempo + loudness]. Serving LLM-free throughout.

---

# V33 (2026-06-12) — colour AROUSAL re-grounded to ICEAS research norms

**Prompt:** product owner — colour energy felt wrong (pink/moon too energetic; etc.); asked to make ALL colours match the science.

**Finding:** verified the chain is bug-free (consistent hex→V-A→rank-match; distinct colours, Jaccard 0). The issue was scientific: comparing every colour's `hsl_to_va` to the **ICEAS/Jonauskaite human V-A norms**, **valence matched (r=0.969, mean|err|=0.051)** because it was regression-fit to ICEAS, but **arousal did NOT (r=0.765, mean|err|=0.154)** because it used an un-fit Whiteford formula — systematically too high for warm/saturated colours (Hồng 0.80 vs research 0.48; Nâu/Cam/Đỏ/Vàng +0.19…+0.33) and too low for light/dark (Trắng −0.15, Ngọc −0.14).

**Fix (`tools/fit_arousal_oklab.py`, `COLOR_AROUSAL_ICEAS_FIT`):** ridge-fit arousal to the ICEAS arousal norms on the literature determinants **[redness, saturation, darkness]** (Whiteford/Wilms-Oberfeld), 3 params (LOO-CV; the 6-feat Oklab basis overfit at r=0.35). Coeffs `0.226 + 0.172·redness + 0.087·sat + 0.221·darkness`. Now BOTH axes are research-fit, symmetric with valence.

**Result:** arousal mean|err| vs ICEAS **0.154→0.053** (≈ valence's 0.051); Hồng 0.80→0.51 (research 0.48), Trắng 0.17→0.33 (0.32), warm colours pulled down to the norms. Colour gate: **TE 0.0227→0.0216** (better targeting), valence L1 r=0.969, arousal L1 r=0.783, journey passes, beats baselines. Frontend `colors.ts` regenerated; Hồng label "Phấn khích"→"Dịu dàng" to match its corrected mid-arousal.

**Honest caveat:** n=12 ICEAS limits fit precision (Brown remains a +0.18 outlier — dark-warm); arousal now follows research even where it diverges from naive intuition (e.g. ICEAS rates **black 0.58 = moderately arousing/heavy**, not calm-slow). Colour→V-A is now research-grounded on **both** axes.

---

# V34 (2026-06-12) — evaluated Valdez-Mehrabian large-sample colour→V-A; KEPT V33

**Prompt:** research more so colour→V-A is complete/accurate for ALL colours (n=12 limit).

**Research:** the foundational large-sample equations — **Valdez & Mehrabian 1994** (~76 Munsell colours): Arousal = 0.60·Saturation − 0.31·Brightness, Pleasure = 0.69·B + 0.22·S; **Wilms-Oberfeld 2018** (30 colours): + secondary hue (arousal blue→green→red). Both agree **saturation is the dominant arousal driver** — whereas the V33 ICEAS-12 fit gave saturation only 0.087 (a **collinearity artifact**: 12 confounded colours can't isolate saturation).

**Test (`tools/color_va_model_compare.py`):** a saturation-sweep grid showed V33 arousal rises with saturation ONLY for red, staying flat for saturated **green/blue** (wrong); VM rises correctly for all hues. So VM is structurally right for the *full colour space*.

**BUT — decision: KEEP V33, VM default OFF.** The picker serves only the **12 fixed ICEAS colours**, and for those V33 is MORE accurate: mae vs ICEAS **0.053 < VM 0.082**, colour **TE 0.0216 < VM 0.0229**, ICEAS-arousal **r 0.78 > VM 0.58**. VM's saturation-fix only helps *arbitrary* colours between anchors — which the product never serves. Adopting VM would regress the real product for a moot benefit. VM is kept as a gated, documented alternative (`COLOR_VA_VALDEZ`) if free colour choice is ever added.

**Net:** confirmed the shipped V33 colour→V-A is the more accurate choice for the 12 colours in use, by triangulating against the largest published colour-emotion study. No behaviour change. Honest caveat unchanged: ICEAS/VM are Western-leaning; n=12 caps anchor precision (Brown outlier).
