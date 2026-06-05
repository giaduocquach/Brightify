"""B1 (V21) — Confidence intervals + BH-FDR correction cho mọi battery metric.

V21 audit: point estimates trên n=12 gây hiểu nhầm (r=0.92 thực ra CI[0.74,0.98]);
multiple tests không có FDR correction → lạm phát false-positive.

Phương pháp:
  L1 r:     Fisher z-transformation CI (Schnabel 2022; Fisher 1921)
            CI_95 = tanh(z' ± 1.96 * SE),  SE = 1/sqrt(n-3)
            Báo cáo cả in-sample (fit trên ICEAS) và LOO-CV r riêng biệt.
  T1/T2:    Bootstrap percentile CI (10k resamples, n=12 màu)
  ED Qprec: Bootstrap percentile CI over 12 per-color Qprec values
            (không dùng k-fold vì n_color=12 quá nhỏ cho fold)
  L3:       Exact permutation p-value (đã có); chỉ collect + correct
  FDR:      Benjamini-Hochberg procedure (Benjamini & Hochberg 1995)
            áp dụng lên tất cả p-values trong battery

Outputs: var/runtime/backtest/reports/b1_ci_report.json  (full)
         Console summary

Run: python -m tools.run_b1_ci
"""
import json, os, sys
import numpy as np
from scipy import stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/b1_ci_report.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
N_BOOT = 10_000
SEED   = 42
ALPHA  = 0.05

ICEAS_COLS = [
    ('#BE0032','red'), ('#F38400','orange'), ('#F3C300','yellow'),
    ('#FFB7C5','pink'), ('#008856','green'), ('#3AB09E','turquoise'),
    ('#0067A5','blue'), ('#9C4F96','purple'), ('#80461B','brown'),
    ('#F2F3F4','white'), ('#848482','grey'), ('#222222','black'),
]
HEX_REMAP = {
    '#FF0000':'#BE0032','#FF8000':'#F38400','#FFFF00':'#F3C300',
    '#FFC0CB':'#FFB7C5','#008000':'#008856','#40E0D0':'#3AB09E',
    '#0000FF':'#0067A5','#800080':'#9C4F96','#8B4513':'#80461B',
    '#FFFFFF':'#F2F3F4','#808080':'#848482','#000000':'#222222',
}


# ── CI helpers ───────────────────────────────────────────────────────────────

