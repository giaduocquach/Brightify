# Color Feature Upgrade V12 — "Màu → Cảm xúc → Nhạc" peak edition

**Date:** 2026-05-31
**Goal:** Make `recommend_by_colors` the most research-grounded, friendly, "wow" feature
of the system, faithful to its philosophy: *user expresses mood non-verbally through
colour; the system infers emotion; then finds matching music.*

User decisions (2026-05-31):
- **Colours:** 1 primary + up to 3 (blend). Aggregate by **UNION** (max over colours),
  NOT centroid average — avoids the "drift to centre" mush.
- **Culture:** keep **universal** mapping (Jonauskaite r=.88 global), no VN override.
- **Emotion bridge:** show a light chip "màu → cảm xúc → N bài" above results.

---

## 1. Research foundation (verified, no invented citations)

| Finding | Source | Use |
|---|---|---|
| Colour↔music mediated by **emotion (V-A)**, not raw audio. Partialling out emotion kills all colour↔audio correlations. | Palmer/Schloss, PLOS One pone.0144013 | Confirms our chain is correct. Emotion is the bridge. |
| **Arousal** ← redness r_s=.755, saturation .720, darkness −.549. **Valence** ← lightness .484, yellowness .466. Saturation does NOT predict valence. | Whiteford 2018, PMC6240980 | Exact V-A formula (§2). |
| V-A explains: saturation 72%, lightness 68%, red/green 58%, yellow/blue 33%. | Whiteford 2018 | Lightness+yellow most reliable for valence. |
| a* (green-red) inconsistent in emotion mediation; focus Lightness + b* (yellow-blue). | PLOS One | Weight b*/lightness for valence. |
| 12 universal colour terms; black & red most emotional, brown least; r=.88 universal. | Jonauskaite 2020, Psych Science | Canonical palette = these 12 named colours. |
| Categorical emotions (happy/sad/angry/tender) + continuous response recommended. | PLOS One | Keep 8 CLAP labels; offer continuous picker for power users. |

---

## 2. Backend — `core/advanced_color_mapping.py`

### 2.1 Refine HSL→V-A formula (Whiteford-exact)
Replace the current formula (which wrongly uses `(1-saturation)` for valence).

```
# a* / b* perceptual axes from hue
redness    = (1 + cos(h°))      / 2     # red=1, cyan=0   (a* proxy)
yellowness = (1 + cos(h°-60))   / 2     # yellow=1, blue=0 (b* proxy)

# Whiteford normalized-r weights:
valence = 0.52*lightness + 0.48*yellowness            # drop saturation (not a predictor)
arousal = 0.37*redness + 0.36*saturation + 0.27*(1-lightness)

# achromatic (s<12%): hue meaningless
valence = 0.35 + 0.55*lightness ;  arousal = 0.50 - 0.35*lightness
```
Then Gaussian soft-assignment over 8 CLAP Russell centroids (σ=0.22) — unchanged.

### 2.2 Canonical palette (Jonauskaite 12) with mood-correct swatches
Swatches must use S/L matching the intended emotion (e.g. "sad blue" = deep muted
navy `#2c3e66`, NOT vivid `#0000FF` which reads as energetic due to saturation→arousal).
Each named colour → representative hex tuned so its V-A lands in the intended quadrant.

## 3. Backend — `core/recommendation_engine.py` `recommend_by_colors`

### 3.1 UNION aggregation (multi-colour)
- Compute per-colour V-A and emotion vector.
- `va_sim[song]   = max over chosen colours of Gaussian(song_va, colour_va)`
- `emotion_sim[song] = max over colours of cos(song_emo, colour_emo)`
- 1 colour → identical to today. 2–3 colours → song relevant if it matches ANY chosen
  mood (a "mixed-mood" playlist), not the bland average.

### 3.2 Return the emotion bridge
Add to the response: `query_emotion` (top inferred label, VN display name) and
`query_va` per colour, so the frontend can render the chip.

### 3.3 Cap at 3 colours (guard).

## 4. Frontend — `static/js/ai-discovery.js`, `ui-pages.js`

- **Tap-to-run:** tapping a colour card selects it AND runs immediately (friendly,
  "chạy ngay"). Adding a 2nd/3rd re-runs. Big button kept for explicit re-run.
- Cap **3** (was 5); update `0/5`→`0/3`; trim palette presets to 3 colours each.
- Canonical 12-colour cards with honest VN emotion labels mapped to the 8 backend
  emotions (vui/phấn khích/bình yên/thư thái/u sầu/buồn/căng thẳng/giận dữ).
- **Emotion bridge chip** above results: e.g. `🔵 Xanh dương → U sầu (V .28 / A .32) → 12 bài`.

## 5. Validation
- Re-run color→emotion accuracy harness (target ≥ 10/12 with mood-correct swatches).
- Re-run GT-COLOR Recall@K / mAP@K (relative comparison).
- Smoke-test 1-colour and 3-colour union paths in browser.

## 6. Out of scope (future)
- Continuous colour-wheel picker (PLOS continuous-response) — power-user nicety.
- Per-user personalization of colour→emotion (individual differences, PLOS).
- VN cultural layer (decided OUT this round; revisit if user demand).
