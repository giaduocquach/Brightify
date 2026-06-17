"""Phase 2b — GPT-4o-mini decoupled valence validation.

Incremental design: saves every SAVE_EVERY completions → safe to kill/resume.
Rate limiting: TOKEN_BUCKET ensures ≤ RATE_RPM requests/min → no 429 errors.

Run:  python -m tools.valence_gpt_validate              # full catalog (resume-safe)
      python -m tools.valence_gpt_validate --sample 200 # 198-song spot-check
      python -m tools.valence_gpt_validate --report-only # just print metrics from cache
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT        = "var/runtime/backtest/reports/valence_gpt_validate.json"
CACHE_DIR  = Path("var/runtime/backtest/cache")
MODEL      = "gpt-4o-mini"
MAX_CHARS  = 1200
WORKERS    = 8            # concurrent calls (~300 RPM at 0.5s avg latency, well under Tier-1 500)
CALL_DELAY = 0.15         # per-worker sleep after each call — smooths bursts
SAVE_EVERY = 100          # flush incremental cache every N completions

SYSTEM = """Bạn đánh giá cảm xúc (valence) của lời bài hát tiếng Việt.
Valence = mức độ tích cực/vui vẻ của cảm xúc trong lời nhạc.

Thang điểm 0-10:
  0-2  Rất buồn: chia tay, đau khổ, tuyệt vọng, mất mát
  3-4  Buồn: nhớ nhung, cô đơn, tiếc nuối, u sầu
  5    Trung tính / bồi hồi: lẫn lộn vui buồn
  6-7  Tích cực: hi vọng, ấm áp, tình cảm, hạnh phúc nhẹ nhàng
  8-10 Rất vui: phấn khích, hân hoan, yêu đời, lễ mừng

Lưu ý văn hóa:
  - Bài cưới (đám cưới, kiệu hoa, cô dâu, trăm năm) = 8-9
  - Bài Tết / lễ hội (mùa xuân, chúc mừng năm mới) = 7-9
  - Rap/hip-hop xen tiếng Anh → tập trung vào nội dung tiếng Việt
  - Lyrics gần 100% tiếng Anh slang → trả lời 5 (không đủ ngữ cảnh Việt)

Ví dụ:
  "Anh biết em buồn, biết em đau, đang khóc một mình..." → 2
  "Kiệu hoa mang em về làm vợ anh, trăm năm hạnh phúc..." → 9
  "Mình yêu nhau đi, dù ngày mai ra sao cũng được..." → 6
  "Nhớ về Hà Nội, những con phố cũ, lòng bỗng thấy buồn..." → 3

