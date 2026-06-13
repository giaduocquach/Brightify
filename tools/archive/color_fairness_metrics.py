"""B5/B6/B7 (V21) — Popularity-bias, artist-fairness, serendipity, robustness.

NO human labels. Cơ sở:
  B5 Popularity-bias: Gini + Entropy + ARP (Abdollahpouri 2021; Duricic 2023)
  B6 Artist fairness: Gini-trên-artist + exposure (Klimashevskaia 2024)
  B7 Serendipity (unexpectedness):  Pᵢ(U) = artist_freq/max_freq; unexp = 1 - Pᵢ(U)
     Robustness (perturbation):     hex ± ε → Jaccard/Kendall-τ của top-k

Run: python -m tools.color_fairness_metrics [top_k]
"""
import json, os, sys
import numpy as np
from collections import Counter
from scipy import stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K = int(sys.argv[1]) if len(sys.argv) > 1 else 10
OUT   = "var/runtime/backtest/reports/color_fairness_metrics.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

ICEAS_COLS = [
    ('#BE0032','red'),('#F38400','orange'),('#F3C300','yellow'),('#FFB7C5','pink'),
    ('#008856','green'),('#3AB09E','turquoise'),('#0067A5','blue'),('#9C4F96','purple'),
    ('#80461B','brown'),('#F2F3F4','white'),('#848482','grey'),('#222222','black'),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def gini(values: np.ndarray) -> float:
    """Gini coefficient: 0 = perfect equality, 1 = one item gets everything."""
    v = np.sort(np.abs(values)).astype(float)
    n = len(v)
    if n == 0 or v.sum() == 0: return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * (idx * v).sum()) / (n * v.sum()) - (n + 1) / n)


def entropy_norm(counts: np.ndarray) -> float:
    """Normalised Shannon entropy ∈ [0,1]. 1 = uniform."""
    p = counts / counts.sum()
    p = p[p > 0]
    h = -float((p * np.log2(p)).sum())
    return round(h / np.log2(len(counts)) if len(counts) > 1 else 0.0, 4)


def perturb_hex(hex_c: str, delta: int = 8) -> list[str]:
    """Generate 8 perturbed hexes by ±delta on each R/G/B channel independently."""
    hex_c = hex_c.lstrip('#')
    r, g, b = int(hex_c[0:2],16), int(hex_c[2:4],16), int(hex_c[4:6],16)
    variants = []
    for dr, dg, db in [(delta,0,0),(-delta,0,0),(0,delta,0),(0,-delta,0),
                       (0,0,delta),(0,0,-delta),(delta,delta,0),(-delta,-delta,0)]:
        nr = np.clip(r+dr, 0, 255)
        ng = np.clip(g+dg, 0, 255)
        nb = np.clip(b+db, 0, 255)
        variants.append(f'#{int(nr):02X}{int(ng):02X}{int(nb):02X}')
    return variants


def jaccard(a: list, b: list) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0


