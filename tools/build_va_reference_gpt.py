"""Phase 1 (V32) — GPT Valence+Arousal REFERENCE for backtest only.

Builds an independent V-A reference over the catalog using a single LLM provider
(OpenAI, per product decision). This reference is used ONLY offline: convergent
validity (Phase 2), cross-corpus transfer (Phase 2), and as the optimization
target to re-tune the SERVED non-LLM blend (Phase 3). The serving path never
calls an LLM.

Design (reuses tools/valence_gpt_validate.py async pattern):
  - one call/song → JSON {"valence":0-10, "arousal":0-10} (V and A judged INDEPENDENTLY)
  - JSON mode, temp 0, Semaphore(8), 0.15s/worker delay, checkpoint every 100
  - resume-safe per-(model) cache; measures actual token cost for the gpt-4o<$4 rule

Usage:
  python -m tools.build_va_reference_gpt --probe 50 --model gpt-4o     # cost probe
  python -m tools.build_va_reference_gpt --model gpt-4o-mini           # full catalog (bulk)
  python -m tools.build_va_reference_gpt --subset 600 --model gpt-4o   # cross-model subset
  python -m tools.build_va_reference_gpt --retest 100 --model gpt-4o-mini  # test-retest
  python -m tools.build_va_reference_gpt --report                      # agreement/ICC only
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

CACHE_DIR = Path("var/runtime/backtest/cache")
OUT_MAIN  = "data/va_reference_gpt.json"
OUT_REPORT = "var/runtime/backtest/reports/va_reference_gpt.json"
MAX_CHARS = 1200
WORKERS   = 8
CALL_DELAY = 0.15
SAVE_EVERY = 100

# Approx OpenAI pricing (USD / 1M tokens), 2026 — used only for the <$4 decision rule.
PRICING = {
    "gpt-4o":      {"in": 2.50, "out": 10.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
}

SYSTEM = """Bạn đánh giá CẢM XÚC của lời bài hát tiếng Việt theo HAI trục ĐỘC LẬP.

VALENCE (0-10) = mức độ tích cực/vui của cảm xúc:
  0-2 rất buồn (chia tay, tuyệt vọng) · 3-4 buồn (nhớ nhung, cô đơn) ·
  5 trung tính/lẫn lộn · 6-7 tích cực (hi vọng, ấm áp) · 8-10 rất vui (hân hoan, lễ mừng)

AROUSAL (0-10) = mức năng lượng/cường độ cảm xúc, KHÔNG liên quan vui hay buồn:
  0-2 rất tĩnh (ballad chậm, ru) · 3-4 nhẹ nhàng (acoustic tâm tình) ·
  5 vừa phải · 6-7 sôi nổi (pop nhanh) · 8-10 rất mạnh (EDM, rock, rap dồn dập, cao trào)

QUAN TRỌNG: hai trục độc lập. Bài chia tay gào thét giận dữ = valence THẤP nhưng arousal CAO.
Bài ru con hạnh phúc = valence CAO nhưng arousal THẤP.

Lưu ý văn hóa: cưới (kiệu hoa, cô dâu, trăm năm) valence 8-9; Tết/lễ hội valence 7-9;
lyrics gần như toàn tiếng Anh → valence 5, arousal 5 (không đủ ngữ cảnh).

