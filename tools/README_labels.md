# Emotion-label pipeline (Valence–Arousal) — provenance & reproduction

Each of the 5,138 catalogue songs carries one **(Valence, Arousal)** coordinate, shared by both
recommendation features. The served labels are **frozen** in `data/emotion_labels_v6i.json`
(pointed to by `config.RELABELED_EMOTIONS_FILE`). At serving time there is **no model inference
and no LLM** — labels are a lookup. All models are used **frozen + linear probe only** (no
fine-tuning); every signal traces to a published source.

## How V-A is built

```
VALENCE  =  EWE( vn_lex , vn_sent , emobank , muq )  →  rank  →  affine-calibrate
            (Evaluator-Weighted-Estimator; weights = measured signal reliability, NO LLM target)

  vn_lex   build_grounded_vnlex.py     → data/vnlex_grounded_valence.json
           NRC-VAD-Vietnamese (Mohammad 2018) + VnEmoLex (Zenodo 801610), clause-negation
  vn_sent  build_grounded_vnsent.py    → data/vnsent_grounded_valence.json
           frozen ViSoBERT (Nguyen 2023) + Ridge probe on UIT-VSMEC (emotion→NRC-VAD valence)
  emobank  emobank_valence_probe.py all→ data/emobank_valence.json
           frozen XLM-R-base [CLS] + Ridge probe on EmoBank (Buechel&Hahn 2017), cross-lingual
  muq      muq_probe.py                → data/muq_valence.json
           frozen MuQ audio embeddings + Ridge probe on DEAM-human (Aljanaki 2017)

  EWE reliability weights (this rebuild): vn_lex 0.35 · emobank 0.341 · vn_sent 0.218 · muq 0.091

AROUSAL  =  rank-blend [ MuQ-arousal 0.574 , clean-BPM 0.35 , loudness 0.076 ]  →  standardise
            (DEAM-human-grounded; tempo weight raised to 0.35 because MuQ encodes tempo weakly)

  muq_arousal  muq_probe.py            → data/muq_arousal.json   (MuQ + DEAM probe)
  clean-BPM    extract_clean_bpm.py    → data/clean_bpm.json     (librosa downbeat tempo)
  loudness     data/crossfade_features.json (loudness_lufs)
```

## Reproduce from scratch (offline; one-time model downloads for ViSoBERT/XLM-R)

```bash
python -m tools.muq_probe                      # muq_valence.json + muq_arousal.json   (offline)
python -m tools.build_grounded_vnlex           # vnlex_grounded_valence.json           (offline)
python -m tools.build_grounded_vnsent          # vnsent_grounded_valence.json          (HF ViSoBERT)
python -m tools.emobank_valence_probe all       # emobank_valence.json                  (HF XLM-R)
python -m tools.build_labels_repro             # emotion_labels_repro.json + gate vs frozen v6i
```

`build_labels_repro.py` rebuilds the FINAL labels directly from the four grounded signals
(skipping the historical v6a→v6c→v6g→v6h replay) using the exact method of `build_v6h_labels.py`
(valence) + `build_v6i_labels.py` (arousal). Deterministic (fixed seeds; pure numpy/NNLS).

### Reproduction gate (measured)
```
VALENCE  ρ(repro, frozen v6i) = 1.0000     (exact)
AROUSAL  ρ(repro, frozen v6i) = 1.0000     (exact; max|Δ| = 0.0000)
```
i.e. the served labels are reproduced bit-for-bit by the documented offline pipeline.

## Independent convergent validity (optional, paid)

`build_va_reference_gpt.py` builds an independent V-A reference with OpenAI **gpt-4o-mini**
(reads `OPENAI_API_KEY`/`OpenAI_API_KEY` from `.env`; full catalogue ≈ **$0.60**; resume-safe cache):
```bash
python -m tools.build_va_reference_gpt --probe 50 --model gpt-4o-mini   # cost probe (~$0.01)
python -m tools.build_va_reference_gpt --model gpt-4o-mini               # full → data/va_reference_gpt.json
```
Reference reliability: test–retest ICC valence **0.991**, arousal **0.965**; cross-model
(gpt-4o vs mini) ICC 0.927 / 0.784.

Convergent validity of the frozen labels vs this independent judge (n = 5138):
```
VALENCE  ρ(v6i, GPT) = 0.634   CI95 [0.617, 0.650]
AROUSAL  ρ(v6i, GPT) = 0.412   CI95 [0.389, 0.435]
```
(Arousal agreement is lower by design: arousal is derived from audio, the GPT judge reads lyrics only.)

## Notes
- The frozen `emotion_labels_v6i.json` is the submission artifact — **do not regenerate in place**;
  `build_labels_repro.py` writes a separate `emotion_labels_repro.json` for gating.
- The historical builders (`build_v6a/v6c/v6g/v6h_labels.py`, `va_ewe_weights.py`) are kept in
  `tools/` for inspection of the version history; `build_labels_repro.py` is the canonical,
  self-contained reproduction.
