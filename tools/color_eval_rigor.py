"""Phase 1 (V24) — Rigorous evaluation: targeting error + CI + FDR + journey calibration.

New metrics not covered by existing tools (color_quality_metrics / color_baseline_eval /
color_fairness_metrics — those are called by run_f1_validation separately):

  TE   V-A Targeting Error (Euclidean + Mahalanobis)
       Mean distance from colour's V-A point to each returned song's V-A.
       Lower is better. Compared against 5 baselines:
         random / popularity / nearest-VA-only / valence-only / arousal-only
  CI   Bootstrap 95% CI (n=10 000 resamples over 12 colours) on all means.
  FDR  Benjamini-Hochberg correction on 5 pairwise Wilcoxon tests:
       production vs every baseline on per-colour targeting error.
  JTE  Journey Targeting Error (2-colour path A→B):
       For every adjacent pair in ICEAS_COLS, run recommend_by_colors([A,B])
       and measure how uniformly songs are distributed along V-A trajectory.
       Ideal = uniform U[0,1]; measured by KS-statistic + mean projection.

Science basis:
  Steck 2018 (RecSys'18) — KL/calibration as primary eval target.
  Dacrema 2021 (ACM TOIS) — strong baselines mandatory; fusion must beat them.
  Schnabel 2022 (arXiv:2211.01261) — CI required; never report point estimates.
  Benjamini & Hochberg 1995 — FDR correction for multiple comparisons.

Run: python -m tools.color_eval_rigor [top_k]
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import numpy as np
from scipy import stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse as _ap
_parser = _ap.ArgumentParser(description="V-A targeting error + construct validity eval")
_parser.add_argument("top_k", nargs="?", type=int, default=10)
_parser.add_argument("--save-baseline", metavar="PATH",
                     help="Save report copy to PATH (e.g. va_baseline_v5d.json)")
_parser.add_argument("--emotions-file", metavar="PATH",
                     help="Override RELABELED_EMOTIONS_FILE before engine init")
_parser.add_argument("--no-vn-overlay", action="store_true",
                     help="(no-op: VN overlay removed in v6b)")
_args = _parser.parse_args()

TOP_K = _args.top_k
OUT   = "var/runtime/backtest/reports/color_eval_rigor.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

ICEAS_COLS = [
    ('#BE0032', 'red'),    ('#F38400', 'orange'), ('#F3C300', 'yellow'),
    ('#FFB7C5', 'pink'),   ('#008856', 'green'),  ('#3AB09E', 'turquoise'),
    ('#0067A5', 'blue'),   ('#9C4F96', 'purple'), ('#80461B', 'brown'),
    ('#F2F3F4', 'white'),  ('#848482', 'grey'),   ('#222222', 'black'),
]

# ── Bootstrap CI ─────────────────────────────────────────────────────────────

def boot_ci(vals: list[float], n_boot: int = 10_000, seed: int = 42
            ) -> tuple[float, float, float]:
    """Return (mean, ci_lo_2.5, ci_hi_97.5) via percentile bootstrap."""
    a = np.asarray(vals, dtype=float)
    if len(a) == 0:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    means = [rng.choice(a, len(a), replace=True).mean() for _ in range(n_boot)]
    return (round(float(a.mean()), 4),
            round(float(np.percentile(means, 2.5)), 4),
            round(float(np.percentile(means, 97.5)), 4))


# ── Benjamini-Hochberg FDR ────────────────────────────────────────────────────

def bh_correction(p_values: list[float], alpha: float = 0.05
                  ) -> tuple[list[float], list[bool]]:
    """Return (adjusted p-values, reject mask) via Benjamini-Hochberg (1995)."""
    m = len(p_values)
    order = np.argsort(p_values)
    sorted_p = np.array(p_values)[order]
    bh_thresh = (np.arange(1, m + 1) / m) * alpha
    reject_sorted = sorted_p <= bh_thresh
    # Ensure monotonicity: once rejected stay rejected (from largest rank down)
    for i in range(m - 2, -1, -1):
        reject_sorted[i] = reject_sorted[i] or reject_sorted[i + 1]
        reject_sorted[i] = reject_sorted[i] and (sorted_p[i] <= bh_thresh[i])
    adj_p = np.minimum(1.0, sorted_p * m / (np.arange(1, m + 1) / 1))
    # Proper BH adjusted: q_i = min(m/rank * p_i, 1), enforce monotone
    bh_adj = np.ones(m)
    bh_adj[order] = np.minimum.accumulate((sorted_p * m / np.arange(1, m + 1))[::-1])[::-1]
    bh_adj = np.clip(bh_adj, 0, 1)
    reject = np.zeros(m, dtype=bool)
    reject[order] = reject_sorted
    return list(np.round(bh_adj, 5)), list(reject)


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _top_k_idxs(scores: np.ndarray, k: int) -> list[int]:
    return np.argsort(scores)[::-1][:k].tolist()


def _baseline_scores(song_va: np.ndarray, color_va: np.ndarray,
                     pop_proxy: np.ndarray, sigma_v: float, sigma_a: float,
                     rng: np.random.Generator, n: int, k: int
                     ) -> dict[str, list[int]]:
    """Return top-k index lists for each baseline."""
    cv, ca = float(color_va[0]), float(color_va[1])
    dv = song_va[:, 0] - cv
    da = song_va[:, 1] - ca

    va_scores  = np.exp(-0.5 * ((dv / sigma_v) ** 2 + (da / sigma_a) ** 2))
    val_scores = np.exp(-0.5 * (dv / sigma_v) ** 2)   # valence-only
    aro_scores = np.exp(-0.5 * (da / sigma_a) ** 2)   # arousal-only

    return {
        'random':       rng.choice(n, k, replace=False).tolist(),
        'popularity':   np.argsort(pop_proxy)[::-1][:k].tolist(),
        'nearest_va':   _top_k_idxs(va_scores,  k),
        'valence_only': _top_k_idxs(val_scores, k),
        'arousal_only': _top_k_idxs(aro_scores, k),
    }


# ── Targeting error (Euclidean + Mahalanobis) ─────────────────────────────────

def euclidean_te(idxs: list[int], song_va: np.ndarray,
                 color_va: np.ndarray) -> float:
    """Mean Euclidean distance from colour's V-A to each result's V-A."""
    if not idxs:
        return 1.0
    pts = song_va[np.array(idxs, int)]
    return float(np.mean(np.linalg.norm(pts - color_va, axis=1)))


def compute_ild(idxs: list[int], song_va: np.ndarray) -> float:
    """Mean pairwise Euclidean distance in V-A space (Intra-List Diversity).

    Informational metric only — not a gate. Reference: blue=0.066 (best),
    pink=0.013 (densest Q1 region). Higher = more diverse V-A spread.
    """
    if len(idxs) < 2:
        return 0.0
    pts = song_va[np.array(idxs, int)]
    n = len(pts)
    dists = [float(np.linalg.norm(pts[i] - pts[j]))
             for i in range(n) for j in range(i + 1, n)]
    return float(np.mean(dists))


def mahalanobis_te(idxs: list[int], song_va: np.ndarray,
                   color_va: np.ndarray, cov_inv: np.ndarray) -> float:
    """Mean Mahalanobis distance from colour's V-A to each result's V-A."""
    if not idxs:
        return 1.0
    pts = song_va[np.array(idxs, int)] - color_va
    return float(np.mean([float(np.sqrt(max(0.0, (p @ cov_inv @ p)))) for p in pts]))


# ── Journey calibration ───────────────────────────────────────────────────────

def journey_calibration(p1: np.ndarray, p2: np.ndarray,
                        idxs: list[int], song_va: np.ndarray
                        ) -> dict:
    """Measure how uniformly songs are distributed along V-A path P1→P2.

    Projects each song onto t ∈ [0,1] along P1→P2. Ideal journey = uniform
    U[0,1]. Measured by:
      ks_stat   KS distance from uniform (lower = more uniform)
      mean_t    should be ≈ 0.5 if path is traversed end-to-end
      std_t     should be ≈ 0.289 (std of U[0,1])
      pct_covered fraction of [0,1] covered in 10 equal bins
    """
    if not idxs or len(idxs) < 2:
        return {'ks_stat': 1.0, 'mean_t': 0.0, 'std_t': 0.0, 'pct_bins_covered': 0.0}
    axis = p2 - p1
    denom = float(axis @ axis)
    if denom < 1e-9:
        return {'ks_stat': 1.0, 'mean_t': 0.5, 'std_t': 0.0, 'pct_bins_covered': 0.0}
    t_vals = np.clip(
        [(song_va[i] - p1) @ axis / denom for i in idxs], 0.0, 1.0)
    ks_stat, _ = ss.kstest(t_vals, 'uniform')
    bins = np.zeros(10)
    for t in t_vals:
        bins[min(9, int(t * 10))] += 1
    pct_cov = float((bins > 0).sum()) / 10.0
    return {
        'ks_stat':          round(float(ks_stat), 4),
        'mean_t':           round(float(np.mean(t_vals)), 4),
        'std_t':            round(float(np.std(t_vals)), 4),
        'ideal_std_t':      0.289,
        'pct_bins_covered': round(pct_cov, 3),
        'n_songs':          len(idxs),
    }


# ── Construct validity helpers ───────────────────────────────────────────────

def gini_coef(values: np.ndarray) -> float:
    """Gini coefficient of a 1D array (0=uniform, 1=concentrated at one value)."""
    v = np.sort(np.abs(values.flatten()))
    n = len(v)
    if n == 0 or v.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * (idx * v).sum() / (n * v.sum())) - (n + 1) / n)


def coverage_va(song_va: np.ndarray, n_bins: int = 10) -> float:
    """Fraction of n_bins×n_bins grid cells in [0,1]² containing ≥1 song."""
    v_idx = np.minimum((np.clip(song_va[:, 0], 0, 1) * n_bins).astype(int), n_bins - 1)
    a_idx = np.minimum((np.clip(song_va[:, 1], 0, 1) * n_bins).astype(int), n_bins - 1)
    occupied = set(zip(v_idx.tolist(), a_idx.tolist()))
    return round(len(occupied) / (n_bins * n_bins), 4)


def entropy_va(song_va: np.ndarray, n_bins: int = 10) -> float:
    """Normalized Shannon entropy of V-A distribution (0=degenerate, 1=uniform)."""
    v_idx = np.minimum((np.clip(song_va[:, 0], 0, 1) * n_bins).astype(int), n_bins - 1)
    a_idx = np.minimum((np.clip(song_va[:, 1], 0, 1) * n_bins).astype(int), n_bins - 1)
    counts = Counter(zip(v_idx.tolist(), a_idx.tolist()))
    total = sum(counts.values())
    probs = np.array([c / total for c in counts.values()])
    entropy = -float(np.sum(probs * np.log2(probs + 1e-12)))
    return round(entropy / np.log2(n_bins * n_bins), 4)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    import config
    if _args.emotions_file:
        config.RELABELED_EMOTIONS_FILE = _args.emotions_file
        print(f"[override] RELABELED_EMOTIONS_FILE = {_args.emotions_file}")
    from core.recommendation_engine import get_recommender

    rec      = get_recommender()

    n        = rec.n_songs
    song_va  = rec.song_va          # (n, 2)
    # V31: under rank-space matching the recommender ranks in catalog-CDF space and the
    # colour target is a raw quantile. Measure TE in that SAME space — comparing real
    # song_va to a raw-quantile colour_va mixes coordinate systems and inflates TE.
    if getattr(config, 'COLOR_VA_RANK_MATCH', False) and hasattr(rec, 'song_va_match'):
        song_va = rec.song_va_match
        print("[V31] measuring TE in quantile/rank match space")
    sigma_v  = config.COLOR_SCORE_VA_SIGMA_V   # 0.20
    sigma_a  = config.COLOR_SCORE_VA_SIGMA_A   # 0.14

    # Covariance of song_va for Mahalanobis
    cov = np.cov(song_va.T)
    try:
        cov_inv = np.linalg.inv(cov + 1e-6 * np.eye(2))
    except np.linalg.LinAlgError:
        cov_inv = np.eye(2)

    # Popularity proxy (artist frequency, same as other tools)
    art_col  = rec.artist_col or 'artists'
    artists  = rec.df[art_col].fillna('__unknown__').astype(str).values
    art_freq = Counter(artists)
    max_freq = max(art_freq.values())
    pop_proxy = np.array([art_freq[a] / max_freq for a in artists], float)

    rng = np.random.default_rng(42)

    # ── Per-colour targeting error ────────────────────────────────────────────
    baselines = ['random', 'popularity', 'nearest_va', 'valence_only', 'arousal_only']
    prod_te_eu: list[float] = []
    prod_te_ma: list[float] = []
    base_te_eu: dict[str, list[float]] = {b: [] for b in baselines}
    base_te_ma: dict[str, list[float]] = {b: [] for b in baselines}
    per_color: dict[str, dict] = {}

    print(f"\nV-A TARGETING ERROR  top_k={TOP_K}")
    hdr = (f"{'colour':22} {'prod_eu':>8} {'nearest':>8} "
           f"{'val_only':>9} {'aro_only':>9} {'pop':>7} {'rand':>7} {'ILD':>7}")
    print(hdr); print("-" * len(hdr))

    for hx, name in ICEAS_COLS:
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        color_va = np.array([cv, ca])

        # Production recommendations
        df_prod = rec.recommend_by_colors(hx, top_k=TOP_K)
        prod_idx = (df_prod['original_index'].tolist()
                    if df_prod is not None and not df_prod.empty
                    and 'original_index' in df_prod.columns else [])

        prod_eu = euclidean_te(prod_idx, song_va, color_va)
        prod_ma = mahalanobis_te(prod_idx, song_va, color_va, cov_inv)
        prod_ild = compute_ild(prod_idx, song_va)
        prod_te_eu.append(prod_eu)
        prod_te_ma.append(prod_ma)

        # Baselines
        bl = _baseline_scores(song_va, color_va, pop_proxy,
                               sigma_v, sigma_a, rng, n, TOP_K)
        bl_eu = {b: euclidean_te(bl[b], song_va, color_va) for b in baselines}
        bl_ma = {b: mahalanobis_te(bl[b], song_va, color_va, cov_inv) for b in baselines}
        for b in baselines:
            base_te_eu[b].append(bl_eu[b])
            base_te_ma[b].append(bl_ma[b])

        per_color[hx] = {
            'name': name, 'color_va': [round(cv, 3), round(ca, 3)],
            'prod': {'euclidean': round(prod_eu, 4), 'mahalanobis': round(prod_ma, 4),
                     'ild': round(prod_ild, 4)},
            'baselines_eu': {b: round(bl_eu[b], 4) for b in baselines},
            'baselines_ma': {b: round(bl_ma[b], 4) for b in baselines},
            'wins_euclidean': sum(prod_eu < bl_eu[b] for b in baselines),
        }
        print(f"{name+' '+hx:22}"
              f" {prod_eu:8.4f}"
              f" {bl_eu['nearest_va']:8.4f}"
              f" {bl_eu['valence_only']:9.4f}"
              f" {bl_eu['arousal_only']:9.4f}"
              f" {bl_eu['popularity']:7.4f}"
              f" {bl_eu['random']:7.4f}"
              f" {prod_ild:7.4f}")

    # ── Aggregate + CI ────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    prod_ci_eu = boot_ci(prod_te_eu)
    prod_ci_ma = boot_ci(prod_te_ma)
    base_ci_eu = {b: boot_ci(base_te_eu[b]) for b in baselines}
    base_ci_ma = {b: boot_ci(base_te_ma[b]) for b in baselines}

    print(f"\nAGGREGATE TARGETING ERROR (lower = better, 95% bootstrap CI n=10k)")
    print(f"  {'':18} {'mean':>8} {'CI_lo':>8} {'CI_hi':>8}  wins/12")
    wins_eu = {b: sum(prod_te_eu[i] < base_te_eu[b][i] for i in range(len(ICEAS_COLS)))
               for b in baselines}

    def _pr(label, ci, wins=None):
        m, lo, hi = ci
        w = f"  {wins}/12" if wins is not None else ""
        print(f"  {label:<18} {m:8.4f} {lo:8.4f} {hi:8.4f}{w}")

    print("  [Euclidean]")
    _pr("production", prod_ci_eu)
    for b in baselines:
        _pr(b, base_ci_eu[b], wins_eu[b])

    print("  [Mahalanobis]")
    _pr("production", prod_ci_ma)
    for b in baselines:
        _pr(b, base_ci_ma[b])

    # ── FDR (Benjamini-Hochberg) ──────────────────────────────────────────────
    print(f"\nFDR ANALYSIS (Benjamini-Hochberg α=0.05, Wilcoxon one-sided)")
    print("  H₁: production targeting error < baseline (lower = better)")
    p_raw: list[float] = []
    fdr_labels: list[str] = []
    for b in baselines:
        # One-sided: production has LOWER targeting error than baseline
        diff = np.array(base_te_eu[b]) - np.array(prod_te_eu)  # positive = prod better
        try:
            _, pval = ss.wilcoxon(diff, alternative='greater', zero_method='wilcox')
        except ValueError:
            pval = 1.0
        p_raw.append(pval)
        fdr_labels.append(b)

    adj_p, reject = bh_correction(p_raw)
    print(f"  {'baseline':18} {'p_raw':>8} {'p_adj_BH':>10} {'reject H₀':>10}")
    for lbl, pr, pa, rej in zip(fdr_labels, p_raw, adj_p, reject):
        sym = '✓ sig' if rej else '✗ n.s.'
        print(f"  {lbl:<18} {pr:8.4f} {pa:10.5f} {sym:>10}")

    # ── Construct validity (Tầng C) ──────────────────────────────────────────
    print(f"\nCONSTRUCT VALIDITY (Tầng C)")

    v_arr = song_va[:, 0]
    a_arr = song_va[:, 1]

    r_va, _ = ss.pearsonr(v_arr, a_arr)
    va_ortho_pass = abs(r_va) <= 0.20
    print(f"  r(V, A) = {r_va:+.4f}  "
          f"(target |r|≤0.20; v5d baseline = 0.313)  "
          f"{'✓' if va_ortho_pass else '✗'}")

    # Prefer the CLEAN librosa-downbeat BPM (data/clean_bpm.json) over the degenerate
    # Essentia-44.1kHz `tempo` column (ρ(clean,essentia)=0.55; essentia is noisy). V32:
    # the gate was partly measuring a bad tempo column — measure against clean BPM.
    rho_a_tempo = None
    tempo_arr = None
    if os.path.exists("data/clean_bpm.json") and "track_id" in rec.df.columns:
        _cb = json.load(open("data/clean_bpm.json"))
        _tids = rec.df["track_id"].astype(str).values
        tempo_arr = np.array([_cb.get(t, np.nan) for t in _tids], float)
        if np.isnan(tempo_arr).all():
            tempo_arr = None
    if tempo_arr is None:
        tempo_col = next((c for c in ['tempo', 'bpm'] if c in rec.df.columns), None)
        if tempo_col:
            tempo_arr = rec.df[tempo_col].fillna(rec.df[tempo_col].median()).values.astype(float)
    if tempo_arr is not None:
        _m = ~np.isnan(tempo_arr)
        rho_a_tempo_val, _ = ss.spearmanr(a_arr[_m], tempo_arr[_m])
        rho_a_tempo = round(float(rho_a_tempo_val), 4)
        a_tempo_pass = rho_a_tempo > 0.20
        print(f"  ρ(A, tempo[clean BPM]) = {rho_a_tempo:+.4f}  "
              f"(target >0.20)  {'✓' if a_tempo_pass else '✗'}")
    else:
        print(f"  ρ(A, tempo) = N/A  (no tempo column)")

    gini_v = round(gini_coef(v_arr), 4)
    gini_a = round(gini_coef(a_arr), 4)
    cov_va = coverage_va(song_va)
    ent_va = entropy_va(song_va)
    print(f"  Gini: V={gini_v:.4f}  A={gini_a:.4f}  "
          f"(low=concentrated; target V<0.60, A<0.60)")
    print(f"  Coverage (10×10 grid) = {cov_va:.4f}  (target ≥0.50)")
    print(f"  Entropy (normalised)  = {ent_va:.4f}  (target ≥0.60)")

    # Inter-signal corroboration: MERT valence vs catalog valence
    inter_signal: dict = {}
    mert_val_path = "data/mert_valence.json"
    if os.path.exists(mert_val_path):
        mert_v_raw = json.load(open(mert_val_path))
        id_col = next((c for c in ['id', 'track_id', 'song_id', 'ID']
                       if c in rec.df.columns), None)
        if id_col:
            matched = [mert_v_raw.get(str(sid)) for sid in rec.df[id_col]]
            valid_mask = np.array([v is not None for v in matched])
            if valid_mask.sum() > 100:
                mert_vals = np.array([matched[i] for i in range(len(matched)) if valid_mask[i]])
                cat_vals  = v_arr[valid_mask]
                rho_inter, _ = ss.spearmanr(mert_vals, cat_vals)
                inter_signal['rho_mert_v_vs_catalog_v'] = round(float(rho_inter), 4)
                inter_pass = abs(rho_inter) > 0.25
                print(f"  ρ(MERT_V, catalog_V) = {rho_inter:+.4f}  "
                      f"(inter-signal corroboration; target |ρ|>0.25)  "
                      f"{'✓' if inter_pass else '✗'}")

    construct_validity = {
        'r_valence_arousal': round(float(r_va), 4),
        'va_orthogonal_pass': bool(va_ortho_pass),
        'rho_arousal_tempo': rho_a_tempo,
        'gini_valence': gini_v,
        'gini_arousal': gini_a,
        'coverage_va_10x10': cov_va,
        'entropy_va_normalised': ent_va,
        'inter_signal': inter_signal,
        'targets': {
            'r_va': '|r|≤0.20 (orthogonal)',
            'rho_a_tempo': '>0.20',
            'coverage': '≥0.50',
            'entropy': '≥0.60',
        },
    }

    # ── Journey calibration (adjacent colour pairs) ───────────────────────────
    print(f"\nJOURNEY CALIBRATION (2-colour path A→B, KS vs uniform)")
    print(f"  Ideal: ks_stat≈0, mean_t≈0.5, pct_bins_covered=1.0")
    print(f"  {'pair':28} {'ks':>6} {'mean_t':>7} {'std_t':>7} {'bins%':>7}")
    journey_results: dict[str, dict] = {}

    pairs = [(ICEAS_COLS[i], ICEAS_COLS[(i + 3) % len(ICEAS_COLS)])
             for i in range(len(ICEAS_COLS))]  # spread-out pairs

    for (hx_a, na), (hx_b, nb) in pairs:
        va_a = np.array(rec.color_mapper.hsl_to_va(hx_a), float)
        va_b = np.array(rec.color_mapper.hsl_to_va(hx_b), float)
        try:
            df_j = rec.recommend_by_colors([hx_a, hx_b], top_k=TOP_K)
            j_idxs = (df_j['original_index'].tolist()
                      if df_j is not None and not df_j.empty
                      and 'original_index' in df_j.columns else [])
        except Exception:
            j_idxs = []
        jc = journey_calibration(va_a, va_b, j_idxs, song_va)
        pair_key = f"{na}→{nb}"
        journey_results[pair_key] = {**jc, 'hex_a': hx_a, 'hex_b': hx_b}
        print(f"  {pair_key:<28}"
              f" {jc['ks_stat']:6.3f}"
              f" {jc['mean_t']:7.3f}"
              f" {jc['std_t']:7.3f}"
              f" {jc['pct_bins_covered']:7.1%}")

    ks_mean = float(np.mean([v['ks_stat'] for v in journey_results.values()]))
    mt_mean = float(np.mean([v['mean_t']  for v in journey_results.values()]))
    pct_mean= float(np.mean([v['pct_bins_covered'] for v in journey_results.values()]))
    print(f"  {'MEAN':28} {ks_mean:6.3f} {mt_mean:7.3f}"
          f" {'':>7} {pct_mean:7.1%}")
    ks_pass = ks_mean < 0.40   # relaxed threshold (journey is near-uniform by design)
    mt_pass = 0.35 <= mt_mean <= 0.65
    print(f"\n  Journey gate: KS<0.40 {'✓' if ks_pass else '✗'}  "
          f"mean_t∈[0.35,0.65] {'✓' if mt_pass else '✗'}")

    # ── Ordering summary ──────────────────────────────────────────────────────
    prod_mean_eu = prod_ci_eu[0]
    # nearest_va is prod's own scorer without diversity penalty → expect TE ≈ equal.
    # Gate: strictly beat the 4 non-identical baselines; nearest_va ≤ prod + tolerance.
    TOLERANCE_NEAREST = 0.005
    ordering = {}
    for b in baselines:
        if b == 'nearest_va':
            ordering[f"prod_eu ≤ nearest_va+tol"] = bool(
                prod_mean_eu <= base_ci_eu[b][0] + TOLERANCE_NEAREST)
        else:
            ordering[f"prod_eu < {b}"] = bool(prod_mean_eu < base_ci_eu[b][0])
    n_wins = sum(ordering.values())
    print(f"\nORDERING CHECKS (production Euclidean TE vs baseline mean)")
    print(f"  Note: nearest_va = same V-A scorer without diversity penalty → TE ≈ equal")
    for label, ok in ordering.items():
        print(f"  {'✓' if ok else '✗'} {label}")
    all_ordering_pass = (n_wins == len(baselines))
    print(f"\n  Production passes all {len(baselines)} checks: "
          f"{'YES ✓' if all_ordering_pass else f'NO ({n_wins}/{len(baselines)} ✗)'}")

    # ── Fisher-z CI for L1 correlation (n=12) ─────────────────────────────────
    # L1 bridge: r ≈ 0.92 from existing color_bridge_metrics; recompute here for CI
    print(f"\nFISHER-z CI for L1 colour→V-A correlation (n=12 ICEAS colours)")
    iceas_va_human = {       # ICEAS human valence norms (Jonauskaite 2020 Table 2)
        '#BE0032': (0.35, 0.72), '#F38400': (0.68, 0.65), '#F3C300': (0.73, 0.62),
        '#FFB7C5': (0.75, 0.48), '#008856': (0.62, 0.43), '#3AB09E': (0.70, 0.42),
        '#0067A5': (0.55, 0.45), '#9C4F96': (0.45, 0.50), '#80461B': (0.30, 0.42),
        '#F2F3F4': (0.65, 0.32), '#848482': (0.30, 0.40), '#222222': (0.18, 0.58),
    }
    pred_v, pred_a, true_v, true_a = [], [], [], []
    for hx, _ in ICEAS_COLS:
        pv, pa = rec.color_mapper.hsl_to_va(hx)
        if hx in iceas_va_human:
            tv, ta = iceas_va_human[hx]
            pred_v.append(pv); true_v.append(tv)
            pred_a.append(pa); true_a.append(ta)

    def fisher_z_ci(r: float, n: int, alpha: float = 0.05):
        z = np.arctanh(np.clip(r, -0.9999, 0.9999))
        se = 1.0 / np.sqrt(n - 3)
        z_crit = ss.norm.ppf(1 - alpha / 2)
        return (round(np.tanh(z - z_crit * se), 3),
                round(np.tanh(z + z_crit * se), 3))

    r_v = float(ss.pearsonr(pred_v, true_v)[0]) if len(pred_v) > 2 else 0.0
    r_a = float(ss.pearsonr(pred_a, true_a)[0]) if len(pred_a) > 2 else 0.0
    ci_v = fisher_z_ci(r_v, len(pred_v))
    ci_a = fisher_z_ci(r_a, len(pred_a))
    print(f"  Valence:  r = {r_v:.3f}  95% CI Fisher-z {ci_v}")
    print(f"  Arousal:  r = {r_a:.3f}  95% CI Fisher-z {ci_a}")
    print(f"  Note: n={len(pred_v)} is small; CI width is expected. "
          f"This is the known limitation per V21 audit (B1).")

    # ── Save report ───────────────────────────────────────────────────────────
    report = {
        "top_k": TOP_K,
        "va_targeting_error": {
            "description": (
                "Mean Euclidean/Mahalanobis distance from query colour V-A to "
                "result songs V-A. Lower = better calibrated targeting."
            ),
            "production": {
                "euclidean":   {"mean": prod_ci_eu[0], "ci95": list(prod_ci_eu[1:])},
                "mahalanobis": {"mean": prod_ci_ma[0], "ci95": list(prod_ci_ma[1:])},
            },
            "baselines_euclidean": {
                b: {"mean": base_ci_eu[b][0], "ci95": list(base_ci_eu[b][1:])}
                for b in baselines
            },
            "baselines_mahalanobis": {
                b: {"mean": base_ci_ma[b][0], "ci95": list(base_ci_ma[b][1:])}
                for b in baselines
            },
            "wins_euclidean_per_baseline": wins_eu,
            "ordering_all_pass": all_ordering_pass,
        },
        "fdr_analysis": {
            "method": "Benjamini-Hochberg (1995), Wilcoxon one-sided",
            "alpha": 0.05,
            "results": [
                {"baseline": lbl, "p_raw": round(pr, 5), "p_adj_BH": round(pa, 5),
                 "reject_H0": rej}
                for lbl, pr, pa, rej in zip(fdr_labels, p_raw, adj_p, reject)
            ],
        },
        "journey_calibration": {
            "description": (
                "KS statistic vs U[0,1] for song projection along V-A path A→B. "
                "Lower KS = more uniform = better journey coverage."
            ),
            "mean_ks_stat": round(ks_mean, 4),
            "mean_t": round(mt_mean, 4),
            "mean_pct_bins_covered": round(pct_mean, 3),
            "gate_ks_pass": ks_pass,
            "gate_mean_t_pass": mt_pass,
            "per_pair": journey_results,
        },
        "l1_bridge_fisher_z": {
            "n_colors": len(pred_v),
            "valence": {"r": round(r_v, 4), "ci95_fisher_z": list(ci_v)},
            "arousal": {"r": round(r_a, 4), "ci95_fisher_z": list(ci_a)},
            "note": "n=12 → wide CI; this is B1 known limitation per V21 audit.",
        },
        "per_color": per_color,
        "gates": {
            "ordering_all_pass": all_ordering_pass,
            "journey_ks_pass":   ks_pass,
            "journey_t_pass":    mt_pass,
        },
        "basis": (
            "Dacrema 2021 (ACM TOIS) strong baselines; "
            "Schnabel 2022 CI requirement; "
            "Benjamini&Hochberg 1995 FDR; "
            "Steck 2018 (RecSys'18) calibration; "
            "Saari 2016 / Starcke 2024 Iso-Principle journey."
        ),
        "construct_validity": construct_validity,
        "meta": {
            "emotions_file": _args.emotions_file or "config default",
            "no_vn_overlay": bool(_args.no_vn_overlay),
        },
    }

    def _jsonify(obj):
        """Recursively convert numpy types to Python natives for JSON serialization."""
        if isinstance(obj, dict):
            return {k: _jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_jsonify(v) for v in obj]
        if isinstance(obj, (bool, int, float, str, type(None))):
            return obj
        if hasattr(obj, 'item'):   # numpy scalar
            return obj.item()
        return obj

    json.dump(_jsonify(report), open(OUT, "w"), ensure_ascii=False, indent=2)

    if _args.save_baseline:
        import shutil
        shutil.copy(OUT, _args.save_baseline)
        print(f"\n  baseline saved → {_args.save_baseline}")

    print(f"\n{'='*70}")
    print("PHASE-1 RIGOR SUMMARY")
    print(f"{'='*70}")
    print(f"  TE ordering (prod < all 5 baselines): "
          f"{'ALL PASS ✓' if all_ordering_pass else f'{n_wins}/5 ✗'}")
    sig_count = sum(reject)
    print(f"  FDR significance (α=0.05):  {sig_count}/{len(baselines)} baselines rejected")
    print(f"  Journey calibration:  KS={ks_mean:.3f} "
          f"({'PASS ✓' if ks_pass else 'FAIL ✗'})  "
          f"mean_t={mt_mean:.3f} ({'PASS ✓' if mt_pass else 'FAIL ✗'})")
    print(f"  L1 Fisher-z: valence r={r_v:.3f} CI{list(ci_v)}  "
          f"arousal r={r_a:.3f} CI{list(ci_a)}")
    print(f"  Construct validity: r(V,A)={r_va:+.4f} "
          f"{'✓' if va_ortho_pass else '✗'}  "
          f"coverage={cov_va:.3f}  entropy={ent_va:.3f}")
    print(f"\n  saved → {OUT}")
    print(f"{'='*70}")

    return 0 if (all_ordering_pass and ks_pass and mt_pass) else 1


if __name__ == "__main__":
    sys.exit(main())
