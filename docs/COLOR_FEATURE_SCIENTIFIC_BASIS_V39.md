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

---

# V42 (2026-06-13) — lexicon fully published (no self-made) + tech-debt cleanup

## Valence lexicon now grounded in TWO published resources (auto-translation improved)
The served valence (v6i) was already 100% NRC-VAD-VN (no self-made valence words — the earlier
"GenZ slang" note referred to the *retired* hand lexicon, not the grounded build). To reduce the
auto-translation caveat, the build now **cross-checks NRC-VAD-VN against the native VnEmoLex**
(Doan & Luu 2022, *Improving Sentiment Analysis By Emotion Lexicon Approach on Vietnamese Texts*,
IALP 2022, arXiv:2210.02063; lexicon DOI **10.5281/zenodo.801610**): drops words whose NRC-VAD-VN
valence sign CONFLICTS with VnEmoLex's native polarity (10 likely mistranslations removed) and adds
236 native VN words NRC lacks. Coverage 98.2%→**99.3%**; vn_lex EWE reliability 0.78→0.79; colour-TE
0.0250 (no regression); all gates green. Every valence word now traces to **NRC-VAD (Mohammad 2018)
and/or VnEmoLex** — no subjective scores. Only remaining hand element: a 10-word negation list
(standard closed-class NLP, not valence scores). `tools/build_grounded_vnlex.py` (+VnEmoLex).

**Honest provenance nuance (V45):** VnEmoLex is itself built on **NRC EmoLex + Viet WordNet**
(~12.8k words: 4,431 from NRC-EmoLex, 8,364 from Viet WordNet). So vn_lex's two sources share an NRC
lineage — the genuinely *VN-native* contribution is the **8,364 Viet WordNet words**. Both remain
fully published/citable; this is stated so the two are not mis-presented as wholly independent.

## Remaining inherent limitations (cannot fix offline — honest)
- **n=12 colours / VN not in ICEAS-30:** ICEAS studied exactly the 12 basic colour TERMS, so there
  are no "more colours" to validate on; no VN-native colour-emotion dataset exists. LOO-CV (r≈0.87)
  is the held-out validation available. Fixing requires new human colour-emotion data (out of scope:
  no user-data collection). Stated as a limitation, not papered over.
- **Cover index built on MERT (backbone is MuQ):** intentional — cover/duplicate detection is a
  separate semantic-dedup task (a precomputed track→covers exclusion list), validated on MERT and
  backbone-independent at serving. Not rebuilt on MuQ to avoid re-calibrating thresholds for zero
  benefit (the list already identifies the real covers). Documented as a deliberate choice.

---

# V43 (2026-06-13) — vn_sent re-grounded (frozen ViSoBERT + UIT-VSMEC probe, no community blackbox)

`vn_sent` (~25–30% of the EWE valence; **shared by BOTH features** via the common V-A labels) was
the only lyrics-emotion signal whose training corpus was not citable — the community
`wonrax/phobert-base-vietnamese-sentiment` head over an unpublished dataset. Re-grounded with the
**same recipe as the EmoBank probe** (frozen encoder + linear probe + published data, no fine-tune,
offline-only): **frozen ViSoBERT** (Nguyen et al. 2023, EMNLP Findings — encoder pretrained for VN
social-media text, matching lyric register) + **Ridge probe** trained on **UIT-VSMEC** (Ho et al.
2020, peer-reviewed 7-emotion corpus), with **emotion→valence read from NRC-VAD** (Mohammad 2018) —
so even the label mapping is grounded, zero self-made scores. `tools/build_grounded_vnsent.py`.

Probe validity: UIT-VSMEC 5-fold CV R²=0.35, held-out test ρ(pred,emotion-valence)=0.56,
high−low valence gap +0.30. Catalog: healthy spread (mean 0.358, std 0.078 — no OOD collapse),
ρ vs old wonrax 0.41, ρ vs served valence 0.33. EWE self-down-weighted it (reliability 0.62 →
weight 0.22, vs wonrax ~0.30 — correctly noisier).

**Adoption gate (end-metric governs):** colour-TE **0.0250 → 0.0242** (improved, CI[0.0219,0.0263]),
TE-ordering ALL PASS, journey ✓, Whiteford-tempo ρ(L,BPM)=0.41/ρ(S,BPM)=0.66 ✓, ICEAS r=0.969 ✓,
r(V,A)=0.161 ✓; similar-song MoodCoherence +0.034, Symmetry +0.048, Tempo stable. Valence ρ vs GPT
0.677→0.634 (the citability trade-off; the recommendation end-metric improved, so ADOPTED).
Rejected variant: UIT-VSFC (student-feedback sentiment) — domain too far from lyrics, catalog
predictions collapsed (std 0.05, ρ vs served 0.14) → VSMEC's social-media register was decisive.

**All lyrics-emotion signals are now fully grounded:** vn_lex (NRC-VAD-VN + VnEmoLex), vn_sent
(ViSoBERT + UIT-VSMEC + NRC-VAD), emobank (XLM-R + EmoBank) — each = published dataset + frozen
backbone + linear probe, no fine-tuning, no community blackbox, LLM-free at serving.

---

# V44 (2026-06-13) — model bake-off: adopt e5-large for lyrics-similarity; others verified best (fair)