Trả về DUY NHẤT một JSON: {"valence": <0-10 số nguyên>, "arousal": <0-10 số nguyên>}"""


def _parse_va(content: str) -> tuple[float, float] | None:
    try:
        o = json.loads(content)
        v = float(np.clip(int(round(float(o["valence"]))) / 10, 0, 1))
        a = float(np.clip(int(round(float(o["arousal"]))) / 10, 0, 1))
        return v, a
    except Exception:
        return None


async def _call(client, sem, model, tid, lyrics, usage):
    text = lyrics[:MAX_CHARS].strip()
    if not text:
        return tid, None
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": text}],
                    max_tokens=30,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                await asyncio.sleep(CALL_DELAY)
                if resp.usage:
                    usage["in"] += resp.usage.prompt_tokens
                    usage["out"] += resp.usage.completion_tokens
                va = _parse_va(resp.choices[0].message.content)
                return tid, va
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "rate" in msg.lower()) and attempt < 3:
                    await asyncio.sleep(3 * (attempt + 1))
                elif attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return tid, None
        return tid, None


async def _run(model, tids, lyrics, cache, cache_f):
    from openai import AsyncOpenAI
    api_key = os.environ.get("OpenAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI_API_KEY not found in .env")
    todo = [(t, l) for t, l in zip(tids, lyrics) if t not in cache]
    if not todo:
        print("  all cached", flush=True)
        return cache, {"in": 0, "out": 0}
    client = AsyncOpenAI(api_key=api_key)
    sem = asyncio.Semaphore(WORKERS)
    usage = {"in": 0, "out": 0}
    total, n_done, t0, lock = len(todo), 0, time.time(), asyncio.Lock()

    async def _task(tid, lyr):
        nonlocal n_done
        tid_r, va = await _call(client, sem, model, tid, lyr, usage)
        async with lock:
            if va is not None:
                cache[tid_r] = {"valence": va[0], "arousal": va[1]}
            n_done += 1
            if n_done % SAVE_EVERY == 0 or n_done == total:
                cache_f.parent.mkdir(parents=True, exist_ok=True)
                json.dump(cache, open(cache_f, "w"), ensure_ascii=False)
                el = time.time() - t0
                rate = n_done / el if el > 0 else 1
                print(f"  {len(cache)}/{len(tids)} done  {rate:.1f} req/s  "
                      f"ETA {(total-n_done)/rate:.0f}s", flush=True)

    await asyncio.gather(*[_task(t, l) for t, l in todo])
    await client.close()
    return cache, usage


def _cost(usage, model):
    p = PRICING.get(model, PRICING["gpt-4o-mini"])
    return usage["in"] / 1e6 * p["in"] + usage["out"] / 1e6 * p["out"]


def _icc21(x, y):
    """ICC(2,1) two-way random, single rater — test-retest reliability."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 3:
        return float("nan")
    M = np.column_stack([x, y])
    grand = M.mean()
    ms_r = 2 * ((M.mean(axis=1) - grand) ** 2).sum() / (n - 1)            # between-subject
    ms_c = n * ((M.mean(axis=0) - grand) ** 2).sum() / 1                  # between-rater (k-1=1)
    ms_e = (((M - M.mean(axis=1, keepdims=True) - M.mean(axis=0, keepdims=True) + grand) ** 2).sum()
            / (n - 1))
    denom = ms_r + ms_c / n + (2 - 1) * ms_e + 1e-12
    return float((ms_r - ms_e) / (denom if denom != 0 else 1e-12))


def _load_catalog():
    import pandas as pd
    import config as cfg
    df = pd.read_csv(cfg.PROCESSED_FILE)
    tids = df["track_id"].astype(str).values
    lyr = df["lyrics_cleaned"].fillna("").astype(str).values
    keep = np.array([len(l) > 30 for l in lyr])
    return tids[keep], [str(l) for l in lyr[keep]]


