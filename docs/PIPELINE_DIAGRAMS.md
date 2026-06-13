# Recommendation Pipelines — Flow Diagrams

Flow diagrams (Mermaid) for the two features, annotated with signals, weights, and the
research basis. Renders on GitHub / most Markdown viewers. State = current serving (V36–V39, v6g).

---

## 1. Recommend-by-Song (similar song)

```mermaid
flowchart TD
    A["Seed song (track_id)"] --> B{"Precomputed signals"}
    B --> S1["MERT embedding<br/>768-d, L2-norm<br/>(frozen MERT-v1-95M, audio)"]
    B --> S2["VN-SBERT lyrics<br/>768-d embedding"]
    B --> S3["song V-A (v6g)<br/>see §3"]

    S1 --> C1["MERT cosine → [0,1]"]
    S2 --> C2["lyrics cosine → [0,1]"]
    S3 --> C3["V-A heteroscedastic RBF<br/>σ_V=0.22, σ_A=0.14<br/>(σ_V>σ_A: valence less audio-reliable)"]

    C1 --> F["FUSION (Σw=1)<br/><b>0.82·MERT + 0.12·V-A + 0.06·lyrics</b><br/>weights: SLSQP-optimal on editorial NDCG"]
    C2 --> F
    C3 --> F

    F --> G["Exclude seed + covers<br/>(MERT>0.95 & lyrics>0.90)"]
    G --> H["Diversity rerank (_fast_rank)<br/>artist repeat cap = 3"]
    H --> Z["Top-K similar songs"]
```

**Why:** MERT dominates (0.82) because timbre/genre/energy define "sounds alike" (MARBLE);
V-A (0.12) keeps mood coherent (ablation: removing it collapses mood-coherence); lyrics (0.06)
a minor semantic cue (noisier). Timbral/rhythmic/tonal/instrument/mood slots = weight 0
(Essentia degenerate at 44.1 kHz / redundant). Learned metric+fusion heads were trained &
evaluated (Phase 1) but did **not** beat this baseline → not adopted (honest negative result).

---

## 2. Recommend-by-Color

```mermaid
flowchart TD
    IN["Color hex(es)<br/>1 = static mood · 2 = journey"] --> VA["hsl_to_va: color → (V,A)"]

    subgraph VA_MODEL["Color → V-A (per-color, fixed 12 ICEAS colors)"]
        VA --> VAL["Valence = Oklab ridge<br/>fit to ICEAS norms (Jonauskaite 2020)<br/>r=0.97 / LOO-CV ~0.82"]
        VA --> ARO["Arousal = Whiteford 2018 (color↔MUSIC)<br/>0.373·redness + 0.356·sat + 0.271·lightness − 0.10<br/>(lighter/saturated → faster music)"]
    end

    VAL --> CDF["CDF target mapping<br/>F_catalog(color V-A) → target quantile<br/>(un-compress: 12 colors span the catalog)"]
    ARO --> CDF

    CDF --> SPLIT{"1 or 2 colors?"}

    SPLIT -- "1 color" --> R1["V-A mood score (heteroscedastic RBF)<br/>σ_V=0.20, σ_A=0.14 (rank space)"]
    R1 --> COH["Coherent-cluster select<br/>over-fetch top_k×5; greedily grow:<br/><b>α·mood + (1−α)·cos(MERT_centered, centroid)</b>, α=0.45<br/>(centered MERT: random 0.0 vs neighbor 0.45)"]
    COH --> DIV["Artist-diversity cap + cover filter"]
    DIV --> Z1["Top-K (on-mood + acoustically coherent)"]

    SPLIT -- "2 colors" --> J1["Iso-principle waypoints A→B<br/>sigmoid (ease-in-ease-out), ~10–15%/step<br/>(Starcke 2024, Saari 2016)"]
    J1 --> J2["+ audio smoothness bonus<br/>small ΔBPM + high cos(MERT) to previous, γ=0.30<br/>(Knopke 2018 acoustic continuity)"]
    J2 --> J3["Sequence along path"]
    J3 --> Z2["Top-K mood journey (smooth in mood + tempo/timbre)"]
```

**Why:** color↔music is mediated by V-A (Palmer 2013, Whiteford 2018) → V-A picks WHICH mood;
CDF fixes "every color feels mid" (raw color arousal spans a narrow band); MERT-coherence makes
a color's songs "feel alike" (V-A alone can't carry timbre); the journey follows the iso-principle
plus DJ-style acoustic continuity. `color_to_emotion_probs` (the "why" chip) uses a separate
ICEAS emotion table — unaffected by the arousal model.

---

## 3. song V-A (v6g) — shared sub-pipeline (feeds both features)

```mermaid
flowchart TD
    L["Lyrics (cleaned)"] --> V1["VN-sentiment (PhoBERT) 0.31"]
    L --> V2["VN lexicon (negation-fixed) 0.30"]
    L --> V3["EmoBank → XLM-R 0.28"]
    AU["Audio (MERT/MuQ)"] --> V4["MuQ valence probe 0.12"]
    V1 --> VAL2["VALENCE = EWE blend (de-circularized)<br/>weight = reliability"]
    V2 --> VAL2
    V3 --> VAL2
    V4 --> VAL2

    AU --> A1["MERT-arousal probe (DEAM) 0.67"]
    AU --> A2["loudness (LUFS) 0.18"]
    AU --> A3["clean tempo / BPM 0.15"]
    A1 --> ARO2["AROUSAL = NNLS fit to DEAM-human"]
    A2 --> ARO2
    A3 --> ARO2

    VAL2 --> OUT["song (V, A) → song_va"]
    ARO2 --> OUT
```

**Why:** music-emotion research — **valence ← lyrics** (stronger), **arousal ← audio** (~.81, Eerola).
EWE weights (Grimm & Kroschel) = signal reliability, no LLM target → de-circularized. Validated:
PMEmo cross-corpus transfer V 0.69 / A 0.65; independent refs (CLAP-ears arousal 0.48, XLM-T
valence 0.59); GPT 0.71 / Gemini 0.64.

---

### Legend
- All embeddings frozen + L2-normalized; probes are linear (MARBLE protocol — no fine-tune).
- Weights cited + validated offline (NDCG/FDR/bootstrap CI/ablation); no user data; LLM offline-only.
