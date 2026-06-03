# Recommend-by-Colour — Deep Research & Upgrade Plan (V16)

Date: 2026-06-02. Goal: re-found the colour feature on verifiable science + transform its UX.
Every external claim carries a source; confidence and `[UNVERIFIED]` flags are kept honest.

---

## PART A — CURRENT STATE (codebase)

### A.1 What the user sees (frontend `static/js/ui-pages.js`)
- A grid of **12 fixed colour cards** (Đỏ, Cam, Vàng, Hồng, Xanh lá, Ngọc, Xám, Trắng, Xanh dương,
  Lam thẫm, Tím, Đen), each with a Vietnamese emotion label + a hardcoded `data-va`.
- **Multi-select up to 3 colours, simultaneously**, on one page. Plus a custom hex input and a
  song-count stepper. Swatches are bespoke Tailwind-ish hexes (e.g. red `#ef4444`, blue `#3b5998`).

### A.2 What the engine does (after P1/P2, `core/`)
- Query colour → `hsl_to_va()` (recalibrated against ICEAS, P1) → V-A; → `color_to_emotion_probs()`
  (empirical ICEAS table, P2) → 8-emotion vector; → VN keyword centroid (PhoBERT).
- Per song: `score = 0.40·lyrics_cos + 0.30·va_RBF + 0.30·emotion_cos + 0.12·label_boost`,
  minus 0.08 cross-mood penalty, then RRF + artist-diversity rerank. Multi-colour = score each
  colour, round-robin interleave.

### A.3 Problems found (must fix)
1. **UI labels & `data-va` are STALE vs the engine.** They were tuned to the OLD mis-calibrated
   formula (e.g. blue = "U sầu/Suy tư"). After P1/P2 the engine says blue → excited/calm. The UI
   now contradicts the engine — and the old labels encode the *English* "feeling blue = sad" folk
   belief, which Jonauskaite 2020 shows is **not** cross-culturally universal.
