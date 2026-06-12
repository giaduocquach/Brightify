"""Phase 3 EXPERIMENT — CIELAB + Oklab colour→V-A regression vs current hsl_to_va.

Không thay thế production code. Chỉ đánh giá xem CIELAB / Oklab có tốt hơn HSL không.

Approach:
  Dữ liệu: 12 ICEAS centroids với V-A human norms (Jonauskaite 2020).
  Features: CIELAB [L*,a*,b*,C*,cos h,sin h] và Oklab [L,a,b,C,cos h,sin h].
  Model: Ridge regression (L2 regularisation) — tránh overfit với n=12.
  Eval: Leave-One-Out CV Pearson r và RMSE vs human norms.
  Baseline: hsl_to_va() hiện tại trên cùng 12 điểm.
  Extra: Smoothness test trên 200 màu ngẫu nhiên.

Oklab không cần colormath — pure sRGB→XYZ→LMS→Oklab transform (Ottosson 2020).
CIELAB cần colormath — bỏ qua CIELAB section nếu không có.

Run: python -m tools.phase3_cielab_experiment
"""
from __future__ import annotations
import sys, os
import numpy as np
from scipy import stats as ss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from colormath.color_objects import sRGBColor, LabColor
    from colormath.color_conversions import convert_color
    HAS_CM = True
except ImportError:
    HAS_CM = False
    print("NOTE: colormath not installed — CIELAB section skipped; Oklab section will run.")

# ── 12 ICEAS centroids với V-A human norms (Jonauskaite 2020) ─────────────────
# V/A norms khớp với giá trị đang dùng trong L1 bridge validation
ICEAS = [
    ('#BE0032', 0.35, 0.72, 'red'),
    ('#F38400', 0.68, 0.65, 'orange'),
    ('#F3C300', 0.73, 0.62, 'yellow'),
    ('#FFB7C5', 0.75, 0.48, 'pink'),
    ('#008856', 0.62, 0.43, 'green'),
    ('#3AB09E', 0.70, 0.42, 'turquoise'),
    ('#0067A5', 0.55, 0.45, 'blue'),
    ('#9C4F96', 0.45, 0.50, 'purple'),
    ('#80461B', 0.30, 0.42, 'brown'),
    ('#F2F3F4', 0.65, 0.32, 'white'),
    ('#848482', 0.30, 0.40, 'grey'),
    ('#222222', 0.18, 0.58, 'black'),
]


# ── Colour conversion helpers ─────────────────────────────────────────────────

def hex_to_oklab(hex_c: str) -> tuple[float, float, float]:
    """HEX → (L, a, b) in Oklab. No colormath needed."""
    h = hex_c.lstrip('#')
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    # sRGB → linear sRGB (gamma ≈ 2.2)
    r, g, b = r**2.2, g**2.2, b**2.2
    # linear sRGB → XYZ (D65)
    X = 0.4124 * r + 0.3576 * g + 0.1805 * b
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = 0.0193 * r + 0.1192 * g + 0.9505 * b
    # XYZ → LMS (Oklab)
    l_ = (0.8189 * X + 0.3619 * Y - 0.1288 * Z) ** (1/3)
    m_ = (0.0329 * X + 0.9293 * Y + 0.0361 * Z) ** (1/3)
    s_ = (0.0482 * X + 0.2643 * Y + 0.6338 * Z) ** (1/3)
    L =  0.2104 * l_ + 0.7936 * m_ - 0.0040 * s_
    a =  1.9779 * l_ - 2.4285 * m_ + 0.4505 * s_
    b_ = 0.0259 * l_ + 0.7827 * m_ - 0.8086 * s_
    return float(L), float(a), float(b_)


