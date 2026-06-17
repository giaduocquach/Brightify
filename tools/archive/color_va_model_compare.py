"""Compare colour→V-A models against the ICEAS human norms + test full-space generalization.

Motivation: the bridge was fit on only n=12 ICEAS colours → can't recover true structure
(V33 arousal underweighted saturation: 0.087 vs the authoritative 0.60). This adopts the
large-sample published equations:
  Valdez & Mehrabian 1994 (~76 Munsell colours): Arousal = 0.60·S − 0.31·B,
                                                 Pleasure = 0.69·B + 0.22·S  (standardized)
  Wilms & Oberfeld 2018 (30 colours): + secondary hue effect (arousal rises blue→green→red)
We use ICEAS-12 only to CALIBRATE scale (2-param affine), letting the 76-colour structure
generalize. Reports: ICEAS corr/mae for VM vs V33-fit vs Oklab; and a grid smoothness check
(VM should be monotonic in S/B where the n=12 fit overfits between anchors).

Run: python -m tools.color_va_model_compare
"""
from __future__ import annotations
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.advanced_color_mapping import get_advanced_color_mapper

# ICEAS Jonauskaite 2020 Table 2 human norms (V, A)
ICEAS = {
 '#BE0032':(0.35,0.72),'#F38400':(0.68,0.65),'#F3C300':(0.73,0.62),'#FFB7C5':(0.75,0.48),
 '#008856':(0.62,0.43),'#3AB09E':(0.70,0.42),'#0067A5':(0.55,0.45),'#9C4F96':(0.45,0.50),
 '#80461B':(0.30,0.42),'#F2F3F4':(0.65,0.32),'#848482':(0.30,0.40),'#222222':(0.18,0.58)}
W_HUE = 0.10   # Wilms-Oberfeld secondary hue (redness) effect on arousal


def _feats(cm, hx):
    h, l, s = cm.hex_to_hsl(hx)
    s01, l01 = s / 100.0, l / 100.0
    redness = 0.5 if s01 < 0.12 else (1 + np.cos(np.deg2rad(h))) / 2
    return s01, l01, redness


def _affine_to(raw, target):
    """Least-squares affine raw→target (slope+intercept); returns (a,b,calibrated)."""
    A = np.vstack([raw, np.ones_like(raw)]).T
    (a, b), *_ = np.linalg.lstsq(A, target, rcond=None)
    return float(a), float(b), np.clip(a * raw + b, 0, 1)


def main() -> int:
    from scipy.stats import pearsonr
    cm = get_advanced_color_mapper()
    hexes = list(ICEAS)
    S = np.array([_feats(cm, h)[0] for h in hexes])
    L = np.array([_feats(cm, h)[1] for h in hexes])
    R = np.array([_feats(cm, h)[2] for h in hexes])
    tv = np.array([ICEAS[h][0] for h in hexes])
    ta = np.array([ICEAS[h][1] for h in hexes])

    # Valdez-Mehrabian raw, then affine-calibrate scale to ICEAS
    vm_a_raw = 0.60 * S - 0.31 * L + W_HUE * R
    vm_v_raw = 0.69 * L + 0.22 * S
    aa, ab, vm_a = _affine_to(vm_a_raw, ta)
    va, vb, vm_v = _affine_to(vm_v_raw, tv)

    # current model (whatever flags are on) for comparison
    cur_v, cur_a = np.array([cm.hsl_to_va(h) for h in hexes]).T

    def rpt(name, pred, truth):
        r = pearsonr(pred, truth)[0]; mae = np.mean(np.abs(pred - truth))
        print(f"  {name:22} r={r:+.3f}  mae={mae:.3f}")

    print("=== AROUSAL vs ICEAS-12 ===")
    rpt("Valdez-Mehrabian", vm_a, ta)
    rpt("current (V33 fit)", cur_a, ta)
    print(f"  VM arousal calib: a={aa:.4f} b={ab:.4f}  (apply to 0.60*s -0.31*l +{W_HUE}*redness)")
    print("=== VALENCE vs ICEAS-12 ===")
    rpt("Valdez-Mehrabian", vm_v, tv)
    rpt("current (Oklab)", cur_v, tv)
    print(f"  VM valence calib: a={va:.4f} b={vb:.4f}")

    # Generalization / smoothness on a dense grid (monotonic in S and B?)
    print("\n=== GENERALIZATION: arousal vs SATURATION (hsl_to_hex(h,s,l); fix l=50) — should ↑ with S ===")
    for nm, hue in [('red(0)', 0), ('green(140)', 140), ('blue(220)', 220)]:
        row = []
        for s in [10, 40, 70, 100]:
            hx = cm.hsl_to_hex(hue, s, 50)        # (h, s, l) — vary saturation, fix lightness
            _, a = cm.hsl_to_va(hx)
            sr, lr, rr = _feats(cm, hx)
            a_vm = float(np.clip(aa * (0.60 * sr - 0.31 * lr + W_HUE * rr) + ab, 0, 1))
            row.append(f"S{s}: cur={a:.2f} VM={a_vm:.2f}")
        print(f"  {nm:10} " + " | ".join(row))
    print("  (Valdez-Mehrabian: arousal MUST rise with saturation; flag if current is flat/backwards)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
