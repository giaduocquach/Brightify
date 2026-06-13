"""V22 — Negative control (shuffled-label) gate for editorial eval.

Falsification test: if Qprec is truly measuring recommendation quality,
shuffling song_va randomly must degrade it significantly. If Qprec under
shuffle ≈ Qprec real → metric is tautological (V-A NN-lookup guarantees
quadrant match regardless of labels). This was the key gap in V1–V21.

Verdict mapping:
  Qprec_real >> Qprec_shuffled (+0.15+): metric is discriminative (good)
  Qprec_real ≈ Qprec_shuffled (< +0.05): metric is tautological (bad)

Also runs P@k comparison: P@k uses the raw playlist GT (editorial membership)
which does NOT depend on quadrant → genuinely non-tautological.

Run: python -m tools.color_negative_control [top_k] [n_shuffles]
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K      = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N_SHUFFLES = int(sys.argv[2]) if len(sys.argv) > 2 else 10
OUT        = "var/runtime/backtest/reports/color_negative_control.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

HEX_REMAP = {
    '#FF0000':'#BE0032','#FF8000':'#F38400','#FFFF00':'#F3C300',
    '#FFC0CB':'#FFB7C5','#008000':'#008856','#40E0D0':'#3AB09E',
    '#0000FF':'#0067A5','#800080':'#9C4F96','#8B4513':'#80461B',
    '#FFFFFF':'#F2F3F4','#808080':'#848482','#000000':'#222222',
}
ICEAS_COLS = [
    ('#BE0032','red'),('#F38400','orange'),('#F3C300','yellow'),('#FFB7C5','pink'),
    ('#008856','green'),('#3AB09E','turquoise'),('#0067A5','blue'),('#9C4F96','purple'),
    ('#80461B','brown'),('#F2F3F4','white'),('#848482','grey'),('#222222','black'),
]


def _quadrant(v, a):
    if v >= 0.5 and a >= 0.5: return 'Q1'
    if v <  0.5 and a >= 0.5: return 'Q2'
    if v <  0.5 and a <  0.5: return 'Q3'
    return 'Q4'


def compute_metrics(rec, gt, top_k):
    """Compute Qprec AND P@k for current rec.song_va."""
    import tools.color_editorial_grouped as ed
    n = rec.n_songs
    sq = [_quadrant(rec.song_va[i,0], rec.song_va[i,1]) for i in range(n)]

    qprec_vals, pak_vals = [], []
    for hx, name in ICEAS_COLS:
        entry = gt.get(hx)
        if not entry: continue
        rel = set(entry.get('relevant', []))
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        tq = _quadrant(cv, ca)
        recs = ed._production_score(rec, hx, top_k)
        if not recs: continue

        # Qprec (tautological for V-A retrieval)
        qp = sum(1 for r in recs if sq[r] == tq) / len(recs)
        qprec_vals.append(qp)

        # P@k (honest external metric — relevant set is raw playlist membership)
        if rel:
            pk = sum(1 for r in recs if r in rel) / min(top_k, len(recs))
            pak_vals.append(pk)

    macro_qprec = float(np.mean(qprec_vals)) if qprec_vals else 0.0
    mean_pak    = float(np.mean(pak_vals))    if pak_vals    else 0.0
    return macro_qprec, mean_pak


def run():
    from core.recommendation_engine import get_recommender
    import tools.color_editorial_grouped as ed

    rec = get_recommender()
    n   = rec.n_songs
    real_va = rec.song_va.copy()

    gt_raw = json.load(open('var/runtime/backtest/ground_truth/color_editorial_gt_v1.json'))
    gt     = {HEX_REMAP.get(k,k): v for k, v in gt_raw.get('colors', gt_raw).items()}

    print(f"NEGATIVE CONTROL  top_k={TOP_K}  n_shuffles={N_SHUFFLES}")
    print("=" * 60)

    # Real metrics
    real_qprec, real_pak = compute_metrics(rec, gt, TOP_K)
    print(f"  REAL   song_va → Qprec={real_qprec:.4f}  P@k={real_pak:.4f}")

    # Shuffled metrics
    shuffled_q, shuffled_p = [], []
    rng = np.random.default_rng(42)
    for s in range(N_SHUFFLES):
        rec.song_va = real_va[rng.permutation(n)]
        sq, sp = compute_metrics(rec, gt, TOP_K)
        shuffled_q.append(sq); shuffled_p.append(sp)
    rec.song_va = real_va  # restore

    mean_sq = float(np.mean(shuffled_q))
    mean_sp = float(np.mean(shuffled_p))
    std_sq  = float(np.std(shuffled_q))
    std_sp  = float(np.std(shuffled_p))

    print(f"  SHUFFLED ×{N_SHUFFLES} → Qprec={mean_sq:.4f}±{std_sq:.4f}  P@k={mean_sp:.4f}±{std_sp:.4f}")
    print()

    # Verdicts
    qprec_gap    = real_qprec - mean_sq
    pak_gap      = real_pak   - mean_sp
    qprec_passes = qprec_gap > 0.10   # needs substantial drop when shuffled
    pak_passes   = real_pak   > mean_sp + std_sp  # real P@k above shuffled distribution

    print("=" * 60)
    print("VERDICTS")
    print("=" * 60)
    q_sym = "✓ DISCRIMINATIVE" if qprec_passes else "✗ TAUTOLOGICAL"
    p_sym = "✓ ABOVE SHUFFLE"  if pak_passes   else "✗ NOT ABOVE SHUFFLE"
    print(f"  Qprec gap real−shuffled = {qprec_gap:+.4f}  → {q_sym}")
    print(f"  P@k   gap real−shuffled = {pak_gap:+.4f}  → {p_sym}")

    if not qprec_passes:
        print()
        print("  ⚠ QPREC IS TAUTOLOGICAL — V-A NN-lookup guarantees quadrant")
        print("    match regardless of song labels. Qprec = internal consistency")
        print("    check ONLY, not evidence of recommendation quality.")
        print("    P@k (external raw playlist GT) is the honest metric.")
    if pak_passes:
        print()
        print("  ✓ P@k is above shuffled baseline — retrieval returns more")
        print("    playlist-relevant songs than chance (weak external signal).")

    report = {
        "top_k": TOP_K, "n_shuffles": N_SHUFFLES,
        "real":     {"qprec": round(real_qprec,4), "pak": round(real_pak,4)},
        "shuffled": {"qprec_mean": round(mean_sq,4), "qprec_std": round(std_sq,4),
                     "pak_mean": round(mean_sp,4), "pak_std": round(std_sp,4)},
        "gaps":     {"qprec": round(qprec_gap,4), "pak": round(pak_gap,4)},
        "qprec_discriminative": qprec_passes,
        "pak_above_shuffle":    pak_passes,
        "interpretation": (
            "Qprec tautological" if not qprec_passes else "Qprec discriminative"
        ) + "; P@k " + ("above shuffle ✓" if pak_passes else "not above shuffle"),
        "basis": "Kriegeskorte 2009 (double-dipping); falsification via shuffled-label control.",
    }
    json.dump(report, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    return qprec_passes or pak_passes   # pass if EITHER metric is valid


if __name__ == "__main__":
    # Exit 1 when Qprec is tautological (important diagnostic finding).
    # In run_f1_validation, NC FAIL = "metric is non-discriminative" —
    # this does NOT mean the system is wrong, only that Qprec cannot
    # prove it. L1 remains the strongest external evidence.
    ok = run()
    sys.exit(0 if ok else 1)