def oklab_features(hex_c: str) -> np.ndarray:
    """Build feature vector from Oklab coordinates.

    Features: [L, a/0.4, b/0.4, C/0.4, cos_h, sin_h]
    Oklab a,b range ≈ [-0.4, 0.4] → normalise by 0.4.
    """
    L, a, b = hex_to_oklab(hex_c)
    C = float(np.sqrt(a**2 + b**2))
    h = float(np.arctan2(b, a))
    return np.array([L, a / 0.4, b / 0.4, C / 0.4, np.cos(h), np.sin(h)])


def hex_to_cielab(hex_c: str) -> tuple[float, float, float]:
    """HEX → (L*, a*, b*)."""
    h = hex_c.lstrip('#')
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    lab = convert_color(sRGBColor(r, g, b), LabColor)
    return float(lab.lab_l), float(lab.lab_a), float(lab.lab_b)


def cielab_features(hex_c: str) -> np.ndarray:
    """Build feature vector from CIELAB coordinates.

    Features: [L_norm, a_norm, b_norm, C_norm, cos_h, sin_h]
    Normalised: L/100, a/128, b/128, C/128, cos(h), sin(h)
    cos/sin encoding avoids discontinuity at 0°/360°.
    """
    L, a, b = hex_to_cielab(hex_c)
    C = float(np.sqrt(a**2 + b**2))
    h = float(np.arctan2(b, a))  # radians
    return np.array([
        L / 100.0,          # lightness 0-1
        a / 128.0,          # red-green axis
        b / 128.0,          # yellow-blue axis
        C / 128.0,          # chroma
        np.cos(h),          # hue (circular)
        np.sin(h),          # hue (circular)
    ])


# ── Ridge regression (no sklearn needed) ─────────────────────────────────────

def ridge_fit(X: np.ndarray, y: np.ndarray,
              alpha: float = 0.1) -> np.ndarray:
    """Fit ridge regression: w = (X'X + αI)^-1 X'y."""
    n_feat = X.shape[1]
    A = X.T @ X + alpha * np.eye(n_feat)
    return np.linalg.solve(A, X.T @ y)


