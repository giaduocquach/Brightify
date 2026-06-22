"""Measure serving latency of the recommendation engine — the numbers in the thesis
Table 4.8. Times the in-process engine methods only (the API path minus network + JSON
serialization), exactly as described in §4.8.1: at serving there is no model inference,
just matrix products + ranking over the precomputed 5138×D feature matrices.

Reports engine load (one-time) + per-query median / p95 / p99 for the three query types:
  - recommend by 1 colour      (UC02)
  - recommend similar song     (UC01)
  - two-colour journey         (UC02 journey)

Run: python -m tools.bench_latency [--iters 1000] [--warmup 20]
"""
from __future__ import annotations
import argparse, os, platform, sys, time
import numpy as np

os.environ.setdefault("SKIP_PHOBERT_LOAD", "True")   # PhoBERT is never invoked at serving
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

# Representative inputs (from the 12-colour palette + a mid-catalogue song index)
COLOR_1 = ["#BE0032"]                 # one colour
COLOR_2 = ["#BE0032", "#1F6FB2"]      # two-colour journey
SONG_IDX = 100                         # a valid catalogue index


def _bench(fn, iters: int, warmup: int):
    for _ in range(warmup):
        fn()
    ts = np.empty(iters)
    for i in range(iters):
        t = time.perf_counter()
        fn()
        ts[i] = (time.perf_counter() - t) * 1000.0   # ms
    return np.median(ts), np.percentile(ts, 95), np.percentile(ts, 99), float(ts.mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--song-idx", type=int, default=SONG_IDX)
    args = ap.parse_args()

    from core.recommendation_engine import get_recommender
    t0 = time.perf_counter()
    rec = get_recommender()
    load_s = time.perf_counter() - t0

    cases = [
        ("Recommend by 1 colour (UC02)", lambda: rec.recommend_by_colors(COLOR_1, top_k=10)),
        ("Recommend similar song (UC01)", lambda: rec.recommend_by_song(args.song_idx, top_k=10)),
        ("Two-colour journey", lambda: rec.recommend_by_colors(COLOR_2, top_k=10)),
    ]

    print(f"\n=== Serving latency  (machine: {platform.platform()}, "
          f"py{platform.python_version()}; iters={args.iters}, warmup={args.warmup}) ===")
    print(f"  Engine load (one-time): {load_s:.2f} s\n")
    print(f"  {'Query type':<34}{'median':>10}{'p95':>10}{'p99':>10}{'mean':>10}")
    print("  " + "-" * 74)
    for name, fn in cases:
        med, p95, p99, mean = _bench(fn, args.iters, args.warmup)
        print(f"  {name:<34}{med:>8.2f}ms{p95:>8.2f}ms{p99:>8.2f}ms{mean:>8.2f}ms")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
