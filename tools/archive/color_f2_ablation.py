"""F2 — Ablation: confirm that dropping lyr-cosine and emo-cosine is safe (V19).

Tests three weight configurations on the F1 evaluation suite:
  A) Production current : lyrics=0.35  va=0.55  emotion=0.10
  B) V-A only          : lyrics=0.00  va=1.00  emotion=0.00  ← science-backed default
  C) VA + lyr, no emo  : lyrics=0.35  va=0.65  emotion=0.00  ← intermediate

Hypothesis (Whiteford 2018 + anisotropy Li 2020):
  • Dropping emo (double-counts V-A)   → no harm
  • Dropping lyr-cosine (near-noise)   → no harm or improvement
  • B ≥ A on editorial Qprec (majority correct quadrant)

Evaluation is on F1 tools (editorial artist-grouped Qprec + structural battery),
both already validated as non-circular.

Usage: python -m tools.color_f2_ablation
"""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

OUT = 'var/runtime/backtest/reports/color_f2_ablation.json'

CONFIGS = {
    'A_production': {'lyrics': 0.35, 'va': 0.55, 'emotion': 0.10},
    'B_va_only':    {'lyrics': 0.00, 'va': 1.00, 'emotion': 0.00},
    'C_va_lyr':     {'lyrics': 0.35, 'va': 0.65, 'emotion': 0.00},
}

ICEAS_COLS = [
    ('#BE0032','red'),('#F38400','orange'),('#F3C300','yellow'),('#FFB7C5','pink'),
    ('#008856','green'),('#3AB09E','turquoise'),('#0067A5','blue'),('#9C4F96','purple'),
    ('#80461B','brown'),('#F2F3F4','white'),('#848482','grey'),('#222222','black'),
]

HEX_REMAP = {
    '#FF0000':'#BE0032','#FF8000':'#F38400','#FFFF00':'#F3C300',
    '#FFC0CB':'#FFB7C5','#008000':'#008856','#40E0D0':'#3AB09E',
    '#0000FF':'#0067A5','#800080':'#9C4F96','#8B4513':'#80461B',
    '#FFFFFF':'#F2F3F4','#808080':'#848482','#000000':'#222222',
}

TOP_K = 10


def _quadrant(v, a):
    if v >= 0.5 and a >= 0.5: return 'Q1'
    if v <  0.5 and a >= 0.5: return 'Q2'
    if v <  0.5 and a <  0.5: return 'Q3'
    return 'Q4'


def _spearman(x, y):
    x, y = np.asarray(x,float), np.asarray(y,float)
    if len(x)<3: return float('nan')
    rx=np.argsort(np.argsort(x)).astype(float); ry=np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx,ry)[0,1])


def eval_editorial(rec, gt, sq):
    """Return macro quadrant-precision across colours with ≥1 relevant."""
    qprec = []
    for hx, _ in ICEAS_COLS:
        entry = gt.get(hx)
        if not entry or not entry.get('relevant'): continue
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        tq = _quadrant(cv, ca)
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        if df is None or df.empty: continue
        res = df['original_index'].tolist()
        res_q = [sq[r] for r in res if r < len(sq)]
        qprec.append(sum(1 for q in res_q if q==tq)/len(res_q) if res_q else 0)
    return float(np.mean(qprec)) if qprec else 0.0