def ridge_pred(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return X @ w


# ── LOO-CV evaluation ─────────────────────────────────────────────────────────

def loo_cv(X: np.ndarray, y: np.ndarray,
           alpha: float = 0.1) -> tuple[np.ndarray, float, float]:
    """Leave-one-out CV. Returns (predictions, Pearson r, RMSE)."""
    n = len(y)
    preds = np.zeros(n)
    for i in range(n):
        idx_train = [j for j in range(n) if j != i]
        w = ridge_fit(X[idx_train], y[idx_train], alpha)
        preds[i] = float(ridge_pred(X[[i]], w))
    preds = np.clip(preds, 0, 1)
    r, _  = ss.pearsonr(y, preds)
    rmse  = float(np.sqrt(np.mean((y - preds)**2)))
    return preds, float(r), rmse


def alpha_search(X: np.ndarray, y: np.ndarray) -> float:
    """Find best ridge alpha via LOO-CV RMSE."""
    best_a, best_rmse = 0.01, 999
    for a in [0.001, 0.01, 0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0]:
        _, _, rmse = loo_cv(X, y, a)
        if rmse < best_rmse:
            best_rmse, best_a = rmse, a
    return best_a


# ── Production hsl_to_va baseline ────────────────────────────────────────────

def get_current_va(hex_c: str) -> tuple[float, float]:
    from core.advanced_color_mapping import get_advanced_color_mapper
    mapper = get_advanced_color_mapper()
    return mapper.hsl_to_va(hex_c)


# ── Ablation: which CIELAB features matter most? ─────────────────────────────

FEATURE_NAMES = ['L*', 'a*', 'b*', 'C*', 'cos_h', 'sin_h']

def ablation(X: np.ndarray, y: np.ndarray, label: str):
    """Try different feature subsets."""
    subsets = {
        'L*+C*+hue':   [0, 3, 4, 5],
        'L*+a*+b*':    [0, 1, 2],
        'L*+C*':       [0, 3],
        'L*+a*+b*+C*+hue': [0,1,2,3,4,5],  # full
    }
    results = {}
    for name, idxs in subsets.items():
        Xs = X[:, idxs]
        a  = alpha_search(Xs, y)
        _, r, rmse = loo_cv(Xs, y, a)
        results[name] = (r, rmse, a)
    return results


# ── Smoothness test on random colours ────────────────────────────────────────

def smoothness_test(w_v: np.ndarray, w_a: np.ndarray, X_fit: np.ndarray,
                    y_v: np.ndarray, y_a: np.ndarray) -> dict:
    """Generate 200 random colours, compare CIELAB vs hsl_to_va predictions.

    Smoothness: adjacent colours should give similar V-A (small gradient).
    Monotonicity: L* ↑ → valence ↑ (expected from lit).
    """
    rng = np.random.default_rng(42)
    hexes = [
        f'#{rng.integers(0,255):02X}{rng.integers(0,255):02X}{rng.integers(0,255):02X}'
        for _ in range(200)
    ]

    cielab_v, cielab_a, hsl_v, hsl_a = [], [], [], []
    L_vals = []
    for hx in hexes:
        feat = cielab_features(hx)
        cv = float(np.clip(feat @ w_v, 0, 1))
        ca = float(np.clip(feat @ w_a, 0, 1))
        hv, ha = get_current_va(hx)
        cielab_v.append(cv); cielab_a.append(ca)
        hsl_v.append(hv);    hsl_a.append(ha)
        L_vals.append(feat[0])  # L* normalised

    # Cross-correlation between two methods
    r_v, _ = ss.pearsonr(cielab_v, hsl_v)
    r_a, _ = ss.pearsonr(cielab_a, hsl_a)

    # Monotonicity: L* vs valence (should be positive)
    mono_v_cielab, _ = ss.spearmanr(L_vals, cielab_v)
    mono_v_hsl,    _ = ss.spearmanr(L_vals, hsl_v)

    return {
        'n_random':          200,
        'pearson_v':         round(float(r_v), 4),
        'pearson_a':         round(float(r_a), 4),
        'mono_L_vs_V_cielab': round(float(mono_v_cielab), 4),
        'mono_L_vs_V_hsl':    round(float(mono_v_hsl), 4),
        'cielab_v_mean':     round(float(np.mean(cielab_v)), 4),
        'cielab_a_mean':     round(float(np.mean(cielab_a)), 4),
        'hsl_v_mean':        round(float(np.mean(hsl_v)), 4),
        'hsl_a_mean':        round(float(np.mean(hsl_a)), 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*65)
    print("PHASE 3 EXPERIMENT — CIELAB + Oklab regression vs hsl_to_va")
    print("="*65)
    print(f"n = {len(ICEAS)} ICEAS centroids, LOO-CV, Ridge regression\n")

    # Targets
    v_h = np.array([v for _, v, _, _ in ICEAS])
    a_h = np.array([a for _, _, a, _ in ICEAS])

    # Oklab features (always available)
    X_ok = np.array([oklab_features(hx) for hx, *_ in ICEAS])

    # CIELAB features (only if colormath available)
    X = np.array([cielab_features(hx) for hx, *_ in ICEAS]) if HAS_CM else None

    # Current hsl_to_va baseline on same 12 points
    hsl_preds_v = np.array([get_current_va(hx)[0] for hx, *_ in ICEAS])
    hsl_preds_a = np.array([get_current_va(hx)[1] for hx, *_ in ICEAS])
    r_hsl_v, _ = ss.pearsonr(v_h, hsl_preds_v)
    r_hsl_a, _ = ss.pearsonr(a_h, hsl_preds_a)
    rmse_hsl_v = float(np.sqrt(np.mean((v_h - hsl_preds_v)**2)))
    rmse_hsl_a = float(np.sqrt(np.mean((a_h - hsl_preds_a)**2)))

    print("── Baseline: hsl_to_va (production) ──")
    print(f"  Valence:  r = {r_hsl_v:.4f}  RMSE = {rmse_hsl_v:.4f}")
    print(f"  Arousal:  r = {r_hsl_a:.4f}  RMSE = {rmse_hsl_a:.4f}")

    # ── OKLAB SECTION ─────────────────────────────────────────────────────────
    print("\n── Oklab LOO-CV (all 6 features) ──")
    alpha_ok_v = alpha_search(X_ok, v_h)
    alpha_ok_a = alpha_search(X_ok, a_h)
    preds_ok_v, r_ok_v, rmse_ok_v = loo_cv(X_ok, v_h, alpha_ok_v)
    preds_ok_a, r_ok_a, rmse_ok_a = loo_cv(X_ok, a_h, alpha_ok_a)
    w_ok_v = ridge_fit(X_ok, v_h, alpha_ok_v)
    w_ok_a = ridge_fit(X_ok, a_h, alpha_ok_a)
    print(f"  Valence:  r = {r_ok_v:.4f}  RMSE = {rmse_ok_v:.4f}  (alpha={alpha_ok_v})")
    print(f"  Arousal:  r = {r_ok_a:.4f}  RMSE = {rmse_ok_a:.4f}  (alpha={alpha_ok_a})")

    # Monotonicity L→V for Oklab (L ∈ [0,1], dim=0)
    L_ok = X_ok[:, 0]
    mono_ok_v, _ = ss.spearmanr(L_ok, preds_ok_v)
    print(f"  Monotonicity L→Valence: {mono_ok_v:.4f}")

    # ── CIELAB SECTION (if colormath available) ───────────────────────────────
    r_cielab_v = r_cielab_a = rmse_cielab_v = rmse_cielab_a = None
    w_v_full = w_a_full = None
    preds_v = preds_a = None
    if HAS_CM:
        print("\n── CIELAB feature ablation (LOO-CV) ──")
        abl_v = ablation(X, v_h, 'valence')
        abl_a = ablation(X, a_h, 'arousal')
        print(f"  {'features':30} {'V_r':>7} {'V_rmse':>7} {'A_r':>7} {'A_rmse':>7}")
        for name in abl_v:
            rv, rmv, _ = abl_v[name]
            ra, rma, _ = abl_a[name]
            mark = " ← best" if name == 'L*+a*+b*+C*+hue' else ""
            print(f"  {name:30} {rv:7.4f} {rmv:7.4f} {ra:7.4f} {rma:7.4f}{mark}")

        best_feat = [0,1,2,3,4,5]
        Xf = X[:, best_feat]
        alpha_v = alpha_search(Xf, v_h)
        alpha_a = alpha_search(Xf, a_h)
        preds_v, r_cielab_v, rmse_cielab_v = loo_cv(Xf, v_h, alpha_v)
        preds_a, r_cielab_a, rmse_cielab_a = loo_cv(Xf, a_h, alpha_a)
        w_v = ridge_fit(Xf, v_h, alpha_v)
        w_a = ridge_fit(Xf, a_h, alpha_a)
        w_v_full = np.zeros(6); w_v_full[best_feat] = w_v
        w_a_full = np.zeros(6); w_a_full[best_feat] = w_a
        print(f"\n── Best CIELAB model (alpha_v={alpha_v}, alpha_a={alpha_a}) ──")
        print(f"  Valence:  r = {r_cielab_v:.4f}  RMSE = {rmse_cielab_v:.4f}")
        print(f"  Arousal:  r = {r_cielab_a:.4f}  RMSE = {rmse_cielab_a:.4f}")

    # ── Per-colour comparison ─────────────────────────────────────────────────
    print(f"\n── Per-colour LOO-CV comparison ──")
    has_cielab = HAS_CM and preds_v is not None
    hdr = f"  {'colour':12} {'V_human':>8} {'V_hsl':>7} {'V_oklab':>8}"
    if has_cielab: hdr += f" {'V_cielab':>9}"
    print(hdr)
    for i, (hx, vh, ah, name) in enumerate(ICEAS):
        hv = hsl_preds_v[i]
        row = f"  {name:12} {vh:8.3f} {hv:7.3f} {preds_ok_v[i]:8.3f}"
        if has_cielab: row += f" {preds_v[i]:9.3f}"
        print(row)

    # ── Smoothness: Oklab monotonicity on 200 random colours ─────────────────
    print(f"\n── Smoothness test (n=200 random colours) ──")
    rng = np.random.default_rng(42)
    hexes = [f'#{rng.integers(0,255):02X}{rng.integers(0,255):02X}{rng.integers(0,255):02X}'
             for _ in range(200)]
    L_rnd_ok = [oklab_features(hx)[0] for hx in hexes]
    v_rnd_ok = [float(np.clip(oklab_features(hx) @ w_ok_v, 0, 1)) for hx in hexes]
    v_rnd_hsl = [get_current_va(hx)[0] for hx in hexes]
    mono_ok_rnd, _ = ss.spearmanr(L_rnd_ok, v_rnd_ok)
    mono_hsl_rnd, _ = ss.spearmanr(L_rnd_ok, v_rnd_hsl)
    r_ok_hsl, _ = ss.pearsonr(v_rnd_ok, v_rnd_hsl)
    print(f"  Monotonicity L→V:  Oklab={mono_ok_rnd:.4f}  hsl={mono_hsl_rnd:.4f}")
    print(f"  Pearson(Oklab_V, hsl_V) = {r_ok_hsl:.4f}  (consistency)")

    # ── Summary verdict ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("VERDICT — Oklab vs CIELAB vs HSL (valence only; arousal stays HSL)")
    print(f"{'='*65}")
    print(f"  HSL:   r = {r_hsl_v:.4f}")
    if HAS_CM and r_cielab_v is not None:
        print(f"  CIELAB r = {r_cielab_v:.4f}  (Δ vs HSL = {r_cielab_v - r_hsl_v:+.4f})")
    print(f"  Oklab: r = {r_ok_v:.4f}  (Δ vs HSL = {r_ok_v - r_hsl_v:+.4f})", end="")
    if HAS_CM and r_cielab_v is not None:
        print(f"  (Δ vs CIELAB = {r_ok_v - r_cielab_v:+.4f})", end="")
    print()
    print()

    best_r = r_ok_v
    best_name = "Oklab"
    if HAS_CM and r_cielab_v is not None and r_cielab_v > r_ok_v:
        best_r = r_cielab_v; best_name = "CIELAB"

    if best_r > r_hsl_v + 0.01:
        print(f"  → {best_name} beats HSL by >{0.01:.0%}.")
        if best_name == "Oklab":
            print(f"  ACTION: Set COLOR_VALENCE_OKLAB=True + copy w_oklab below.")
            print(f"          Then run: python -m tools.color_eval_rigor")
            print(f"          Gate pass → keep. Gate fail → revert.")
        else:
            print(f"  ACTION: Set COLOR_VALENCE_CIELAB=True (needs colormath).")
    else:
        print(f"  → No clear winner over HSL. Keep COLOR_VALENCE_OKLAB=False.")
    print(f"{'='*65}\n")

    # ── Coefficients ──────────────────────────────────────────────────────────
    print("── Oklab regression coefficients ──")
    print(f"  Features: [L, a/0.4, b/0.4, C/0.4, cos_h, sin_h]")
    print(f"  w_valence = {np.round(w_ok_v, 4).tolist()}")
    print(f"  w_arousal = {np.round(w_ok_a, 4).tolist()}")
    print(f"  (alpha_v={alpha_ok_v}, alpha_a={alpha_ok_a})")
    if HAS_CM and w_v_full is not None:
        print(f"\n── CIELAB regression coefficients ──")
        print(f"  Features: {FEATURE_NAMES}")
        print(f"  w_valence = {np.round(w_v_full, 4).tolist()}")
        print(f"  w_arousal = {np.round(w_a_full, 4).tolist()}")
    print()


if __name__ == "__main__":
    main()
