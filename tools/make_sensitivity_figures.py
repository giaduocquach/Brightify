"""Render the 3 weight-sensitivity figures for the thesis from the measured
sensitivity_analysis.json (+ the tempo sweep, captured from tools.tune_muq_arousal).

Out: SOICT_DATN_Application_VIE_Template/Hinhve/fig_sens_{tempo,sigma,fusion}.png
Run: python -m tools.make_sensitivity_figures
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "SOICT_DATN_Application_VIE_Template", "Hinhve")
SENS = os.path.join(ROOT, "var/runtime/backtest/reports/sensitivity_analysis.json")

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "axes.grid": True, "grid.alpha": 0.3,
    "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
})

# Tempo sweep — measured by tools.tune_muq_arousal (no JSON; captured here).
TEMPO_W   = [0.15, 0.25, 0.35, 0.45, 0.55]
TEMPO_CV  = [0.771, 0.744, 0.692, 0.608, 0.496]
TEMPO_BPM = [0.161, 0.305, 0.466, 0.635, 0.791]
CV_GATE, BPM_TARGET, SERVING_T = 0.647, 0.20, 0.35


def _save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path); plt.close(fig)
    print("wrote", path)


def fig_tempo():
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    ax.plot(TEMPO_W, TEMPO_CV, "o-", color="#1f77b4", label="DEAM-CV ρ (độ chính xác arousal)")
    ax.plot(TEMPO_W, TEMPO_BPM, "s-", color="#d62728", label="ρ(Arousal, BPM) (bám nhịp độ)")
    ax.axhline(CV_GATE, ls="--", color="#1f77b4", alpha=0.6)
    ax.axhline(BPM_TARGET, ls="--", color="#d62728", alpha=0.6)
    ax.axvspan(0.25, 0.38, color="green", alpha=0.10)
    ax.axvline(SERVING_T, color="black", lw=1.2)
    ax.annotate("giá trị phục vụ 0.35", xy=(SERVING_T, 0.30), xytext=(0.40, 0.40),
                arrowprops=dict(arrowstyle="->"), fontsize=10)
    ax.text(0.252, CV_GATE + 0.01, "cổng DEAM-CV 0.647", color="#1f77b4", fontsize=9)
    ax.text(0.252, BPM_TARGET + 0.01, "mục tiêu BPM 0.20", color="#d62728", fontsize=9)
    ax.set_xlabel("Trọng số nhịp độ trong tổ hợp Arousal")
    ax.set_ylabel("Hệ số tương quan")
    ax.set_title("Độ nhạy: trọng số nhịp độ (Arousal)")
    ax.legend(fontsize=9, loc="center right")
    _save(fig, "fig_sens_tempo.png")


def fig_sigma(d):
    cs = d["color_sigma"]
    sv = cs["sweep_sigma_v_at_serving_a"]; sa = cs["sweep_sigma_a_at_serving_v"]
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    xv = [float(k) for k in sv]; yv = list(sv.values())
    xa = [float(k) for k in sa]; ya = list(sa.values())
    ax.plot(xv, yv, "o-", color="#1f77b4", label="quét σ_V (σ_A=0.14)")
    ax.plot(xa, ya, "s-", color="#ff7f0e", label="quét σ_A (σ_V=0.20)")
    ax.axvline(0.20, color="#1f77b4", ls=":", alpha=0.7)
    ax.axvline(0.14, color="#ff7f0e", ls=":", alpha=0.7)
    ax.set_ylim(0.018, 0.024)
    ax.set_xlabel("Băng thông σ của RBF")
    ax.set_ylabel("Targeting Error (thấp hơn = tốt hơn)")
    ax.set_title("Độ nhạy: σ của RBF màu (TE dao động < 0.003)")
    ax.legend(fontsize=9)
    _save(fig, "fig_sens_sigma.png")


def fig_fusion(d):
    sw = d["fusion_va"]["sweep"]
    x = [float(k) for k in sw]
    nd = [sw[k]["ndcg10_graded"] for k in sw]
    mc = [sw[k]["mood_coherence"] for k in sw]
    fig, ax1 = plt.subplots(figsize=(6.4, 4.0))
    l1, = ax1.plot(x, nd, "o-", color="#d62728", label="NDCG@10 (graded, xu hướng)")
    ax1.set_xlabel("Trọng số V-A trong fusion bài-tương-tự")
    ax1.set_ylabel("NDCG@10 (graded)", color="#d62728")
    ax1.tick_params(axis="y", labelcolor="#d62728")
    ax2 = ax1.twinx(); ax2.grid(False)
    l2, = ax2.plot(x, mc, "s-", color="#1f77b4", label="MoodCoherence")
    ax2.set_ylabel("MoodCoherence", color="#1f77b4")
    ax2.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.axvline(0.16, color="black", lw=1.2)
    ax1.annotate("phục vụ 0.16\n(điểm khuỷu)", xy=(0.16, nd[2]), xytext=(0.18, max(nd) * 0.98),
                 fontsize=9, arrowprops=dict(arrowstyle="->"))
    ax1.set_title("Độ nhạy: trọng số V-A — đánh đổi NDCG ↔ MoodCoherence")
    ax1.legend(handles=[l1, l2], fontsize=9, loc="center right")
    _save(fig, "fig_sens_fusion.png")


def main():
    d = json.load(open(SENS))
    os.makedirs(OUT, exist_ok=True)
    fig_tempo(); fig_sigma(d); fig_fusion(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
