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

**Status:** Blocked — needs API key  
**Blocker:** OpenWeatherMap API key (free tier: 1000 calls/day, sufficient)  
**Cost:** Free  

**What to build:**
- Add weather-based V-A shift in `core/vn_context.py` alongside existing time-of-day shifts
- Rainy/overcast day → lower arousal (−0.05), lower valence (−0.03)
- Clear/sunny → higher arousal (+0.03), higher valence (+0.04)
- Hot/humid → no valence change, slight arousal boost (+0.02)

**Implementation (ready to code, 30-min task once key is available):**
```python
# In vn_context.py, new function:
def _get_weather_shift(lat=10.8231, lon=106.6297) -> dict:  # HCM default
    resp = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": lat, "lon": lon, "appid": OWM_API_KEY, "units": "metric"},
        timeout=2,
    )
    ...
```
- Config: `OWM_API_KEY = os.environ.get("OWM_API_KEY", "")` in `config.py`
- Fallback: if API unavailable/key missing, skip weather shift silently (already coded as no-op)

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

## Backtest Notes (v8.0)

One methodology note for future re-runs:

- **iter_6 (Pillar E) ran after iter_7 (Pillar F)** in actual execution order, so the iter_6 "lexicon baseline" already had KG enabled (NDCG=0.18632). The marginal effect of CLAP was measured on top of KG+MERT, not on top of A+B+C+D alone. The PASS verdict is still correct (Δ=0 in either context), but to get the exact isolated contribution of CLAP, re-run `python -m tools.backtest_v2 run-pillar-e` after setting `ENABLE_KG=False` temporarily.
- **iter_5 (Pillar C) and iter_6 (Pillar E)** show CI₉₅=[0,0] because RRF and CLAP don't affect `recommend_by_song()` paths tested by the editorial GT. This is expected and correct.
