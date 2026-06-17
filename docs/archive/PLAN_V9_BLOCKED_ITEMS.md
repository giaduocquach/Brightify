# Brightify v9 — Blocked Items Plan

Items that are technically scoped and designed but blocked on external resources.
Each can be picked up independently when the blocker is resolved.

---

## Item 1 — Pillar E: MLP V-A Combiner

**Status:** Blocked — needs labeled dataset  
**Blocker:** ~500 Vietnamese songs annotated with (valence, arousal) float values  
**Cost:** $500–1000 (crowdsource via Label Studio or VietCrowd), ~3 weeks calendar time  

**What to build:**
- A 2-output MLP: input = CLAP audio embedding (512-dim) + PhoBERT lyrics embedding (768-dim) → output = (valence, arousal) in [0,1]
- Replace the current heuristic V-A mapping in `core/emotion_analysis.py`
- Expected gain: more accurate V-A scores → better `recommend_by_colors()` alignment

**Implementation notes:**
- Annotation task: listen to song 30s clip, drag slider for valence (sad–happy) and arousal (calm–energetic)
- Model: 2-hidden-layer MLP, ~[1280 → 512 → 256 → 2], train with MSE + cosine annealing
- File: `core/va_regressor.py` (new), `config.py` flag `ENABLE_VA_MLP`
- Backtest: measure `recommend_by_colors()` precision via new color-query GT

---

## Item 2 — Pillar E: Multi-task ViDeBERTa Fine-tuning

**Status:** Blocked — needs labeled dataset (same as Item 1)  
**Blocker:** Same annotation pool as above, plus emotion category labels (13 categories)  

**What to build:**
- Fine-tune `vinai/videberta-base` on 3 simultaneous tasks:
  1. Emotion category classification (13-way)
  2. Mood quadrant classification (4-way: Q1/Q2/Q3/Q4)
  3. V-A regression (if Item 1 data available)
- Expected gain: better lyrics embedding alignment with emotion/mood queries

**Implementation notes:**
- Multi-head output: shared encoder + 3 task-specific heads
- Training: gradient accumulation, freeze bottom 6 layers for 2 epochs then unfreeze
- File: `tools/finetune_videberta_multitask.py` (new)
- Backtest: compare NDCG@10 on editorial GT vs current `ENABLE_PILLAR_B` baseline

---

## Item 3 — Pillar F: Weather API Context

**Status:** CODE DONE — waiting for API key only  
**Blocker:** Set `OWM_API_KEY` environment variable (free tier at openweathermap.org, ~5 min signup)  
**Cost:** Free  

**Code shipped (2026-05-28):**
- `core/vn_context.py`: `_get_weather_shift()` + wired into `get_context_shift(use_weather=True)`
  - Rain/drizzle/thunder → V −0.03 / A −0.05
  - Clear/sunny → V +0.04 / A +0.03
  - Hot-humid (>32°C, >70% RH) → A +0.02
  - Silent no-op if key missing or network error
- `config.py`: `OWM_API_KEY`, `OWM_LAT`, `OWM_LON`, `OWM_TIMEOUT_S`

**To activate:** `export OWM_API_KEY=your_key_here` — no code changes needed.

---

## Item 4 — Pillar G: Async SQLAlchemy + Redis Cache

**Status:** Blocked — engineering sprint (~1 week)  
**Blocker:** Dev time; no external dependency  
**Priority:** Low (DevX/performance, not AI/ML)  

**What to build:**
- Migrate `db/engine.py` from sync SQLAlchemy to `asyncpg` + `SQLAlchemy[asyncio]`
- Add Redis LRU cache for hot recommendation queries (TTL 5min)
- Expected gain: 40–60% latency reduction on concurrent requests

**Implementation notes:**
- `asyncpg` driver replaces `psycopg2`
- All route handlers in `api/` need `async def` + `await` throughout
- `core/recommendation_engine.py` stays sync (CPU-bound NumPy); bridge via `asyncio.run_in_executor`
- Redis: cache key = `sha256(endpoint + params)`, invalidate on seed/catalog update
- Migration is large but mechanical — no AI logic changes

---

## Item 5 — P5: Second Independent GT for Pillar F

**Status:** Partially addressed — cross-artist check done; full independent GT still blocked  
**Blocker (full GT):** Expert labels or actual user listening session data  
**Priority:** Medium (affects trustworthiness of the +107% headline)

**Proxy circularity check (DONE 2026-05-28):**  
Added `pillar-f-xartist` command (`tools/backtest_v2/cli.py`) that re-runs Pillar F evaluation
keeping only seed→relevant pairs from **different artists** in each playlist. This directly tests
whether KG gain is real cross-artist retrieval or same-artist inflation.  
Run: `python -m tools.backtest_v2 pillar-f-xartist`  
Report saved to: `var/runtime/backtest/reports/pillar_F_xartist/`

**Why needed (full GT still relevant):**  
Cross-artist check uses the same editorial GT source (YouTube Music playlists). A structurally
different GT (different platform, different labelers) is the gold standard to rule out broader
circularity between KG and playlist co-occurrence.

**Options (ranked by feasibility):**  
1. Collect 200–300 explicit user listening sessions (next-song in actual listening history) — if the app is deployed
2. Expert annotation: 30–50 seed songs, music experts label top-10 relevant songs each (~2 hours work)
3. Cross-platform GT: crawl a second platform's playlist data (e.g. Zing MP3) and match to catalog

---

## Backtest Notes (v8.0 — updated 2026-05-28)

- **Isolation issue (RESOLVED):** Earlier runs had a baseline contamination issue (e.g. iter_6 ran with KG still on). This was fixed by `Catalog.build_isolated(V72_BASELINE_FLAGS)` + `_pinned_recommend_flags`, committed 2026-05-28. All pillar re-runs done on 2026-05-28 use the correct isolation.

- **Pillar C / Pillar E show CI=[0,0]** on editorial GT — expected. RRF and CLAP don't affect `recommend_by_song()`. Their actual target path `recommend_by_colors()` was validated separately (2026-05-28):
  - Pillar C color: Δ+0.056 CI95=[+0.025, +0.090] — **CONFIRMS**
  - Pillar E color: Δ+0.065 CI95=[+0.028, +0.109] — **CONFIRMS**

- **Bonferroni CI (DONE 2026-05-28):** All 6 pillar reports re-run with `BONFERRONI_CI_LEVEL ≈ 0.9917` (CI99.2%). No verdicts changed. Gate print labels now show `CI99.2%` instead of `CI95%`. All `_CI_LABEL` and gate-threshold fixes applied in `cli.py`.