2. **Two of three ranking signals are redundant** (`emo_s ≈ va_s`, both functions of song V-A —
   `song_emotion_vec` is derived from the song's audio-V-A colour). Effective model ≈ 0.40 lyrics +
   0.60 V-A. (P3.)
3. **Weights hardcoded** in `_color_score` (violates the project "config-only" rule); untuned on the
   new non-circular GT. (P3.)
4. **Multi-colour path untested**; the "blend / gradient" value proposition is unproven. (P5.)
5. No share artifact, no per-rec explanation, no novelty control (repetitiveness is the #1 industry
   complaint — see C.6).

---

## PART B — SCIENTIFIC FOUNDATION (sourced)

### B.1 The core premise is well-supported
People reliably match music to colour, **mediated by emotion** (not direct perception, not
synesthesia):
- Palmer, Schloss, Xu & Prado-León (2013), *PNAS* — music↔colour matches mediated by emotion;
  music-emotion ↔ colour-emotion correlations **r = .89–.99**; predicts happy/sad of chosen colour
  ~95%; holds in US **and** Mexico. https://www.pnas.org/doi/10.1073/pnas.1212562110
- Whiteford, Schloss, Helwig & Palmer (2018), *i-Perception* — two latent factors (arousal r_s=.83,
  valence r_s=.68) mediate matches; affect beats perceptual correspondence.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6240980/
- **Implication:** colour → **(valence, arousal)** → song-affect (Russell 1980 circumplex) is the
  validated pipeline — exactly what Brightify already runs. Confidence: HIGH.

### B.2 Colour is a VALIDATED non-verbal mood-expression channel (the killer justification)
- **Manchester Colour Wheel** — Carruthers, Morris, Tarrier & Whorwell (2010), *BMC Med Res
  Methodol* 10:12. A clinically validated instrument where people express mood by **picking a
  colour**; grey↔anxious/depressed, yellow↔positive; built for when "verbal communication may not be
  optimal." Different *shades* of one hue carried opposite valence.
  https://pubmed.ncbi.nlm.nih.gov/20144203/  Confidence: HIGH.
- This grounds the whole input mechanic: colour lets users express a feeling **they may not be able
  to name** (low emotional granularity / alexithymia — Barrett; ~10% alexithymia commonly cited
  but `[UNVERIFIED]` epidemiology). A non-verbal affect input is a genuine differentiator vs
  text-prompt features.

### B.3 Which colours to present, and exact hex
- **Basic colour terms (Berlin & Kay 1969):** 11 universal categories — white, black, red, green,
  yellow, blue, brown, purple, pink, orange, grey. (Contested but a strong tendency; WCS Kay &
  Regier 2003 supports constrained universals.) https://www.pnas.org/doi/10.1073/pnas.1532837100
- **ICEAS palette (Jonauskaite 2020):** 12 terms = the 11 + **turquoise**. This is the largest
  colour-emotion dataset and the one our P1/P2 mapping is fit to.
- **Canonical hex:** use **ISCC-NBS centroid sRGB** per colour name (Kelly & Judd 1955) rather than
  arbitrary `#FF0000`. https://en.wikipedia.org/wiki/ISCC%E2%80%93NBS_system
  Exact per-swatch hex of BCP-37 / ICEAS patches is `[UNVERIFIED]` — pull from paper supplements.
- **Design principle (from B.2 shades-matter):** the palette must **span all four V-A quadrants**
  using hue **and lightness/saturation** (bright yellow = joy, dark navy = sad, grey = melancholy,
  vivid red = passion). A hue-only wheel collapses many colours into "positive."

### B.4 Cross-cultural / Vietnamese overlay
- Colour-emotion is **largely universal** (Jonauskaite 2020: cross-national similarity **r = .88**,
  4,598 ppl, 30 nations) **but** nation predicts associations beyond the universal core.
- Vietnamese specifics (peer-reviewed): Minina (2021), *Russian J. of Vietnamese Studies* —
  **white = mourning** (and a 20th-c. shift toward youth/weddings), **yellow = imperial/prosperity**,
  **red = luck/festivity/weddings** (wu-xing five-elements system).
  https://vietnamjournal.ru/2618-9453/article/view/96433  Confidence: MEDIUM-HIGH.
- Our own ICEAS analysis (Asia vs West subset): valence deltas are **small (±0.05–0.09)** — red/brown
  slightly warmer in Asia, cool colours slightly cooler. So a VN overlay is a **refinement**, not a
  rewrite; publishable nuance, modest quality lever.

### B.5 Myths to avoid (don't hardcode as truth)
- "Each colour = one fixed universal emotion" — overstated; culture/shade/context modulate (Elliot
  2015, *Front. Psychol.* — colour-psychology field is "nascent," effect sizes overestimated).
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4383146/  → labels carry meaning; consider **per-user
  learning** of colour↔mood over time.
- Music-colour matching needs synesthesia — **false** (Palmer 2013, nonsynesthetes). Chromesthesia
  is only ~1% (Simner 2006 overall synesthesia 4.4%). Target the general intuition, not chromesthesia.

---

## PART C — UX, ACCESSIBILITY & COMPETITION (sourced)

### C.1 Choice architecture — 12 swatches is fine
- Hick's Law cost is **logarithmic** and colour is pre-attentively scannable; choice-overload
  (Iyengar & Lepper 2000, *JPSP*: 30% vs 3% purchase — note often mis-quoted as 40%) is **context-
  dependent and fragile** (Scheibehenne et al. 2010 meta-analysis, ~zero mean effect). Keep ~10–15,
  grouped by hue/quadrant. NN/G: long lists aren't inherently bad with good structure.
  Myth: "Miller 7±2 = max 7 menu items" (7±2 is memory, not on-screen options).
- Sources: https://www.nngroup.com/videos/hicks-law-long-menus/ ;
  https://ideas.repec.org/a/oup/jconrs/v37y2010i3p409-425.html

### C.2 Selection pattern — keep single-page simultaneous multi-select
- Colour picking is **exploratory/comparative** → a wizard (sequential) breaks side-by-side
  comparison (NN/G progressive vs staged disclosure). Keep one page; put **hex input behind a
  one-level "Advanced" disclosure**. https://www.nngroup.com/articles/progressive-disclosure/

### C.3 Accessibility (requirements, not polish)
- **WCAG 1.4.1 (Level A): never rely on colour alone** → every swatch **must** carry a text label +
  a **non-colour selected-state** (border/checkmark) + an accessible name. This makes our emotion
  labels mandatory. https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html
- CVD prevalence: **~8% men / ~0.5% women** (Western; global pooled ~4.4% men, Jeong et al. 2025
  *Ophthalmology*); deutan/protan red–green dominates → don't distinguish red vs green by hue alone.
- Touch targets **≥44×44px** (Apple HIG 44 / Material 48; WCAG AA floor 24).

### C.4 Affective design
- Norman's 3 levels (visceral/behavioural/reflective) — a colour-mood picker is a strong visceral +
  reflective surface; Walter's hierarchy — earn delight only after functional/reliable/usable.

### C.5 Promising input: a Valence-Arousal "mood pad" (complement, not replacement)
- A 2D pad (valence × arousal) is theory-aligned (Russell circumplex; our engine's own space) and
  lets users express pleasantness+intensity in one gesture. Precedent: **Musicovery** mood map,
  **Moodagent** sliders. Keep the labelled swatch grid as the accessible default; make the pad
  keyboard-operable with labelled quadrants.

### C.6 Competitive landscape & gaps
- Spotify (Daylist infers mood; AI DJ / Smart Filters = text/preset, Premium-gated), Apple ("Find
  Your Mood" presets), YouTube/Amazon (text/emoji/voice). **None use colour as input.**
- Affect products: Musicovery (V-A pad), Moodagent (5 mood sliders), Endel (biometric/context),
  Pandora (V-A as backend attribute). Closest colour analogue: **Picture-to-Playlist** (photo, not a
  swatch; no published traction). → **Colour-as-primary-input is open ground.**
- Viral identity mechanics: Wrapped / Instafest / Receiptify win via a **shareable visual identity
  artifact + social comparison** (BuzzFeed News on Wrapped). No affect product has this.
- #1 complaint across mood discovery: **repetitiveness / sameness / no agency.**

---

## PART D — USER NEEDS / PAIN POINTS (ranked, sourced)

1. **"Change/manage how I feel"** — mood regulation is the #1 listening motive (Schäfer et al. 2013,
   *Front. Psychol.*: arousal/mood-regulation M=3.78, top of 3 factors; IFPI 2023: 71% say music is
   important to mental health, 74% use it to relax/cope with stress, n=43k/26 countries). HIGH.
2. **"What should I play?" choice overload** — ~100k tracks/day uploaded (Luminate/UMG, widely
   cited). A small colour palette is a deliberately narrow, low-effort entry. HIGH need.
3. **"Algorithm feeds me the same stuff / I want control"** — filter-bubble sameness; users want
   agency. MEDIUM-HIGH (qualitative; no clean stat).
4. **"I think in moods/moments, not genres"** — 73% listen contextually (Spotify, vendor); Gen Z
   curates by vibe. MEDIUM-HIGH.
5. **"I can't put my feeling into words"** — low emotional granularity / alexithymia; colour is a
   validated non-verbal affect channel (Manchester Colour Wheel). HIGH for mechanism — key edge.
6. **"My music is who I am, and I want to share it"** — 52% tie music to identity (IFPI 2023);
   colour-tagged moods are inherently visual/shareable. HIGH (identity); Gen Z/TikTok specifics
   MEDIUM-LOW.
7. **"Help me process what I feel"** — music aids emotional clarification (Saarikallio & Erkkilä
   2007). A colour pick can be exploratory, not just matching. HIGH concept.

---

## PART E — UPGRADE PLAN (phased; each item: what / scientific or UX anchor / which gap it beats)

### Phase 1 — Correctness & honesty (foundation; low risk, this sprint)
- **E1. Sync UI to the engine (single source of truth).** Regenerate the 12 swatches + labels +
  `data-va` from the live engine (`hsl_to_va` / `color_to_emotion_probs` after P1/P2). Fix blue/
  purple/grey labels. *Anchor:* WCAG 1.4.1 (labels must be accurate); B.5 (don't ship the English
  "blue=sad" myth). *Beats:* internal contradiction; correctness for defense.
- **E2. P3 — de-duplicate signals + weights→config + tune.** Replace `emo_s` (currently ≈`va_s`)
  with an **independent** song-emotion source (v4 label / lyric-emotion), move `0.40/0.30/0.30,
  σ=0.20, ±0.12/0.08` into `config.py`, tune on the L2-LLM NDCG (paired bootstrap, like
  `weight_opt`). *Anchor:* project config rule; B.1 V-A pipeline. *Gate:* L2-LLM, L3.
- **E3. Canonical, quadrant-spanning palette.** Re-pick the 12 swatches so they (a) use defensible
  hues (ISCC-NBS centroids / ICEAS terms) and (b) **span all 4 V-A quadrants via lightness/
  saturation** (bright=joy, dark=sad, grey=melancholy, vivid-red=passion). *Anchor:* B.3, Manchester
  Colour Wheel (shades carry opposite valence). *Beats:* mood coverage; legitimacy.

### Phase 2 — Differentiation & delight (the "lột xác")
- **E4. Valence-Arousal mood pad** as a complementary input next to the swatch grid (keyboard-
  operable, labelled quadrants). *Anchor:* C.5, Russell circumplex, Musicovery precedent. *Beats:*
  expressiveness; matches our own engine space.
- **E5. Multi-colour = emotional gradient/blend** — design + validate the 2–3 colour path to produce
  a *journey* (e.g. calm→energetic) or a *blend*, and back it with a backtest (P5). *Anchor:* no
  competitor blends colours; Iso-principle for transitions. *Beats:* unique mechanic.
- **E6. "Why this song" chip per recommendation** (ties to C1 in the V15 plan): verbalize the real
  signal deltas (colour mood ↔ song V-A, lyric theme). *Anchor:* Norman reflective level; trust;
  EU DSA explainability. *Beats:* black-box mood buttons.
- **E7. Shareable "Your music in colour" card** — palette + top matches as a visual identity artifact
  with one-tap share. *Anchor:* Wrapped/Instafest virality (BuzzFeed); IFPI identity 52%. *Beats:*
  no affect product is shareable — growth loop.

### Phase 3 — Depth & moat
- **E8. Novelty / "dig deeper" dial** to fight repetitiveness (#1 complaint) — surface deep cuts,
  control popularity-debias (we already measured gini). *Anchor:* C.6.
- **E9. Vietnamese cultural overlay** behind a locale flag — adjust white/yellow/red per Minina 2021
  + our Asia-subset deltas; publishable. *Anchor:* B.4. *Beats:* global players won't localize.
- **E10. Per-user colour↔mood learning** (long term) — colour-emotion is partly personal (Elliot
  2015); learn each user's mapping from their picks/skips. *Anchor:* B.5.

### Always: gate every change with the non-circular backtest (L1 bridge / L2 retrieval / L3
discriminant) from `docs/PLAN_COLOR_BACKTEST_V15.md`. Accessibility (WCAG 1.4.1, 44px) is a hard
requirement on all UI work.

---

## Source index (load-bearing)
Palmer 2013 PNAS · Whiteford 2018 i-Perception · Jonauskaite 2020 Psych Science (r=.88) · Carruthers
2010 Manchester Colour Wheel (BMC) · Berlin & Kay 1969 / Kay & Regier 2003 PNAS · ISCC-NBS (Kelly &
Judd 1955) · Elliot 2015 Front. Psychol. · Russell 1980 circumplex · Schäfer 2013 Front. Psychol. ·
IFPI Engaging with Music 2023 · Iyengar & Lepper 2000 JPSP · Scheibehenne 2010 JCR · NN/G
(progressive disclosure, Hick's law) · WCAG 1.4.1 / 2.5.5 · Jeong 2025 Ophthalmology (CVD) · Minina
2021 RJVS (VN colour) · Musicovery / Moodagent / Endel / Spotify newsroom · BuzzFeed (Wrapped).
Flagged `[UNVERIFIED]`: exact BCP-37/ICEAS patch hex; alexithymia ~10%; some vendor/Gen-Z stats.