def eval_structural(rec):
    """T1 monotonicity + T2 commensurability — key structural tests."""
    color_va = {hx: rec.color_mapper.hsl_to_va(hx) for hx,_ in ICEAS_COLS}
    top_mean = {}
    for hx,_ in ICEAS_COLS:
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        if df is None or df.empty: top_mean[hx]=None; continue
        top_mean[hx] = rec.song_va[df['original_index'].tolist()].mean(axis=0)
    # T1
    c_v=[color_va[hx][0] for hx,_ in ICEAS_COLS]; c_a=[color_va[hx][1] for hx,_ in ICEAS_COLS]
    s_v=[top_mean[hx][0] if top_mean[hx] is not None else float('nan') for hx,_ in ICEAS_COLS]
    s_a=[top_mean[hx][1] if top_mean[hx] is not None else float('nan') for hx,_ in ICEAS_COLS]
    rho_v=_spearman(c_v,s_v); rho_a=_spearman(c_a,s_a)
    # T2 valence slope
    pts=[(color_va[hx][0],top_mean[hx][0]) for hx,_ in ICEAS_COLS if top_mean[hx] is not None]
    x,y=zip(*pts); x,y=np.array(x),np.array(y)
    slope_v=float(np.polyfit(x,y,1)[0]); r_v=float(np.corrcoef(x,y)[0,1])
    return {'mono_V':round(rho_v,3),'mono_A':round(rho_a,3),
            'comm_slope_V':round(slope_v,3),'comm_r_V':round(r_v,3)}


def main() -> int:
    import core.recommendation_engine as eng
    from core.recommendation_engine import get_recommender

    gt_raw = json.load(open('var/runtime/backtest/ground_truth/color_editorial_gt_v1.json'))
    gt_raw = gt_raw.get('colors', gt_raw)
    gt = {HEX_REMAP.get(hx,hx): e for hx,e in gt_raw.items()}

    rec = get_recommender()
    n = rec.n_songs
    sq = [_quadrant(rec.song_va[i,0], rec.song_va[i,1]) for i in range(n)]
    orig_w = dict(eng.COLOR_SCORE_WEIGHTS)

    results = {}
    print(f"\n{'='*70}\nF2 ABLATION — editorial Qprec + structural (top_k={TOP_K})\n{'='*70}")
    print(f"{'Config':<22} {'Qprec':>8} {'mono_V':>8} {'mono_A':>8} {'comm_sV':>9} {'comm_r':>8}")

    for name, weights in CONFIGS.items():
        eng.COLOR_SCORE_WEIGHTS = dict(weights)
        qp   = eval_editorial(rec, gt, sq)
        st   = eval_structural(rec)
        results[name] = {'weights': weights, 'editorial_qprec': round(qp,4),
                         'structural': st}
        print(f"{name:<22} {qp:>8.3f} {st['mono_V']:>8.3f} {st['mono_A']:>8.3f} "
              f"{st['comm_slope_V']:>9.3f} {st['comm_r_V']:>8.3f}")

    eng.COLOR_SCORE_WEIGHTS = orig_w   # restore

    # Verdict
    qp_a = results['A_production']['editorial_qprec']
    qp_b = results['B_va_only']['editorial_qprec']
    qp_c = results['C_va_lyr']['editorial_qprec']

    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"  A production  Qprec={qp_a:.3f}")
    print(f"  B va_only     Qprec={qp_b:.3f}  Δ vs A = {qp_b-qp_a:+.3f}")
    print(f"  C va+lyr      Qprec={qp_c:.3f}  Δ vs A = {qp_c-qp_a:+.3f}")

    safe_to_drop_emo = qp_b >= qp_a - 0.05   # B drops both emo+lyr, tolerance 5pp
    safe_to_drop_lyr = qp_c >= qp_a - 0.05   # C drops only emo
    adopt_b = qp_b >= qp_a - 0.05            # V-A-only defensible

    print()
    if adopt_b:
        print("  ✓ V-A-only (B) within 5pp of production → SAFE to adopt V-A-only")
        print("  → Proceed to F3: replace _color_score with V-A heteroscedastic only")
    else:
        print("  ⚠ V-A-only drops >5pp — investigate before F3")

    results['verdict'] = {
        'drop_emo_safe': bool(safe_to_drop_emo),
        'drop_lyr_safe': bool(safe_to_drop_lyr),
        'adopt_va_only': bool(adopt_b),
        'delta_B_vs_A': round(float(qp_b-qp_a),4),
        'delta_C_vs_A': round(float(qp_c-qp_a),4),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(results, open(OUT,'w'), indent=2)
    print(f"\n  saved → {OUT}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