def kendall_tau_top(a: list, b: list) -> float:
    """Kendall τ over union(a,b), treating absent items as rank=len+1."""
    items = list(dict.fromkeys(a + b))  # preserve order, deduplicate
    def rank(lst):
        r = {x: i for i, x in enumerate(lst)}
        return [r.get(x, len(lst)) for x in items]
    ra, rb = rank(a), rank(b)
    tau, _ = ss.kendalltau(ra, rb)
    return round(float(tau), 4)


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    n   = rec.n_songs

    art_col  = rec.artist_col or 'artists'
    artists  = rec.df[art_col].fillna('__unknown__').astype(str).values
    art_freq = Counter(artists)
    max_freq = max(art_freq.values())
    # Popularity proxy: normalised artist frequency
    pop_proxy = np.array([art_freq[a] / max_freq for a in artists], float)

    # Collect all recommendations across 12 colours
    all_recs:   list[int] = []
    color_recs: dict[str, list[int]] = {}
    for hx, _ in ICEAS_COLS:
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        idxs = df['original_index'].tolist() if (
            df is not None and not df.empty and 'original_index' in df.columns) else []
        color_recs[hx] = idxs
        all_recs.extend(idxs)

    # ── B5: Popularity-bias ───────────────────────────────────────────────────
    item_freq  = Counter(all_recs)
    item_counts = np.array([item_freq.get(i, 0) for i in range(n)], float)
    rec_counts  = np.array([v for v in item_freq.values()], float)

    gini_items  = gini(rec_counts)
    ent_items   = entropy_norm(item_counts[item_counts > 0])
    # ARP = mean popularity of recommended items (Abdollahpouri 2021)
    arp         = float(np.mean([pop_proxy[i] for i in all_recs])) if all_recs else 0.0
    catalog_pop = float(pop_proxy.mean())  # catalog-average popularity
    coverage    = len(item_freq) / n

    print("=" * 60)
    print("B5 — POPULARITY BIAS SUITE")
    print("=" * 60)
    print(f"  Item Gini:          {gini_items:.4f}  (0=equal, 1=monopoly)")
    print(f"  Item entropy (norm):{ent_items:.4f}  (1=uniform)")
    print(f"  ARP:                {arp:.4f}  (catalog mean: {catalog_pop:.4f})")
    print(f"  Coverage:           {len(item_freq)}/{n} = {coverage:.1%}")
    arp_note = "ABOVE catalog mean → popularity bias" if arp > catalog_pop + 0.02 else \
               "≈ catalog mean → no significant popularity bias"
    print(f"  ARP vs catalog:     {arp_note}")

    # ── B6: Artist fairness ───────────────────────────────────────────────────
    rec_artists   = [artists[i] for i in all_recs]
    artist_exp    = Counter(rec_artists)
    exp_counts    = np.array(list(artist_exp.values()), float)
    gini_artists  = gini(exp_counts)
    n_distinct_artists = len(artist_exp)

    # Group fairness: popular artists (top-20%) vs niche (bottom-80%)
    all_artists_sorted = sorted(art_freq, key=art_freq.get, reverse=True)
    top20_artists  = set(all_artists_sorted[:max(1, len(all_artists_sorted)//5)])
    niche_artists  = set(all_artists_sorted) - top20_artists
    exp_top20  = sum(artist_exp.get(a,0) for a in top20_artists)
    exp_niche  = sum(artist_exp.get(a,0) for a in niche_artists)
    total_exp  = exp_top20 + exp_niche
    pct_top20  = exp_top20 / total_exp if total_exp else 0

    print("\n" + "=" * 60)
    print("B6 — ARTIST FAIRNESS")
    print("=" * 60)
    print(f"  Artist Gini:        {gini_artists:.4f}")
    print(f"  Distinct artists:   {n_distinct_artists} / {len(art_freq)} total")
    print(f"  Top-20% artists get {pct_top20:.1%} of exposure")
    print(f"  Niche artists get   {1-pct_top20:.1%} of exposure")
    fairness_note = "top-20% dominate (>60%)" if pct_top20 > 0.60 else \
                    "exposure reasonably distributed"
    print(f"  Assessment:         {fairness_note}")

    # Per-artist top-10 most exposed
    print("  Top-10 most exposed artists:")
    for art, cnt in artist_exp.most_common(10):
        slots = round(cnt / len(ICEAS_COLS), 1)
        print(f"    {art[:35]:35} {cnt:4} slots (~{slots:.1f}/colour)")

    # ── B7: Serendipity (unexpectedness) ─────────────────────────────────────
    # Unexpectedness: how surprising is an item vs global popularity?
    # unexp(i) = 1 - pop_proxy(i);  mean over all recs
    unexp_vals = [1.0 - pop_proxy[i] for i in all_recs]
    mean_unexp = float(np.mean(unexp_vals))
    catalog_unexp = float(np.mean(1.0 - pop_proxy))  # baseline

    print("\n" + "=" * 60)
    print("B7a — SERENDIPITY (unexpectedness, label-free)")
    print("=" * 60)
    print(f"  Mean unexpectedness: {mean_unexp:.4f}  (catalog: {catalog_unexp:.4f})")
    unexp_note = "system recommends LESS popular items than catalog avg (serendipitous)" \
        if mean_unexp > catalog_unexp else \
        "system recommends MORE popular items than catalog avg (popularity-biased)"
    print(f"  → {unexp_note}")

    # ── B7b: Robustness (perturbation) ───────────────────────────────────────
    print("\n" + "=" * 60)
    print("B7b — ROBUSTNESS (colour perturbation ±8 RGB)")
    print("=" * 60)
    print(f"  {'colour':20} {'mean_Jaccard':>12} {'mean_KendallT':>14} {'min_Jac':>8}")

    robustness_per_color = {}
    all_jaccards, all_taus = [], []

    for hx, name in ICEAS_COLS:
        orig = color_recs[hx]
        if not orig:
            continue
        variants = perturb_hex(hx, delta=8)
        jaccards, taus = [], []
        for vhx in variants:
            try:
                df_v = rec.recommend_by_colors(vhx, top_k=TOP_K)
                pert = df_v['original_index'].tolist() if (
                    df_v is not None and not df_v.empty) else []
                if pert:
                    jaccards.append(jaccard(orig, pert))
                    taus.append(kendall_tau_top(orig, pert))
            except Exception:
                pass
        if jaccards:
            mj = float(np.mean(jaccards))
            mt = float(np.mean(taus))
            robustness_per_color[hx] = {
                'mean_jaccard': round(mj, 4), 'mean_kendall_tau': round(mt, 4),
                'min_jaccard':  round(float(np.min(jaccards)), 4)
            }
            all_jaccards.extend(jaccards); all_taus.extend(taus)
            print(f"  {name+' '+hx:20} {mj:>12.3f} {mt:>14.3f} {float(np.min(jaccards)):>8.3f}")

    mean_jac = float(np.mean(all_jaccards)) if all_jaccards else 0
    mean_tau = float(np.mean(all_taus))     if all_taus     else 0
    print(f"  {'MEAN':20} {mean_jac:>12.3f} {mean_tau:>14.3f}")
    rob_note = "stable" if mean_jac >= 0.5 else "somewhat sensitive" if mean_jac >= 0.3 else "fragile"
    print(f"  Robustness: mean Jaccard={mean_jac:.3f} → {rob_note}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  B5 Popularity-bias:  Gini={gini_items:.3f}  ARP {'> catalog (bias)' if arp>catalog_pop+0.02 else '≈ catalog (OK)'}")
    print(f"  B6 Artist fairness:  Gini={gini_artists:.3f}  top-20%→{pct_top20:.1%} exposure")
    print(f"  B7 Serendipity:      mean_unexp={mean_unexp:.3f}  ({'> catalog ✓' if mean_unexp>=catalog_unexp else '< catalog ✗'})")
    print(f"  B7 Robustness:       mean_Jaccard={mean_jac:.3f} ({rob_note})")

    report = {
        "top_k": TOP_K,
        "B5_popularity_bias": {
            "item_gini": round(gini_items, 4),
            "item_entropy_norm": ent_items,
            "arp": round(arp, 4),
            "catalog_mean_pop": round(catalog_pop, 4),
            "arp_above_catalog": bool(arp > catalog_pop + 0.02),
            "coverage_pct": round(coverage, 4),
            "n_unique_items": len(item_freq),
        },
        "B6_artist_fairness": {
            "artist_gini": round(gini_artists, 4),
            "n_distinct_artists_in_recs": n_distinct_artists,
            "n_total_artists": len(art_freq),
            "pct_top20_artists_exposure": round(pct_top20, 4),
            "top_10_artists": dict(artist_exp.most_common(10)),
        },
        "B7a_serendipity": {
            "mean_unexpectedness": round(mean_unexp, 4),
            "catalog_unexpectedness": round(catalog_unexp, 4),
            "above_catalog": bool(mean_unexp >= catalog_unexp),
        },
        "B7b_robustness": {
            "perturbation_delta": 8,
            "n_variants": 8,
            "mean_jaccard": round(mean_jac, 4),
            "mean_kendall_tau": round(mean_tau, 4),
            "assessment": rob_note,
            "per_color": robustness_per_color,
        },
        "basis": (
            "B5: Abdollahpouri 2021 (arXiv:2103.06364); Duricic 2023 (Frontiers Big Data); "
            "B6: Klimashevskaia 2024 (UMUAI); "
            "B7: Kaminskas&Bridge 2017 (ACM TiiS); Vargas&Castells 2011."
        ),
    }
    json.dump(report, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    return report


if __name__ == "__main__":
    run()