def _stratified_idx(tids, n, seed=42):
    """Stratify by existing v6c valence so the subset spans the V range."""
    rng = np.random.default_rng(seed)
    try:
        v6c = json.load(open("data/emotion_labels_v6c.json"))
        vals = np.array([float(v6c.get(t, {}).get("valence", 0.5)) for t in tids])
        buckets = np.digitize(vals, np.percentile(vals, [33, 67]))
        idx = np.concatenate([rng.choice(np.where(buckets == b)[0],
                                          min(n // 3, int((buckets == b).sum())), replace=False)
                              for b in [0, 1, 2]])
        return idx[:n]
    except Exception:
        return rng.choice(len(tids), min(n, len(tids)), replace=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--probe", type=int, default=0, help="cost-probe N songs, project full cost")
    ap.add_argument("--subset", type=int, default=0, help="run a stratified N-song subset")
    ap.add_argument("--retest", type=int, default=0, help="re-run N songs into a retest cache (ICC)")
    ap.add_argument("--report", action="store_true", help="agreement/ICC from caches only")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tids, lyr = _load_catalog()
    print(f"Catalog (lyrics>30 chars): {len(tids)} songs", flush=True)

    def cache_path(model, tag=""):
        return CACHE_DIR / f"va_ref_{model}{tag}.json"

    if args.report:
        return _report(tids)

    # Select working set
    if args.probe:
        idx = _stratified_idx(tids, args.probe)
        wt, wl, tag = tids[idx], [lyr[i] for i in idx], "_probe"
    elif args.subset:
        idx = _stratified_idx(tids, args.subset)
        wt, wl, tag = tids[idx], [lyr[i] for i in idx], "_subset"
    elif args.retest:
        idx = _stratified_idx(tids, args.retest, seed=7)
        wt, wl, tag = tids[idx], [lyr[i] for i in idx], "_retest"
    else:
        wt, wl, tag = tids, lyr, ""

    cache_f = cache_path(args.model, tag)
    cache = json.load(open(cache_f)) if cache_f.exists() else {}
    print(f"Model={args.model} tag='{tag}' set={len(wt)} cached={sum(1 for t in wt if t in cache)}", flush=True)

    cache, usage = asyncio.run(_run(args.model, list(wt), wl, cache, cache_f))
    cost = _cost(usage, args.model)
    n_new = sum(usage.values()) and len([t for t in wt if t in cache])
    print(f"\nUsage: in={usage['in']} out={usage['out']} tokens  cost=${cost:.4f}", flush=True)

    if args.probe and usage["in"] > 0:
        n_probe = max(1, len([t for t in wt if t in cache]))
        per_song = cost / n_probe
        full = per_song * len(tids)
        print(f"\n=== COST PROBE ({args.model}) ===")
        print(f"  per-song ≈ ${per_song:.5f}  → full catalog ({len(tids)}) ≈ ${full:.2f}")
        print(f"  RULE: use gpt-4o for all iff < $4  →  {'gpt-4o (full)' if full < 4 else 'gpt-4o-mini (bulk) + gpt-4o subset'}")
        return 0

    # Full / subset run: write the main reference JSON when this is the bulk model
    if tag in ("", "_subset"):
        out = cache_path(args.model, tag)
        if tag == "":
            json.dump(cache, open(OUT_MAIN, "w"), ensure_ascii=False, indent=1)
            print(f"  reference -> {OUT_MAIN} ({len(cache)} songs)")
    return _report(tids)


def _report(tids) -> int:
    """Cross-model (4o vs mini) agreement + test-retest ICC from whatever caches exist."""
    import glob
    caches = {Path(p).stem: json.load(open(p)) for p in glob.glob(str(CACHE_DIR / "va_ref_*.json"))}
    rep = {"caches": {k: len(v) for k, v in caches.items()}}
    print(f"\n=== VA REFERENCE REPORT ===\n  caches: {rep['caches']}")

    def common(a, b, dim):
        ks = [t for t in a if t in b]
        return (np.array([a[t][dim] for t in ks]), np.array([b[t][dim] for t in ks]), ks)

    # cross-model: gpt-4o subset vs gpt-4o-mini (on overlap)
    mini = caches.get("va_ref_gpt-4o-mini")
    o4 = caches.get("va_ref_gpt-4o_subset") or caches.get("va_ref_gpt-4o")
    if mini and o4:
        rep["cross_model"] = {}
        for dim in ("valence", "arousal"):
            x, y, ks = common(o4, mini, dim)
            if len(ks) >= 5:
                rho = float(ss.spearmanr(x, y).correlation)
                icc = _icc21(x, y)
                rep["cross_model"][dim] = {"n": len(ks), "spearman": round(rho, 4),
                                            "icc21": round(icc, 4)}
                print(f"  cross-model {dim}: n={len(ks)} ρ={rho:.3f} ICC={icc:.3f}")

    # test-retest: any model main cache vs its _retest cache
    for m in ("gpt-4o-mini", "gpt-4o"):
        main_c, re_c = caches.get(f"va_ref_{m}"), caches.get(f"va_ref_{m}_retest")
        if main_c and re_c:
            rep.setdefault("test_retest", {})[m] = {}
            for dim in ("valence", "arousal"):
                x, y, ks = common(main_c, re_c, dim)
                if len(ks) >= 3:
                    icc = _icc21(x, y)
                    rep["test_retest"][m][dim] = {"n": len(ks), "icc21": round(icc, 4)}
                    print(f"  test-retest {m} {dim}: n={len(ks)} ICC={icc:.3f}")

    Path(OUT_REPORT).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(OUT_REPORT, "w"), ensure_ascii=False, indent=2)
    print(f"  saved -> {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
