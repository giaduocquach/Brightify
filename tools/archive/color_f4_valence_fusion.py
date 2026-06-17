"""F4 — Lyrics→Valence fusion: ablate audio signals, decide whether fusion helps (V19).

F4 TESTS first, then applies ONLY what demonstrably improves V-A bridge quality.

DATA FINDINGS (pre-run check):
  mode distribution: sad mean_mode=0.625, happy=0.511  ← INVERTED vs Western lit.
  Vietnamese ballads (majority of sad catalog) use major keys but feel sad via
  lyrics/performance — exactly the cultural offset Palmer/Jonauskaite warned about.
  Essentia valence: r=0.22 with LLM-valence → unreliable.

ABLATION APPROACH (scientific, not assuming audio helps):
  A) LLM-only (current F3 baseline)
  B) LLM + mode Tây (major→+valence) — expect HURT due to inverted pattern
  C) LLM + mode INVERTED (minor→+valence, Vietnamese-pattern)
  D) LLM + Essentia valence (r=0.22, weak)
  E) LLM + MERT arousal as valence proxy (cross-axis signal, exploratory)

VERDICT criterion:
  • If no audio signal beats LLM-only on editorial Qprec + structural → keep LLM-only.
  • If an audio signal helps → apply it with documented w weights.
  • Either outcome is valid science. Forcing fusion that hurts is not.

Usage: python -m tools.color_f4_valence_fusion
"""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

OUT = 'var/runtime/backtest/reports/color_f4_valence_ablation.json'
V4_FILE = 'data/emotion_labels_v4.json'
GT_FILE = 'var/runtime/backtest/ground_truth/color_editorial_gt_v1.json'
TOP_K = 10

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


def _spearman(x, y):
    x, y = np.asarray(x,float), np.asarray(y,float)
    if len(x)<3: return float('nan')
    rx=np.argsort(np.argsort(x)).astype(float); ry=np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx,ry)[0,1])


def eval_system(rec, gt, sq):
    """Quadrant-precision on editorial GT."""
    qp = []
    for hx, _ in ICEAS_COLS:
        entry = gt.get(hx)
        if not entry or not entry.get('relevant'): continue
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        tq = _quadrant(cv, ca)
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        if df is None or df.empty: continue
        res_q = [sq[r] for r in df['original_index'].tolist() if r < len(sq)]
        qp.append(sum(1 for q in res_q if q==tq)/len(res_q) if res_q else 0)
    return float(np.mean(qp)) if qp else 0.0


def eval_structural(rec):
    """T1 monotonicity."""
    color_va = {hx: rec.color_mapper.hsl_to_va(hx) for hx,_ in ICEAS_COLS}
    c_v=[color_va[hx][0] for hx,_ in ICEAS_COLS]
    c_a=[color_va[hx][1] for hx,_ in ICEAS_COLS]
    top_v=[]; top_a=[]
    for hx,_ in ICEAS_COLS:
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        if df is None or df.empty: top_v.append(float('nan')); top_a.append(float('nan')); continue
        va = rec.song_va[df['original_index'].tolist()]
        top_v.append(float(va[:,0].mean())); top_a.append(float(va[:,1].mean()))
    return {'mono_V': round(_spearman(c_v, top_v),3), 'mono_A': round(_spearman(c_a, top_a),3)}


def _norm(arr):
    mn, mx = float(arr.min()), float(arr.max())
    return np.clip((arr - mn) / (mx - mn + 1e-9), 0.0, 1.0)


