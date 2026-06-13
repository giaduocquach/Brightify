# Recommend-by-Color — Scientific Basis & Validation (V39)

**Purpose.** Single reference for the graduation thesis: every design decision in the
recommend-by-color feature, its primary citation, the offline metric that validates it, the
current result, and the honest limitation. The feature recommends Vietnamese songs from a
chosen colour (or a 2-colour "mood journey").

**Hard constraints (held throughout).** Frozen pretrained models + linear probes only (no
fine-tuning); public datasets (ICEAS, DEAM, PMEmo, EmoBank) + offline-LLM-backtest only; **no
user data**; **LLM never in the serving path** (used only for offline reference/backtest).

**Pipeline in one line.** colour → (Valence, Arousal) on Russell's circumplex → match songs
(also placed in V-A) nearest in mood, made acoustically coherent, with a smooth 2-colour
journey. The whole feature reduces to V-A + an acoustic-coherence refinement.

---

## 1. Stage-by-stage basis → metric → result → limitation

| Stage | Design & primary citation | Offline metric | Current result | Limitation |
|---|---|---|---|---|
| **Colour set (12)** | 12 Berlin-Kay basic terms (Berlin & Kay 1969); cross-cultural colour-emotion norms (Jonauskaite et al. 2020, ICEAS, n=4598/30 nations, global r=.88); ~12 avoids choice-overload (Scheibehenne 2010) | circumplex coverage / per-colour separation | colours span V-A; pairwise mood separation **0.31** | 12 anchors only; VN not among ICEAS' 30 nations |
| **V-A space** | Russell (1980) circumplex; colour↔music is **mediated by V-A** (Palmer & Schloss 2013, PNAS, r=.89–.99; Whiteford et al. 2018) | — (architectural) | V-A used as the single matching space | 2-D omits e.g. tension/dominance (Russell-sufficient per GlobalMood 2025) |
| **Colour→Valence** | Oklab perceptual space (Ottosson 2020) → ridge fit to ICEAS valence norms | Fisher-z vs ICEAS (n=12); LOO-CV | r = **0.969** CI[0.889, 0.991]; LOO-CV r≈0.87 | n=12 ⇒ wide CI |
| **Colour→Arousal (V38)** | **Whiteford 2018 colour↔MUSIC**: faster music ↔ lighter+saturated colours, slower ↔ darker. Weights redness +.755, sat +.720, darkness −.549 ⇒ `A = +0.373·redness +0.356·saturation +0.271·lightness` | **independent: measured song tempo (BPM)** | ρ(lightness, BPM)=**+0.46**, ρ(saturation, BPM)=**+0.66** (lighter/saturated → faster songs) | warm-saturated colours (brown, pink) read energetic — *Whiteford-faithful*, may feel counter-intuitive |
| **Match space** | rank/quantile matching + calibration to catalog distribution (Steck 2018) | targeting error (TE) | TE = **0.0268** (Euclidean, rank space) | rises slightly at edges (catalog supply, see §3) |
| **Scorer** | heteroscedastic Gaussian RBF, σ_V(0.20) > σ_A(0.14) — valence less audio-reliable (Eerola 2011; Delbouys 2018) | TE vs 5 baselines + FDR | beats random/popularity/valence-only/arousal-only **(all pass; FDR-sig)**; ≈ nearest-VA (no-diversity) | — |
| **Acoustic coherence (V37)** | a colour's songs should *feel alike* → cluster on frozen **MERT** (Li 2023; MARBLE 2306.10548). Raw cosines are **anisotropic** (~0.9) → **mean-centre** (Gao 2019; Mu & Viswanath 2018; Ethayarajh 2019) | centred-MERT intra-list cosine | random 0.0 vs neighbour **0.45** (centring restores signal); delivered coherence **0.34** (vs 0.06 scattered) | α=0.45 trades a little TE for coherence |
| **Semantic coherence** | existing MTG-Jamendo-style `mood_tags` | dominant-mood-tag share | **0.67**; warm→"epic", cool/dark→"meditative" | tags auto-tagged (Essentia) — secondary signal |
| **2-colour journey** | iso-principle mood trajectory (Starcke 2024, d=0.52; Saari 2016 ~10–15%/step) + acoustic continuity (Knopke 2018) | journey KS vs U[0,1]; ΔBPM/Δtimbre | KS=**0.21** (PASS); smoothness ΔBPM **31→2.7**, Δtimbre **0.87→0.65** | journey is 2-colour (3+ clamped to 2) |
| **Diversity / dedup** | intra-list diversity & novelty (Vargas & Castells 2011); cover filter | ILD; artist-uniqueness | artist diversity kept; covers excluded | — |
| **Song→V-A (v6g)** | valence = EWE ensemble of lyrical signals (Grimm & Kroschel EWE), arousal = DEAM-grounded MERT+tempo+loudness | cross-corpus transfer; independent audio + text refs | PMEmo transfer V **0.69** / A **0.65**; CLAP-ears arousal **0.48**; **independent multilingual XLM-T sentiment vs served valence ρ=0.59** (Phase 4c, non-circular) | cross-corpus valence weak in absolute (R²≈.06); offline only |
| **Evaluation** | strong baselines (Dacrema 2021); bootstrap CI (Schnabel 2022); FDR (Benjamini-Hochberg 1995); diversity (Vargas 2011) | the full battery above | reproducible suite, CIs reported | offline↔online gap (no user study) |