Full SOTA-candidate bake-off for every learned component, each judged on the END-metric (not the
backbone's own benchmark) and — critically — RE-TUNED at its OWN optimal settings before judging
(the project's standing lesson). Adopt only if it beats the active model decisively.

| Slot | Candidate | Fair setting applied | End-metric result | Verdict |
|---|---|---|---|---|
| lyrics-sim | **multilingual-e5-large** (Wang 2024) | lyrics-weight sweep 0.08–0.20 | MoodCoherence/Symmetry/SelfConsistency ↑ vs vnsbert at EVERY weight (200 seeds); best @0.08 | **ADOPT** |
| lyrics-sim | BGE-M3 | same sweep | also > vnsbert, but e5 better overall | reject (2nd) |
| audio | MuQ-MuLan (Tencent) | audio-weight sweep 0.70–0.88 | colour-TE 0.0263>0.0242, MoodCoherence < MuQ | reject — keep MuQ |
| vn_sent | PhoBERT-large (VinAI) | + word-segmentation (pyvi) | CV R² 0.403>ViSoBERT 0.348 but colour-TE 0.0239≈0.0242 | **tie** — keep ViSoBERT |
| emobank | mDeBERTa-v3 | + mean-pool (not [CLS]) | CCC 0.489<XLM-R 0.546, colour-TE 0.0259>0.0242 | reject — keep XLM-R |

**Adopted:** `EMBEDDINGS_FILE → data/lyrics_e5large.npy` (intfloat/multilingual-e5-large, mean-pooled,
"query: " prefix). Lyrics weight unchanged (0.08 was already its optimum). MuQ / ViSoBERT / XLM-R kept.

**Methodological notes (honest):**
- Fair re-tuning CHANGED one verdict: PhoBERT-large went rejected→tie once segmentation was added
  (the first pass without VnCoreNLP/pyvi was an unfair handicap). It is now a legitimate equal to
  ViSoBERT; ViSoBERT kept on secondary grounds (social-media domain match for lyric register; no
  segmentation dependency; ~4× smaller). PhoBERT used pyvi, not its native VnCoreNLP — a residual
  gap that would lift its in-domain CV but not flip the ensemble-dominated colour-TE tie.
- MuQ-MuLan is designed for cross-modal (text↔music) retrieval, NOT intra-modal audio similarity;
  no published benchmark compares it to MuQ on this task, and CLIP-style theory predicts the
  text-projected embedding loses acoustic detail → our result (worse coherence) is consistent.
  Residual test gaps (single-clip vs MuQ's multi-clip; un-retuned COLOR_COHERENCE_ALPHA) left
  intentionally — non-decisive given theory + the end-metric direction.
- Lesson reaffirmed: 3/4 SOTA-on-paper candidates did NOT beat the task's end-metric; only e5-large
  did. Benchmark rank ≠ end-metric fit. Tools: encode_lyrics.py, run_fair_rerun.sh, run_candidate_gates.sh.

---

# V45 (2026-06-13) — closing 3 caveats: VnEmoLex citation, e5 cross-validation, VN-extrapolation

**#7 VnEmoLex citation — RESOLVED** (see provenance note above): Doan & Luu 2022 (IALP, arXiv:2210.02063),
DOI 10.5281/zenodo.801610; built on NRC-EmoLex + Viet WordNet (native part = 8,364 Viet WordNet words).

**#2 VN not in ICEAS-30 — DATA-SUPPORTED extrapolation** (`tools/iceas_cross_cultural.py`):
Tested cross-cultural stability of colour→valence on the ICEAS raw multi-country data (37 countries,
≥30 ppl each). Each country's colour→valence vector (NRC-VAD-weighted emotion endorsements)
correlated vs the global average: **median ρ = 0.930** (min 0.48, max 0.99). Asian countries — the
cultural proxy for Vietnam — **median ρ = 0.923** (India 0.958, Philippines 0.923, Japan 0.923,
China 0.762). ⇒ colour→valence is highly culturally stable, so extrapolating the ICEAS-fit to
Vietnam (absent from ICEAS-30) is **empirically defensible, not just assumed**. Also: the product
exposes only **12 fixed colours**, so n=12 is the exact operating domain (LOO-CV r≈0.87), not an
under-sampled extrapolation. Limitation downgraded from "unvalidated" to "bounded by cross-cultural data".

**#5 e5-large — added an independent validation layer (honest, mixed)**: beyond the intrinsic
coherence win, evaluated e5 vs vnsbert on the **editorial-playlist GT** (human-curated, 872 queries):
NDCG@10 0.0664 vs 0.0666, mAP 0.0261 vs 0.0258, MRR 0.1572 vs 0.1623 — a **TIE** (e5 neither better
nor worse on editorial co-membership). Expected: lyrics is only 8% of an audio-dominated (MuQ 0.76)
fusion, so swapping it barely moves an audio-driven metric. Net honest verdict: e5-large is **better
on intrinsic coherence (Mood/Symmetry/SelfConsistency, the "songs feel alike" axis) and neutral on
editorial NDCG** → a safe, low-leverage improvement, kept (no regression). A clean LLM-judge panel
would require rebuilding the judged pool on e5's own recommendations (OpenAI cost + pool-bias) —
not worth it for an 8%-weight signal given editorial already answers "neutral". Stated plainly: the
e5 gain is real but modest and concentrated in intrinsic coherence, not a broad win.