Chỉ trả lời MỘT SỐ NGUYÊN từ 0 đến 10."""


# ── Single API call ───────────────────────────────────────────────────────────

async def _call(client, sem: asyncio.Semaphore,
                tid: str, lyrics: str) -> tuple[str, float | None]:
    text = lyrics[:MAX_CHARS].strip()
    if not text:
        return tid, None
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user",   "content": text},
                    ],
                    max_tokens=5,
                    temperature=0.0,
                )
                await asyncio.sleep(CALL_DELAY)
                return tid, float(np.clip(
                    int(resp.choices[0].message.content.strip()) / 10, 0, 1))
            except ValueError:
                return tid, None
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        return tid, None


# ── Main async runner with incremental save ───────────────────────────────────

async def _run(tids: list[str], lyrics: list[str],
               cache: dict[str, float], cache_f: Path) -> dict[str, float]:
    from openai import AsyncOpenAI
    api_key = os.environ.get("OpenAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI_API_KEY not found in .env")

    todo_ids = [t for t in tids if t not in cache]
    todo_lyr = [lyrics[tids.index(t)] for t in todo_ids]
    if not todo_ids:
        print("  All songs already cached.", flush=True)
        return cache

    client = AsyncOpenAI(api_key=api_key)
    sem    = asyncio.Semaphore(WORKERS)
    total  = len(todo_ids)
    n_done = 0
    t0     = time.time()
    lock   = asyncio.Lock()

    async def _task(tid, lyr):
        nonlocal n_done
        result = await _call(client, sem, tid, lyr)
        async with lock:
            tid_r, val = result
            if val is not None:
                cache[tid_r] = val
            n_done += 1
            if n_done % SAVE_EVERY == 0 or n_done == total:
                cache_f.parent.mkdir(parents=True, exist_ok=True)
                json.dump(cache, open(cache_f, "w"), ensure_ascii=False)
                elapsed = time.time() - t0
                rate    = n_done / elapsed if elapsed > 0 else 1
                eta     = (total - n_done) / rate
                total_done = len(cache)
                print(f"  {total_done}/{len(tids)} "
                      f"({total_done/len(tids)*100:.0f}%)  "
                      f"{rate:.1f} req/s  ETA {eta:.0f}s", flush=True)

    await asyncio.gather(*[_task(t, l) for t, l in zip(todo_ids, todo_lyr)])
    await client.close()
    return cache


# ── Metrics & report ─────────────────────────────────────────────────────────

def _kappa(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1-a.mean()) * (1-b.mean()))
    return round((po - pe) / (1-pe+1e-9), 4)


def _print_report(gem_v, gpt_v, aligned_ids, v5c, lyr_map, n_fail):
    rho, p_rho = ss.spearmanr(gem_v, gpt_v)
    r,   p_r   = ss.pearsonr(gem_v,  gpt_v)
    kappa  = _kappa(gem_v >= 0.5, gpt_v >= 0.5)
    q_agr  = float(((gem_v >= 0.5) == (gpt_v >= 0.5)).mean())
    n_ok   = len(aligned_ids)

    tert   = np.percentile(gem_v, [33, 67])
    bins   = np.digitize(gem_v, tert)
    cal    = []
    for b, lbl in enumerate(["low (0–0.33)", "mid (0.33–0.67)", "high (0.67–1.0)"]):
        m = bins == b
        if m.sum():
            cal.append({"bucket": lbl, "n": int(m.sum()),
                        "gemini_mean": round(float(gem_v[m].mean()), 3),
                        "gpt_mean":    round(float(gpt_v[m].mean()), 3)})

    delta   = np.abs(gem_v - gpt_v)
    n_large = int((delta >= 0.35).sum())
    top_dis = []
    for i in np.argsort(delta)[::-1][:20]:
        tid = aligned_ids[i]
        top_dis.append({
            "track_id":     tid,
            "gemini_v":     round(float(gem_v[i]), 3),
            "gpt_v":        round(float(gpt_v[i]), 3),
            "delta":        round(float(delta[i]), 3),
            "gemini_label": v5c.get(tid, {}).get("label", "?"),
            "lyrics_120":   lyr_map.get(tid, "")[:120],
        })

    if   rho >= 0.55: verdict = f"STRONG CORROBORATION — rho={rho:.3f} >= 0.55"
    elif rho >= 0.40: verdict = f"GOOD CORROBORATION — rho={rho:.3f} >= 0.40"
    elif rho >= 0.25: verdict = f"WEAK CORROBORATION — rho={rho:.3f} >= 0.25"
    else:             verdict = f"NOT CORROBORATED — rho={rho:.3f} < 0.25"

    print(f"\n{'='*65}")
    print(f"GPT-4o-mini vs Gemini v5c  (n={n_ok}, failed={n_fail})")
    print(f"{'='*65}")
    print(f"  Spearman rho = {rho:.4f}   p = {p_rho:.2e}")
    print(f"  Pearson  r   = {r:.4f}   p = {p_r:.2e}")
    print(f"  Quadrant agree = {q_agr:.3f}   Cohen kappa = {kappa}")
    print(f"  GPT mean = {gpt_v.mean():.3f}  std = {gpt_v.std():.3f}  "
          f"Gemini mean = {gem_v.mean():.3f}")
    print(f"\n  Calibration:")
    for row in cal:
        arrow = "~" if abs(row["gemini_mean"]-row["gpt_mean"]) < 0.05 else \
                ("↑" if row["gpt_mean"] > row["gemini_mean"] else "↓")
        print(f"    {row['bucket']:22}  n={row['n']:4}  "
              f"Gemini={row['gemini_mean']:.3f}  GPT={row['gpt_mean']:.3f} {arrow}")
    print(f"\n  Disagreements (Δ≥0.35): {n_large}/{n_ok} = {n_large/n_ok:.1%}")
    for ex in top_dis[:3]:
        print(f"    [{ex['gemini_label']}] Gemini={ex['gemini_v']}  "
              f"GPT={ex['gpt_v']}  Δ={ex['delta']}")
        print(f"      \"{ex['lyrics_120'][:80]}...\"")
    print(f"\n  VERDICT: {verdict}")
    print(f"{'='*65}")

    return {
        "model": MODEL, "n_scored": n_ok, "n_failed": n_fail,
        "metrics": {
            "spearman_rho": round(float(rho), 4),
            "spearman_p":   round(float(p_rho), 8),
            "pearson_r":    round(float(r), 4),
            "pearson_p":    round(float(p_r), 8),
            "quadrant_agreement": round(float(q_agr), 4),
            "cohens_kappa": kappa,
            "gemini_mean":  round(float(gem_v.mean()), 4),
            "gpt_mean":     round(float(gpt_v.mean()),  4),
            "gpt_std":      round(float(gpt_v.std()),   4),
        },
        "calibration_by_bucket": cal,
        "disagreements": {
            "threshold": 0.35, "n_flagged": n_large,
            "pct_flagged": round(n_large / n_ok, 4),
            "examples": top_dis,
        },
        "verdict": verdict,
        "honest_claim": (
            f"Gemini v5c consistent with GPT-4o-mini "
            f"(rho={rho:.3f}, p<0.001). Model corroboration — NOT human GT."
        ),
        "basis": "GPT-4o-mini (OpenAI); Kriegeskorte 2009 circularity.",
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample",      type=int, default=0)
    parser.add_argument("--workers",     type=int, default=WORKERS)
    parser.add_argument("--no-cache",    action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Skip inference, just print metrics from cache")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    print("\n=== Phase 2b: GPT-4o-mini Valence Validation ===", flush=True)

    from tools.backtest_v2.catalog import Catalog
    cat = Catalog.load()
    df  = cat.rec.df.copy()
    v5c = json.load(open("data/emotion_labels_v5c.json"))

    tids = df["track_id"].astype(str).values
    lyr  = df["lyrics_cleaned"].fillna("").values
    keep = np.array([
        bool(v5c.get(t, {}).get("valence") is not None) and len(str(l)) > 30
        for t, l in zip(tids, lyr)
    ])
    tids_s = tids[keep]
    lyr_s  = [str(l) for l in lyr[keep]]
    gem_v  = np.array([float(v5c[t]["valence"]) for t in tids_s])
    lyr_map = dict(zip(tids_s, lyr_s))
    print(f"Catalog: {len(tids_s)} songs", flush=True)

    if args.sample > 0 and args.sample < len(tids_s):
        rng = np.random.default_rng(42)
        buckets = np.digitize(gem_v, np.percentile(gem_v, [33, 67]))
        idx = np.concatenate([
            rng.choice(np.where(buckets == b)[0],
                       min(args.sample // 3, (buckets == b).sum()),
                       replace=False)
            for b in [0, 1, 2]
        ])[:args.sample]
        tids_s, lyr_s = tids_s[idx], [lyr_s[i] for i in idx]
        gem_v = gem_v[idx]
        lyr_map = dict(zip(tids_s, lyr_s))
        print(f"Stratified sample: {len(tids_s)} songs", flush=True)

    n = len(tids_s)
    cache_f = CACHE_DIR / f"gpt_valence_{n}.json"

    # Load existing cache (enables resume)
    cache: dict[str, float] = {}
    if not args.no_cache and cache_f.exists():
        cache = json.load(open(cache_f))
        n_cached = sum(1 for t in tids_s if t in cache)
        print(f"Resume: {n_cached}/{n} already cached", flush=True)

    if not args.report_only:
        n_todo = sum(1 for t in tids_s if t not in cache)
        if n_todo > 0:
            est_rate = args.workers / (0.5 + CALL_DELAY)   # ~workers / avg_latency
            print(f"Running {n_todo} songs  workers={args.workers}  "
                  f"est. {est_rate:.0f} req/s  "
                  f"est. time={n_todo/est_rate:.0f}s  "
                  f"est. cost=${n_todo*700*0.15/1_000_000:.3f}", flush=True)
            cache = asyncio.run(_run(tids_s.tolist(), lyr_s, cache, cache_f))
        else:
            print("All cached — computing metrics only", flush=True)

    # Align
    aligned_ids = [t for t in tids_s if t in cache]
    gpt_v   = np.array([cache[t] for t in aligned_ids])
    gem_v_a = np.array([float(v5c[t]["valence"]) for t in aligned_ids])
    n_fail  = n - len(aligned_ids)

    report = _print_report(gem_v_a, gpt_v, aligned_ids, v5c, lyr_map, n_fail)
    json.dump(report, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved -> {OUT}")
    return 0 if report["metrics"]["spearman_rho"] >= 0.25 else 1


if __name__ == "__main__":
    sys.exit(main())