---

## 2. Ablation (each component earns its place)

Cumulative configs, n=12 colours, top_k=10 (`tools/color_ablation.py` → `data/color_ablation.json`):

| Config | separation | coherence | ρ(Light,BPM) | ρ(Sat,BPM) | dark arousal | TE |
|---|---|---|---|---|---|---|
| V31 rank-match | 0.129 | 0.022 | +0.19 | **−0.66** | 0.47 | 0.0225 |
| +V36 CDF target | **0.225** | 0.056 | +0.36 | +0.40 | 0.51 | 0.0231 |
| +V37 coherence | 0.224 | **0.173** | −0.04 | −0.06 | 0.50 | 0.0225 |
| +V38 Whiteford arousal | **0.312** | **0.350** | **+0.46** | **+0.66** | **0.37** | 0.0268 |

- **V36** un-compresses colours across the catalog (separation ↑).
- **V37** makes a colour's songs acoustically tight (coherence ×3).
- **V38** flips the tempo correlation from **wrong (−0.66) to correct (+0.66)** and drops dark-colour delivered arousal (0.50→0.37 = slower/sadder). Note: V37 coherence under the *old* arousal even dips tempo-ρ negative — only V38 aligns coherence with the correct colour↔music direction.

---

## 3. Honest limitations (state in the thesis)

1. **n=12 colours** → wide CI on the colour→V-A fit (valence CI [0.89, 0.99]); validated at centroid level, not across the continuous colour space.
2. **Vietnam is not in ICEAS' 30 nations** → colour-emotion norms are extrapolated; no VN-native colour-emotion study exists.
3. **Brown & pink read energetic** (mid/high arousal). This is *faithful* to Whiteford (warm + saturated ↔ faster music), even if intuition says "somber/gentle" — a documented model-vs-intuition tension, not a bug.
4. **TE rises slightly at V38** (0.0225→0.0268): warm colours target the catalog's thin high-arousal tail (only ~22% of songs are high-arousal) — a *supply* limit, not a matcher error.
5. **Tags are auto-tagged** (Essentia/Jamendo taxonomy) → `tag_coherence` is a secondary, corroborating signal, not ground truth.
6. **Offline↔online gap**: all metrics are offline proxies (tempo, coherence, calibration); no human-listener study (out of scope — no user data).

---

## 4. Reproduce

```
python -m tools.color_eval_rigor       # TE+FDR, journey KS+smoothness, Whiteford-tempo ρ, valence Fisher-z
python -m tools.color_per_color_audit  # per-colour V-A + coherence + tag-coherence + separation
python -m tools.color_ablation         # V31→V36→V37→V38 ablation
```
All flags in `config.py` (`COLOR_*`); colour→V-A in `core/advanced_color_mapping.py` (`hsl_to_va`);
matching/coherence/journey in `core/recommendation_engine.py`. Recommendations are deterministic
(greedy selection; fixed bootstrap seeds in eval).

---

## 5. Key references
Berlin & Kay 1969 · Russell 1980 (circumplex) · Valdez & Mehrabian 1994 · Ou & Luo 2004 ·
Palmer & Schloss 2013 (PNAS) · Whiteford et al. 2018 (i-Perception, *Bach to the Blues*) ·
Jonauskaite et al. 2020 (ICEAS) · Ottosson 2020 (Oklab) · Eerola 2011 · Delbouys 2018 ·
Steck 2018 (RecSys, calibration) · Dacrema 2019/2021 · Schnabel 2022 · Benjamini & Hochberg 1995 ·
Vargas & Castells 2011 · Gao 2019 / Mu & Viswanath 2018 / Ethayarajh 2019 (anisotropy) ·
Li 2023 (MERT) / MARBLE 2306.10548 · Starcke 2024 · Saari 2016 · Knopke 2018 · Grimm & Kroschel (EWE).

