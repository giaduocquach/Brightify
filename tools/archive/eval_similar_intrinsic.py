"""Human-free intrinsic evaluation for recommend_by_song.

Measures property metrics (no ground-truth labels needed) across several
weight configurations and reports Δ vs baseline.

Metrics (all human-free):
  tempo_coherence   — recs have similar BPM to each other (high = good)
  mood_coherence    — recs cluster in V-A space (high = good)
  ild_audio         — mean pairwise diversity in audio space (balance)
  ild_lyrics        — mean pairwise diversity in lyrics space (balance)
  ild_va            — mean pairwise diversity in V-A space
  calibration_err   — KL(seed_emotion ‖ recs_emotion) (low = good)
  same_artist@K     — fraction same-artist in top-K (low = good)
  symmetry          — Jaccard A→B / B→A overlap (high = good)
  self_consistency  — Jaccard(nn(seed), nn(seed+noise)) in MERT space (high = good)
  coverage          — fraction of catalog surfaced (global, high = good)
  artist_gini       — Gini of artist exposure (global, low = good)

Usage:
    python -m tools.eval_similar_intrinsic [--n-seeds N] [--top-k K] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Sequence

import numpy as np

TOP_K    = 10
N_SEEDS  = 80     # stratified over fused_emotion
SEED_RNG = 42
NOISE_STD = 0.02  # Gaussian noise for self-consistency test

# Weight configs to compare:
# [timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert]
CONFIGS: Dict[str, List[float]] = {
    "old_baseline":          [0.0,  0.0,  0.0,  0.4991, 0.0315, 0.1042, 0.0300, 0.3352],
    "current (v2)":          [0.0,  0.0,  0.0,  0.15,   0.10,   0.0,    0.0,    0.75  ],
    # Sensitivity+CV candidate: decrease lyrics, increase va+mert — ↑3↓0 on held-out seeds
    "candidate [0.82/0.06/0.12]": [0.0, 0.0,  0.0,  0.06,   0.12,   0.0,    0.0,    0.82  ],
}

REPORT_DIR = "var/runtime/backtest/reports"


def _stratified_seeds(df, n: int, rng: np.random.Generator) -> List[int]:
    if "fused_emotion" not in df.columns:
        return rng.choice(len(df), size=min(n, len(df)), replace=False).tolist()
    groups = df.groupby("fused_emotion").indices
    per_g  = max(1, n // len(groups))
    seeds: List[int] = []
    for idxs in groups.values():
        seeds.extend(int(i) for i in rng.choice(idxs, size=min(per_g, len(idxs)), replace=False))
    remaining = [i for i in range(len(df)) if i not in set(seeds)]
    if len(seeds) < n and remaining:
        seeds.extend(int(i) for i in rng.choice(remaining, size=min(n - len(seeds), len(remaining)), replace=False))
    return seeds[:n]


def _self_consistency(cat, seed_idx: int, w: list, top_k: int, rng: np.random.Generator) -> float:
    """Jaccard overlap between nn(seed) and nn(seed + small MERT noise).

    Higher = more stable / meaningful similarity function in audio space.
    Falls back to 0.0 if MERT matrix not available.
    """
    if cat.rec.mert_matrix is None:
        return 0.0
    recs_a = set(cat.recommend_by_song(seed_idx, top_k=top_k, weights=w))
    if not recs_a:
        return 0.0
    # Add Gaussian noise to seed MERT embedding, re-normalise, re-rank
    orig = cat.rec.mert_matrix[seed_idx].astype(float).copy()
    noise = rng.normal(0, NOISE_STD, size=orig.shape)
    noisy = orig + noise
    nrm = float(np.linalg.norm(noisy))
    if nrm < 1e-9:
        return 0.0
    noisy /= nrm
    # Cosine similarity against MERT matrix → top-K excluding seed
    sims = (cat.rec.mert_matrix.astype(float) @ noisy)
    sims[seed_idx] = -2.0
    top_noisy = set(int(i) for i in np.argsort(sims)[::-1][:top_k])
    inter = len(recs_a & top_noisy)
    union = len(recs_a | top_noisy)
    return inter / union if union > 0 else 0.0


def eval_config(cat, seeds: List[int], w: list, top_k: int, quiet: bool) -> dict:
    from tools.backtest_v2.metrics.property import (
        ild_audio, ild_lyrics, ild_va,
        mood_coherence, tempo_coherence,
        calibration_error, serendipity_proxy,
        same_artist_at_k, similar_song_symmetry,
        catalog_coverage, artist_gini,
    )

    rng = np.random.default_rng(SEED_RNG)
    per_query: Dict[str, List[float]] = {
        k: [] for k in ["tempo_coh", "mood_coh", "ild_audio", "ild_lyrics",
                         "ild_va", "calib_err", "serendipity",
                         "same_artist", "self_consist"]
    }
    all_recs: List[List[int]] = []

    for seed_idx in seeds:
        recs = cat.recommend_by_song(seed_idx, top_k=top_k, weights=w)
        if not recs:
            continue
        all_recs.append(recs)
        per_query["tempo_coh"].append(tempo_coherence(recs, cat))
        per_query["mood_coh"].append(mood_coherence(recs, cat))
        per_query["ild_audio"].append(ild_audio(recs, cat))
        per_query["ild_lyrics"].append(ild_lyrics(recs, cat))
        per_query["ild_va"].append(ild_va(recs, cat))
        per_query["calib_err"].append(calibration_error(recs, seed_idx, cat))
        per_query["serendipity"].append(serendipity_proxy(recs, seed_idx, cat))
        per_query["same_artist"].append(same_artist_at_k(recs, seed_idx, cat))
        per_query["self_consist"].append(_self_consistency(cat, seed_idx, w, top_k, rng))

    # Symmetry (needs recommend_fn)
    def _rec_fn(idx, k):
        return cat.recommend_by_song(idx, top_k=k, weights=w)

    sym = similar_song_symmetry(_rec_fn, seeds, top_k)

    # Global metrics
    cov  = catalog_coverage(all_recs, cat.n)
    gini = artist_gini(all_recs, cat)

    result = {k: float(np.mean(v)) if v else 0.0 for k, v in per_query.items()}
    result["symmetry"]  = float(sym)
    result["coverage"]  = float(cov)
    result["artist_gini"] = float(gini)
    result["n_seeds"]   = len(all_recs)
    return result


def print_table(results: Dict[str, dict], top_k: int) -> None:
    METRICS = [
        # (key, label, higher_is_better)
        ("tempo_coh",   "TempoCoherence ", True),
        ("mood_coh",    "MoodCoherence  ", True),
        ("self_consist","SelfConsistency", True),
        ("symmetry",    "Symmetry       ", True),
        ("coverage",    "Coverage       ", True),
        ("ild_audio",   "ILD_audio      ", None),  # balance
        ("ild_lyrics",  "ILD_lyrics     ", None),
        ("ild_va",      "ILD_va         ", None),
        ("calib_err",   "CalibError     ", False),
        ("same_artist", "SameArtist@K   ", False),
        ("serendipity", "Serendipity    ", None),
        ("artist_gini", "ArtistGini     ", False),
    ]

    names = list(results.keys())
    base_name = names[0]
    base = results[base_name]

    col_w = 14
    header = f"{'Metric':<18}" + "".join(f"{n[:col_w]:>{col_w}}" for n in names)
    print("\n" + "=" * (18 + col_w * len(names)))
    print(f"  INTRINSIC EVAL  top_k={top_k}  n_seeds={base['n_seeds']}")
    print("=" * (18 + col_w * len(names)))
    print(header)
    print("-" * (18 + col_w * len(names)))

    for key, label, hib in METRICS:
        row = f"{label:<18}"
        base_v = base.get(key, 0.0)
        for name in names:
            v = results[name].get(key, 0.0)
            delta = v - base_v
            if name == base_name:
                row += f"{v:>{col_w}.4f}"
            else:
                sign = "+" if delta >= 0 else ""
                marker = ""
                if hib is True  and delta >  0.005: marker = "✓"
                if hib is True  and delta < -0.005: marker = "✗"
                if hib is False and delta < -0.005: marker = "✓"
                if hib is False and delta >  0.005: marker = "✗"
                row += f"{v:>9.4f}{sign}{delta:.3f}{marker:>2}"
        print(row)

    print("-" * (18 + col_w * len(names)))
    # Winner row: count ✓ per config
    wins = {n: 0 for n in names}
    for key, _, hib in METRICS:
        if hib is None:
            continue
        base_v = base.get(key, 0.0)
        best = None
        for n in names[1:]:
            v = results[n].get(key, 0.0)
            d = v - base_v
            if hib is True  and d > 0.005: wins[n] += 1
            if hib is False and d < -0.005: wins[n] += 1
    print(f"{'Improvements vs base':<18}" + "".join(
        f"{'—':>{col_w}}" if n == base_name else f"{wins[n]:>{col_w}}" for n in names
    ))
    print("=" * (18 + col_w * len(names)) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds",    type=int, default=N_SEEDS)
    ap.add_argument("--top-k",      type=int, default=TOP_K)
    ap.add_argument("--quiet",      action="store_true")
    ap.add_argument("--save",       action="store_true", help="save results JSON")
    ap.add_argument("--multilayer", action="store_true",
                    help="A/B test: add 'multilayer' config that swaps MERT matrix "
                         "with data/mert_embeddings_multilayer.npy")
    ap.add_argument("--proj", action="store_true",
                    help="A/B test: add 'proj' configs using SimCSE metric head "
                         "projected embeddings (128-dim)")
    ap.add_argument("--vnsbert", action="store_true",
                    help="A/B test lyrics: swap embeddings_normalized with "
                         "VN Sentence-BERT (data/vnsbert_embeddings.npy)")
    ap.add_argument("--desc", action="store_true",
                    help="A/B test: use description embeddings (TF-IDF keywords + emotion) "
                         "instead of raw lyrics (data/description_embeddings.npy)")
    args = ap.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from tools.backtest_v2.catalog import Catalog
    print("[intrinsic] Loading catalog…")
    cat = Catalog.load()
    df  = cat.df

    rng   = np.random.default_rng(SEED_RNG)
    seeds = _stratified_seeds(df, args.n_seeds, rng)
    print(f"[intrinsic] {len(seeds)} seeds  top_k={args.top_k}")

    import config as cfg

    # Optionally inject multilayer MERT matrix for A/B comparison
    configs = dict(CONFIGS)
    # Env-injected custom weight configs (for fair per-model weight sweeps), JSON: {name: [8 weights]}
    _extra = os.environ.get("BRIGHTIFY_EVAL_CONFIGS")
    if _extra:
        configs.update({k: [float(x) for x in v] for k, v in json.loads(_extra).items()})
    ml_matrix = None
    if args.multilayer:
        ml_path = cfg.MERT_EMBEDDINGS_MULTILAYER_FILE
        if os.path.exists(ml_path):
            ml_raw = np.load(ml_path).astype(np.float32)
            norms  = np.linalg.norm(ml_raw, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            ml_matrix = ml_raw / norms
            print(f"[intrinsic] multilayer embeddings loaded: {ml_matrix.shape}")
            # Add multilayer variant using same weights as current v2
            configs["multilayer (v2 weights)"] = [0.0, 0.0, 0.0, 0.15, 0.10, 0.0, 0.0, 0.75]
            configs["multilayer (mert_only)"]   = [0.0, 0.0, 0.0, 0.0,  0.0,  0.0, 0.0, 1.0]
        else:
            print(f"[intrinsic] WARNING: multilayer file not found: {ml_path}")
            print("  Run: python -m tools.extract_mert_multilayer")

    # Optionally inject SimCSE projected embeddings (128-dim)
    if args.proj:
        for proj_key, proj_path in [
            ("proj_single",        cfg.MERT_PROJ_EMBEDDINGS_FILE),
            ("proj_ml_nova",       "data/mert_proj_embeddings_multilayer_nova.npy"),
            ("proj_ml_va",         cfg.MERT_PROJ_EMBEDDINGS_MULTILAYER_FILE),
        ]:
            if os.path.exists(proj_path):
                praw = np.load(proj_path).astype(np.float32)
                pnrm = np.linalg.norm(praw, axis=1, keepdims=True)
                pnrm[pnrm == 0] = 1.0
                configs[proj_key] = [0.0, 0.0, 0.0, 0.15, 0.10, 0.0, 0.0, 0.75]
                # stash matrix so we can swap it in the loop below
                configs[f"__proj_matrix_{proj_key}"] = praw / pnrm

    # Description embeddings swap (--desc flag)
    if args.desc:
        desc_path = "data/description_embeddings.npy"
        if os.path.exists(desc_path):
            draw = np.load(desc_path).astype(np.float32)
            dnrm = np.linalg.norm(draw, axis=1, keepdims=True); dnrm[dnrm==0]=1
            configs["desc (6%)"]  = [0.0, 0.0, 0.0, 0.06, 0.12, 0.0, 0.0, 0.82]
            configs["desc (15%)"] = [0.0, 0.0, 0.0, 0.15, 0.10, 0.0, 0.0, 0.75]
            configs["desc (20%)"] = [0.0, 0.0, 0.0, 0.20, 0.10, 0.0, 0.0, 0.70]
            configs["__desc_matrix"] = draw / dnrm
            print(f"[intrinsic] description embeddings loaded: {draw.shape}  avg_cos≈0.206")
        else:
            print(f"[intrinsic] WARNING: {desc_path} not found — run extract_description_embeddings.py")

    # VN Sentence-BERT lyrics swap
    vnsbert_matrix = None
    orig_lyrics_emb = cat.rec.embeddings_normalized
    if args.vnsbert:
        vnsbert_path = "data/vnsbert_embeddings.npy"
        if os.path.exists(vnsbert_path):
            vraw = np.load(vnsbert_path).astype(np.float32)
            vnrm = np.linalg.norm(vraw, axis=1, keepdims=True)
            vnrm[vnrm == 0] = 1.0
            vnsbert_matrix = vraw / vnrm
            print(f"[intrinsic] VN-SBERT lyrics loaded: {vnsbert_matrix.shape}")
            # Add VN-SBERT variant: same weights as current v2 but with better lyrics emb
            configs["vnsbert (v2 weights)"] = [0.0, 0.0, 0.0, 0.15, 0.10, 0.0, 0.0, 0.75]
        else:
            print(f"[intrinsic] WARNING: {vnsbert_path} not found — run extract_vnsbert_embeddings.py")

    results: Dict[str, dict] = {}
    for name, w in configs.items():
        t0 = time.time()
        print(f"[intrinsic] evaluating '{name}'…", flush=True)
        # Skip internal stash entries
        if name.startswith("__"):
            continue
        # Swap lyrics embeddings for description configs
        desc_mat = configs.get("__desc_matrix")
        if desc_mat is not None and name.startswith("desc"):
            cat.rec.embeddings_normalized = desc_mat
        else:
            cat.rec.embeddings_normalized = orig_lyrics_emb
        # Swap lyrics embeddings for VN-SBERT configs
        if vnsbert_matrix is not None and name.startswith("vnsbert"):
            cat.rec.embeddings_normalized = vnsbert_matrix
        else:
            cat.rec.embeddings_normalized = orig_lyrics_emb
        # Swap MERT matrix for multilayer / projected configs
        orig_mert = None
        swap_matrix = None
        if ml_matrix is not None and name.startswith("multilayer"):
            swap_matrix = ml_matrix
        proj_key = f"__proj_matrix_{name}"
        if proj_key in configs:
            swap_matrix = configs[proj_key]
        if swap_matrix is not None:
            orig_mert = cat.rec.mert_matrix
            cat.rec.mert_matrix = swap_matrix
        results[name] = eval_config(cat, seeds, w, args.top_k, args.quiet)
        if orig_mert is not None:
            cat.rec.mert_matrix = orig_mert
        elapsed = time.time() - t0
        print(f"           done in {elapsed:.1f}s")

    # Restore original lyrics embeddings
    cat.rec.embeddings_normalized = orig_lyrics_emb

    print_table(results, args.top_k)

    # Qualitative spot-check: print top-5 recs for 3 seeds × top config
    best_config = max((k for k in configs if not k.startswith("__")), key=lambda n: (
        results[n]["tempo_coh"] + results[n]["mood_coh"] + results[n]["self_consist"]
        - results[n]["calib_err"] - results[n]["same_artist"]
    ) if n != "baseline (current)" else -9999)
    print(f"Top config by composite score: '{best_config}'")
    print("\n--- Spot-check: top-5 recs for 3 seeds ---")
    for seed_idx in seeds[:3]:
        seed_name = str(df.iloc[seed_idx].get("track_name", seed_idx))
        seed_tempo = float(cat.tempo[seed_idx])
        seed_mood  = str(df.iloc[seed_idx].get("fused_emotion", "?"))
        print(f"\nSeed: '{seed_name}' | tempo={seed_tempo:.0f} | mood={seed_mood}")
        for cname in ["baseline (current)", best_config]:
            w = CONFIGS[cname]
            recs = cat.recommend_by_song(seed_idx, top_k=5, weights=w)
            print(f"  [{cname}]")
            for r in recs:
                row = df.iloc[r]
                print(f"    {str(row.get('track_name',''))[:32]:32s} "
                      f"bpm={cat.tempo[r]:5.0f}  mood={str(row.get('fused_emotion','?'))[:10]:10s}  "
                      f"artist={str(row.get(cat.artist_col,'?') if cat.artist_col else '?')[:20]}")

    if args.save:
        os.makedirs(REPORT_DIR, exist_ok=True)
        out_path = os.path.join(REPORT_DIR, "intrinsic_eval.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"configs": CONFIGS, "results": results}, fh, indent=2, ensure_ascii=False)
        print(f"\n[intrinsic] results saved → {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