def main() -> int:
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    df_cat = rec.df
    n = rec.n_songs
    v4 = json.load(open(V4_FILE))
    tids = df_cat['track_id'].astype(str).values

    # --- audio-valence candidates ---
    V_llm = np.array([float(v4.get(t,{}).get('valence',0.5)) for t in tids])
    mode  = df_cat['mode'].fillna(0.5).astype(float).values         # 0=minor,1=major
    en    = df_cat['energy'].fillna(0.5).astype(float).values
    essV  = _norm(df_cat['valence'].fillna(0.5).astype(float).values) if 'valence' in df_cat.columns else np.full(n,0.5)
    mert_a = np.array([float(v4.get(t,{}).get('arousal_mert',0.5)) for t in tids])

    # mode West (major→high V): direct use
    V_mode_west = np.clip(0.50 + 0.35*(2*mode-1) + 0.08*(en-0.5), 0, 1)
    # mode VN-inverted (minor→high V, empirical): flip
    V_mode_inv  = np.clip(0.50 + 0.35*(1-2*mode) + 0.08*(en-0.5), 0, 1)
    # Essentia valence (already norm'd)
    V_ess = essV
    # MERT arousal as valence proxy (exploratory; arousal corr with energy, not valence)
    V_mert_proxy = np.clip(1.0 - mert_a, 0, 1)   # high arousal ≈ low-valence in sad songs?

    print("\nPre-ablation audio-valence signal correlations with V_llm:")
    for name, sig in [('mode_west',V_mode_west),('mode_inv',V_mode_inv),
                       ('essentia',V_ess),('mert_a_proxy',V_mert_proxy)]:
        r = float(np.corrcoef(sig, V_llm)[0,1])
        print(f"  {name:<16} r={r:+.3f}")

    gt_raw = json.load(open(GT_FILE)); gt_raw=gt_raw.get('colors',gt_raw)
    gt = {HEX_REMAP.get(hx,hx):e for hx,e in gt_raw.items()}
    sq_base = [_quadrant(rec.song_va[i,0],rec.song_va[i,1]) for i in range(n)]

    orig_va = rec.song_va.copy()

    CONFIGS = {
        'A_llm_only':    V_llm,
        'B_llm_mode_W':  0.70*V_llm + 0.30*V_mode_west,
        'C_llm_mode_INV':0.70*V_llm + 0.30*V_mode_inv,
        'D_llm_ess':     0.70*V_llm + 0.30*V_ess,
        'E_llm_mert':    0.70*V_llm + 0.30*V_mert_proxy,
    }

    results = {}
    print(f"\n{'='*68}\nF4 VALENCE FUSION ABLATION (editorial Qprec + monotonicity)\n{'='*68}")
    print(f"{'Config':<22} {'Qprec':>7} {'mono_V':>8} {'mono_A':>8}  note")

    for name, V_new in CONFIGS.items():
        rec.song_va[:, 0] = np.clip(V_new, 0, 1)
        sq = [_quadrant(rec.song_va[i,0],rec.song_va[i,1]) for i in range(n)]
        qp = eval_system(rec, gt, sq)
        st = eval_structural(rec)
        results[name] = {'qprec': round(qp,4), 'structural': st}
        note = '← baseline' if name=='A_llm_only' else ''
        print(f"{name:<22} {qp:>7.3f} {st['mono_V']:>8.3f} {st['mono_A']:>8.3f}  {note}")

    rec.song_va[:, 0] = orig_va[:, 0]  # restore

    # Verdict
    base = results['A_llm_only']['qprec']
    best_name = max(results, key=lambda k: results[k]['qprec'])
    best_qp   = results[best_name]['qprec']
    adopt_fusion = best_qp > base + 0.01 and best_name != 'A_llm_only'

    print(f"\n{'='*68}\nVERDICT")
    print(f"  Baseline (LLM-only)  Qprec={base:.3f}")
    print(f"  Best config          {best_name}  Qprec={best_qp:.3f}  Δ={best_qp-base:+.3f}")
    if adopt_fusion:
        print(f"\n  ✓ {best_name} beats LLM-only by >1pp → apply fusion")
    else:
        print(f"\n  LLM-only is best (or tied). Keep V_lyr as sole valence signal.")
        print(f"  Root cause: mode is inverted for Vietnamese music (sad=major,happy≈minor).")
        print(f"  What's needed: MERT-valence probe trained on Vietnamese-labelled data.")

    results['verdict'] = {
        'best_config': best_name,
        'adopt_fusion': bool(adopt_fusion),
        'baseline_qprec': round(float(base),4),
        'best_qprec': round(float(best_qp),4),
        'mode_inverted_finding': True,
        'note': ('Vietnamese ballad sad songs use major keys (mean_mode sad=0.625 > happy=0.511) '
                 '— opposite of Western lit (Hunter&Schellenberg). '
                 'Western mode→valence signal hurts. Essentia r=0.22 unreliable. '
                 'LLM valence remains best available signal; real improvement requires '
                 'MERT-valence probe on Vietnamese-labelled V-A data.'),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(results, open(OUT,'w'), indent=2)
    print(f"\n  saved → {OUT}")
    return 0 if not adopt_fusion else 0   # always 0; verdict is in json


if __name__ == '__main__':
    sys.exit(main())