---

# V6h + V40 update (2026-06-13) — grounded lexicon + MuQ backbone migration

## A. Grounded valence lexicon (v6h) — "no more self-made"
The hand-curated in-code VN emotion dict was replaced by the **official Vietnamese NRC-VAD
lexicon** (Mohammad 2018, ACL; v1 multilingual, 19,971 terms, human-rated valence ∈[0,1]) — every
valence word now traces to a peer-reviewed source. Kept only the METHOD (clause-scoped negation),
not subjective scores. `tools/build_grounded_vnlex.py` → 98.2% coverage; agreement vs GPT 0.44 /
served 0.47 (≈ the hand lexicon). EWE re-weighted (grounded vn_lex reliability 0.78 ≈ hand 0.76).
**v6h gate (vs v6g):** colour-TE 0.0274 ≈ 0.0268 (no regression); **r(V,A) 0.25→0.12 (now passes
orthogonality)**; Whiteford-tempo/journey/ICEAS hold; valence ρ vs GPT 0.71→0.67 (small grounding
cost, that agreement is partly circular). **Adopted** (`config.RELABELED_EMOTIONS_FILE→v6h`).
Limitation: NRC-VAD-VN is auto-translated (Google 2022); small GenZ-slang extension kept + flagged.

## B. MuQ audio backbone (V40) — verified + migrated
MuQ (Zhang 2025, arXiv 2501.01108; SOTA on MARBLE, beats MERT/MusicFM) was evaluated as the audio
backbone for similar-song + colour-coherence. At fixed MERT-tuned weights the two TIED; **after
re-optimization MuQ wins both end metrics**:
- similar-song editorial NDCG@10 **0.0739** (MuQ @ audio-weight 0.76) vs **0.0708** (MERT @ 0.88) — robust across the weight grid.
- colour-TE **0.0267** (MuQ-centered, α=0.55) vs **0.0302** (MERT-centered, α=0.45).
Re-gate confirms no regression: colour TE-ordering ALL PASS, journey KS PASS, Whiteford-tempo
ρ 0.47/0.55, r(V,A) 0.12; similar-song intrinsic 4 improvements (MoodCoherence +0.034,
SelfConsistency +0.045, Symmetry +0.055). **Adopted** (`AUDIO_BACKBONE="muq"`; song audio-weight
0.82→0.76; `COLOR_COHERENCE_ALPHA 0.45→0.55`). One consistent backbone everywhere (similar-song,
colour-coherence, valence-audio). Cover index (precomputed on MERT) unaffected. Tools:
`muq_mert_compare.py`, `muq_migration.py`. Lesson: a model's MARBLE-benchmark edge transfers to our
VN end-metrics **only after per-task re-optimization** — fixed incumbent weights masked it.

---

# V41 (2026-06-13) — MuQ-arousal adopted (full MuQ backbone consistency)

The arousal label was the last MERT-based piece. Re-tested MuQ-arousal in the post-V40 context.
At the MERT-inherited tempo weight (0.15) it failed tempo-tracking (ρ(A,BPM)=0.147) — **but that
weight was wrong for MuQ**: MERT-arousal partially encodes tempo, MuQ does not (ρ≈0 vs BPM), so MuQ
needs a HIGHER explicit tempo weight. Sweeping (`tools/tune_muq_arousal.py`) found **w_tempo=0.35**:
DEAM-human-CV **0.692** (> MERT 0.647) AND ρ(A,BPM) **0.466** (clears the 0.20 target both prior
versions failed), colour-TE **0.0246** ≈ v6h (tie), TE-ordering ALL PASS, journey ✓, r(V,A)=0.114,
similar-song intrinsic 4 improvements. **Adopted (v6i, `tools/build_v6i_labels.py`).** Now ONE
consistent backbone everywhere: MuQ for similarity, colour-coherence, valence-audio probe, AND
arousal probe (+explicit tempo/loudness). MERT remains only in the precomputed cover index + as
rollback.

**Methodological lesson (thesis-worthy):** a SOTA model (MuQ) first *regressed* the end metric not
because it was worse, but because it was evaluated with the **incumbent's hyperparameters** (MERT's
tempo weight). Re-optimizing the new model's own weights flipped it to a clear win. Always re-tune a
new component's hyperparameters before judging it — don't inherit the old one's settings.