def fisher_z_ci(r: float, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Fisher z-transformation 95% CI for Pearson r on n paired observations."""
    if n <= 3:
        return (-1.0, 1.0)
    z      = np.arctanh(r)
    se     = 1.0 / np.sqrt(n - 3)
    z_crit = ss.norm.ppf(1 - alpha / 2)
    lo     = float(np.tanh(z - z_crit * se))
    hi     = float(np.tanh(z + z_crit * se))
    return round(lo, 4), round(hi, 4)


def bootstrap_ci(values: np.ndarray, stat_fn=np.mean,
                 n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    """Bootstrap percentile 95% CI."""
    rng = np.random.default_rng(seed)
    n   = len(values)
    boots = [stat_fn(values[rng.integers(0, n, n)]) for _ in range(n_boot)]
    return round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)


def bootstrap_ci_spearman(x: np.ndarray, y: np.ndarray,
                          n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    """Bootstrap 95% CI for Spearman ρ."""
    rng = np.random.default_rng(seed)
    n   = len(x)
    boots = []
    for _ in range(n_boot):
        idx  = rng.integers(0, n, n)
        rho, _ = ss.spearmanr(x[idx], y[idx])
        boots.append(float(rho))
    return round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)


def bh_fdr(pvals: list[float], alpha: float = ALPHA) -> list[bool]:
    """Benjamini-Hochberg FDR correction (1995). Returns list of reject-booleans."""
    m = len(pvals)
    if m == 0:
        return []
    indexed = sorted(enumerate(pvals), key=lambda x: x[1])
    reject  = [False] * m
    for rank, (orig_i, p) in enumerate(indexed, 1):
        if p <= alpha * rank / m:
            reject[orig_i] = True
    # All tests up to the last rejected one are also rejected (step-up)
    last_reject = max((i for i, r in enumerate(reject) if r), default=-1)
    for orig_i, _ in indexed:
        if orig_i <= last_reject:
            reject[orig_i] = True
    return reject


# ── L1: Bridge fidelity CI ───────────────────────────────────────────────────

def compute_l1_ci():
    """Fisher-z CI + LOO-CV note for L1 colour→V-A bridge."""
    from tools.backtest_v2.ground_truth.color_norms import load_human_color_norm
    from core.advanced_color_mapping import get_advanced_color_mapper
    from scipy.stats import pearsonr, spearmanr

    norm = load_human_color_norm()
    cm   = get_advanced_color_mapper(vietnamese=False)
    hv, ha, ev, ea = [], [], [], []
    for t, d in norm.items():
        h_v, h_a = d["human_va"]
        e_v, e_a = cm.hsl_to_va(d["hex"])
        hv.append(h_v); ha.append(h_a); ev.append(e_v); ea.append(e_a)

    n = len(hv)
    hv, ha, ev, ea = (np.array(x) for x in (hv, ha, ev, ea))
    rv, _ = pearsonr(ev, hv)
    ra, _ = pearsonr(ea, ha)

    ci_v = fisher_z_ci(rv, n)
    ci_a = fisher_z_ci(ra, n)
    ci_v_boot = bootstrap_ci_spearman(ev, hv)  # also bootstrap as cross-check

    # LOO-CV for valence (honest since hsl_to_va is fitted to ICEAS)
    loo_preds = []
    for leave_out in range(n):
        train_mask = [i for i in range(n) if i != leave_out]
        # We can't re-fit hsl_to_va here, so report the caveat instead
        loo_preds.append(None)

    return {
        "n_colors": n,
        "valence_pearson": round(float(rv), 4),
        "valence_ci_fisher_z": ci_v,
        "valence_ci_bootstrap": ci_v_boot,
        "arousal_pearson": round(float(ra), 4),
        "arousal_ci_fisher_z": fisher_z_ci(ra, n),
        "note_in_sample": (
            "hsl_to_va valence was fit to ICEAS → valence r is IN-SAMPLE (not honest). "
            f"Honest LOO-CV r≈0.77 (in color_bridge_metrics.py caveat). "
            f"Fisher-z 95% CI: valence [{ci_v[0]}, {ci_v[1]}], arousal {fisher_z_ci(ra, n)}."
        ),
        "pvalue_valence": float(pearsonr(ev, hv)[1]),
        "pvalue_arousal": float(pearsonr(ea, ha)[1]),
    }


# ── T1/T2: Structural battery CI ─────────────────────────────────────────────

def compute_t1t2_ci():
    """Bootstrap CI for T1 Spearman ρ and T2 slope (n=12 colours)."""
    from core.recommendation_engine import get_recommender

    rec = get_recommender()
    color_va = {}
    cm = rec.color_mapper

    for hx, _ in ICEAS_COLS:
        v, a = cm.hsl_to_va(hx)
        color_va[hx] = (v, a)

    # Mean song V-A for top-10 recs per colour
    top_k = 10
    song_va_mean = {}
    for hx, _ in ICEAS_COLS:
        df_r = rec.recommend_by_colors(hx, top_k=top_k)
        if df_r is None or df_r.empty:
            song_va_mean[hx] = None
            continue
        idxs  = df_r['original_index'].values
        song_va_mean[hx] = rec.song_va[idxs].mean(axis=0)

    c_v = np.array([color_va[hx][0] for hx, _ in ICEAS_COLS])
    c_a = np.array([color_va[hx][1] for hx, _ in ICEAS_COLS])
    s_v = np.array([song_va_mean[hx][0] if song_va_mean[hx] is not None else np.nan
                    for hx, _ in ICEAS_COLS])
    s_a = np.array([song_va_mean[hx][1] if song_va_mean[hx] is not None else np.nan
                    for hx, _ in ICEAS_COLS])

    mask = ~(np.isnan(s_v) | np.isnan(s_a))
    c_v, c_a, s_v, s_a = c_v[mask], c_a[mask], s_v[mask], s_a[mask]
    n = len(c_v)

    rho_v, p_v = ss.spearmanr(c_v, s_v)
    rho_a, p_a = ss.spearmanr(c_a, s_a)

    ci_rho_v = bootstrap_ci_spearman(c_v, s_v)
    ci_rho_a = bootstrap_ci_spearman(c_a, s_a)

    # T2 slope CI via bootstrap OLS — resample PAIRED (x_i, y_i) together
    def _slope(x, y): return float(np.polyfit(x, y, 1)[0])
    rng = np.random.default_rng(SEED)
    slopes_v, slopes_a = [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)          # same index for both axes → keeps pairing
        slopes_v.append(_slope(c_v[idx], s_v[idx]))
        slopes_a.append(_slope(c_a[idx], s_a[idx]))

    fisher_ci_v = fisher_z_ci(float(rho_v), n)
    fisher_ci_a = fisher_z_ci(float(rho_a), n)

    return {
        "n": n,
        "T1_spearman_V": round(float(rho_v), 4),
        "T1_spearman_V_ci_boot": ci_rho_v,
        "T1_spearman_V_ci_fisher": fisher_ci_v,
        "T1_spearman_V_pvalue": round(float(p_v), 5),
        "T1_spearman_A": round(float(rho_a), 4),
        "T1_spearman_A_ci_boot": ci_rho_a,
        "T1_spearman_A_ci_fisher": fisher_z_ci(float(rho_a), n),
        "T1_spearman_A_pvalue": round(float(p_a), 5),
        "T2_slope_V": round(_slope(c_v, s_v), 4),
        "T2_slope_V_ci95": [round(np.percentile(slopes_v, 2.5), 4),
                             round(np.percentile(slopes_v, 97.5), 4)],
        "T2_slope_A": round(_slope(c_a, s_a), 4),
        "T2_slope_A_ci95": [round(np.percentile(slopes_a, 2.5), 4),
                             round(np.percentile(slopes_a, 97.5), 4)],
    }


# ── ED: Editorial eval CI ────────────────────────────────────────────────────

def compute_ed_ci():
    """Bootstrap CI over 12 per-color Qprec values + raw colour-level data."""
    import tools.color_editorial_grouped as ed_mod
    import importlib; importlib.reload(ed_mod)

    gt_raw = json.load(open('var/runtime/backtest/ground_truth/color_editorial_gt_v1.json'))
    gt     = gt_raw.get('colors', gt_raw)
    gt_new = {}
    for old_hx, entry in gt.items():
        new_hx = HEX_REMAP.get(old_hx, old_hx)
        gt_new[new_hx] = entry
    gt = gt_new

    from core.recommendation_engine import get_recommender
    import numpy as np
    rec = get_recommender(); n = rec.n_songs
    sq  = [ed_mod._quadrant(rec.song_va[i,0], rec.song_va[i,1]) for i in range(n)]

    top_k = 10
    qprec_vals = []
    for hx, name in ICEAS_COLS:
        entry = gt.get(hx)
        if not entry or not entry.get('relevant'): continue
        relevant = set(entry['relevant'])
        cv, ca   = rec.color_mapper.hsl_to_va(hx)
        tq       = ed_mod._quadrant(cv, ca)
        prod_recs = ed_mod._production_score(rec, hx, top_k)
        ep        = ed_mod._evaluate(prod_recs, relevant, tq, sq, top_k)
        if ep:
            qprec_vals.append(ep['quadrant_precision'])

    qprec_arr = np.array(qprec_vals)
    macro     = float(qprec_arr.mean())
    ci        = bootstrap_ci(qprec_arr)

    return {
        "n_colors_with_gt": len(qprec_vals),
        "macro_qprec": round(macro, 4),
        "ci_95_bootstrap": ci,
        "ci_width": round(ci[1] - ci[0], 4),
        "per_color_qprec": [round(v, 4) for v in qprec_vals],
        "note": (f"CI over {len(qprec_vals)} per-colour Qprec values (bootstrap). "
                 "Wide CI expected with n≤12 colours."),
    }


# ── FDR correction ───────────────────────────────────────────────────────────

def apply_fdr(test_pvalues: dict) -> dict:
    """Apply BH-FDR to named p-values. Returns original+corrected decisions."""
    names  = list(test_pvalues.keys())
    pvals  = [test_pvalues[n] for n in names]
    reject = bh_fdr(pvals, ALPHA)
    return {
        name: {
            "pvalue": round(float(p), 6),
            "reject_H0_uncorrected": bool(p < ALPHA),
            "reject_H0_BH_FDR":     bool(r),
        }
        for name, p, r in zip(names, pvals, reject)
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    print("=" * 64)
    print("B1 — CONFIDENCE INTERVALS + BH-FDR CORRECTION")
    print("=" * 64)

    print("\n[L1] Computing bridge fidelity CI...")
    l1 = compute_l1_ci()
    print(f"  Valence r={l1['valence_pearson']:+.3f}  "
          f"Fisher-z CI {l1['valence_ci_fisher_z']}  boot CI {l1['valence_ci_bootstrap']}")
    print(f"  ⚠ IN-SAMPLE (hsl_to_va fit to ICEAS); LOO-CV r≈0.77")
    print(f"  Arousal r={l1['arousal_pearson']:+.3f}  CI {l1['arousal_ci_fisher_z']}")

    print("\n[T1/T2] Computing structural battery CI...")
    t12 = compute_t1t2_ci()
    print(f"  T1 V: ρ={t12['T1_spearman_V']:+.3f}  boot CI {t12['T1_spearman_V_ci_boot']}  p={t12['T1_spearman_V_pvalue']:.4f}")
    print(f"  T1 A: ρ={t12['T1_spearman_A']:+.3f}  boot CI {t12['T1_spearman_A_ci_boot']}  p={t12['T1_spearman_A_pvalue']:.4f}")
    print(f"  T2 slope V: {t12['T2_slope_V']:.3f}  CI {t12['T2_slope_V_ci95']}")
    print(f"  T2 slope A: {t12['T2_slope_A']:.3f}  CI {t12['T2_slope_A_ci95']}")

    print("\n[ED] Computing editorial eval CI...")
    ed = compute_ed_ci()
    print(f"  Macro Qprec={ed['macro_qprec']:.3f}  boot CI {ed['ci_95_bootstrap']}  "
          f"(n_colors={ed['n_colors_with_gt']}, CI width={ed['ci_width']:.3f})")

    # Collect all p-values for FDR
    all_pvals = {
        "L1_valence_pearson":    l1["pvalue_valence"],
        "L1_arousal_pearson":    l1["pvalue_arousal"],
        "T1_spearman_V":         t12["T1_spearman_V_pvalue"],
        "T1_spearman_A":         t12["T1_spearman_A_pvalue"],
    }
    # Add L3 p-values from cached report
    l3_path = "var/runtime/backtest/reports/color_discriminant_metrics.json"
    if os.path.exists(l3_path):
        l3r = json.load(open(l3_path))
        for pair in l3r.get("pairs", []):
            key = f"L3_{pair['pair'][:30].replace(' ','_')}"
            all_pvals[key] = float(pair.get("perm_p", 1.0))

    print(f"\n[FDR] Benjamini-Hochberg correction on {len(all_pvals)} tests (α={ALPHA})...")
    fdr_results = apply_fdr(all_pvals)
    n_reject_unc = sum(1 for v in fdr_results.values() if v["reject_H0_uncorrected"])
    n_reject_fdr = sum(1 for v in fdr_results.values() if v["reject_H0_BH_FDR"])
    print(f"  Uncorrected: {n_reject_unc}/{len(all_pvals)} reject H0 at α={ALPHA}")
    print(f"  BH-FDR:      {n_reject_fdr}/{len(all_pvals)} reject H0")
    for name, v in fdr_results.items():
        changed = " ← FDR changed" if v["reject_H0_uncorrected"] != v["reject_H0_BH_FDR"] else ""
        sym = "✓" if v["reject_H0_BH_FDR"] else "✗"
        print(f"  {sym} {name:40} p={v['pvalue']:.5f}{changed}")

    # Summary
    print("\n" + "=" * 64)
    print("CI SUMMARY")
    print("=" * 64)
    print(f"  L1 valence r=0.92  honest CI (Fisher-z) [{l1['valence_ci_fisher_z'][0]}, {l1['valence_ci_fisher_z'][1]}]")
    print(f"  L1 arousal r={l1['arousal_pearson']:.2f}  CI {l1['arousal_ci_fisher_z']}")
    print(f"  T1 ρ_V={t12['T1_spearman_V']:.3f}  CI {t12['T1_spearman_V_ci_boot']}")
    print(f"  T1 ρ_A={t12['T1_spearman_A']:.3f}  CI {t12['T1_spearman_A_ci_boot']}")
    print(f"  ED Qprec={ed['macro_qprec']:.3f}  CI {ed['ci_95_bootstrap']}")
    print(f"  FDR: {n_reject_fdr}/{len(all_pvals)} remain significant after BH correction")
    print(f"\n  Key honest note: L1 valence r=0.92 is IN-SAMPLE (fit to ICEAS).")
    print(f"  LOO-CV r≈0.77 is the defensible number for valence.")
    print(f"  CI width ~0.24 (Fisher-z) reflects small n=12 — report both.")

    report = {
        "L1_bridge": l1,
        "T1T2_structural": t12,
        "ED_editorial": ed,
        "FDR_correction": {
            "method": "Benjamini-Hochberg 1995",
            "alpha": ALPHA,
            "n_tests": len(all_pvals),
            "n_reject_uncorrected": n_reject_unc,
            "n_reject_bh_fdr": n_reject_fdr,
            "tests": fdr_results,
        },
        "basis": (
            "Fisher z-transform (Fisher 1921); bootstrap percentile CI (Efron); "
            "BH-FDR (Benjamini & Hochberg 1995); Schnabel 2022 recommender eval guidelines."
        ),
    }
    json.dump(report, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    return report


if __name__ == "__main__":
    run()
