#!/usr/bin/env python3
"""Generate the data-driven figures embedded in the ĐATN report (Chương 4/5).

Every chart is produced from REAL artifacts so the numbers match the report tables:
  - catalog V-A          ← data/emotion_labels_v6i.json   (5138 songs)
  - 12 colours on V-A    ← core.advanced_color_mapping.hsl_to_va (the shipped transform)
  - ablation bars        ← data/color_ablation.json       (V31→V38)
  - PMEmo transfer       ← data/pmemo_cross_eval.json
  - TE baselines / latency ← values produced by tools/color_eval_rigor.py and
                             tools/bench_latency.py (mirrored here, == report Tables 4.5/4.8)

Run:  .venv/bin/python tools/make_thesis_figures.py
Out:  SOICT_DATN_Application_VIE_Template/Hinhve/fig_*.png
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "SOICT_DATN_Application_VIE_Template", "Hinhve")

# ── consistent, clean publication style ────────────────────────────────────
plt.rcParams.update({
    "font.family": "DejaVu Sans",          # covers Vietnamese diacritics
    "font.size": 12,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "savefig.bbox": "tight",
})
ACCENT = "#0067A5"      # primary bar colour (matches ICEAS blue)
ACCENT2 = "#BE0032"     # highlight (Brightify / our system)
GREY = "#9aa0a6"


def _save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {name}")


def load_catalog_va():
    """Return (valence[N], arousal[N]) from the frozen serving labels."""
    with open(os.path.join(DATA, "emotion_labels_v6i.json"), encoding="utf-8") as f:
        labels = json.load(f)
    v = np.array([d["valence"] for d in labels.values()], dtype=float)
    a = np.array([d["arousal"] for d in labels.values()], dtype=float)
    return v, a


# 12 ICEAS basic colours (Jonauskaite 2020 / Berlin & Kay) — same list the eval uses.
ICEAS_COLS = [
    ("#BE0032", "Đỏ"),    ("#F38400", "Cam"),   ("#F3C300", "Vàng"),
    ("#FFB7C5", "Hồng"),  ("#008856", "Lục"),   ("#3AB09E", "Ngọc"),
    ("#0067A5", "Lam"),   ("#9C4F96", "Tím"),   ("#80461B", "Nâu"),
    ("#F2F3F4", "Trắng"), ("#848482", "Xám"),   ("#222222", "Đen"),
]


def fig_va_scatter(v, a):
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    # colour points by Russell quadrant (split at 0.5/0.5)
    q_colors = np.where(v >= 0.5,
                        np.where(a >= 0.5, "#e8a33d", "#5aa469"),   # Q1 vui-sôi / Q4 thư thái
                        np.where(a >= 0.5, "#c0504d", "#4f81bd"))   # Q2 căng/giận / Q3 buồn
    ax.scatter(v, a, c=q_colors, s=6, alpha=0.45, linewidths=0)
    ax.axvline(0.5, color="k", lw=0.8, alpha=0.5)
    ax.axhline(0.5, color="k", lw=0.8, alpha=0.5)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("Valence (tiêu cực → tích cực)")
    ax.set_ylabel("Arousal (trầm lắng → sôi động)")
    ax.set_title("Phân bố cảm xúc V-A của 5.138 bài hát")
    for (x, y, t) in [(0.78, 0.92, "Vui / Sôi nổi"), (0.22, 0.92, "Căng / Giận"),
                      (0.22, 0.06, "Buồn / U sầu"), (0.78, 0.06, "Thư thái / Bình yên")]:
        ax.text(x, y, t, ha="center", va="center", fontsize=10, style="italic",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))
    _save(fig, "fig_va_scatter.png")


def fig_va_hist(v, a):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.8))
    for ax, x, name, c in [(ax1, v, "Valence", ACCENT), (ax2, a, "Arousal", ACCENT2)]:
        ax.hist(x, bins=40, color=c, alpha=0.8, edgecolor="white", linewidth=0.3)
        ax.axvline(x.mean(), color="k", ls="--", lw=1.2,
                   label=f"TB={x.mean():.2f}, σ={x.std():.2f}")
        ax.set_xlim(0, 1); ax.set_xlabel(name); ax.legend(fontsize=10)
    ax1.set_ylabel("Số bài hát")
    fig.suptitle("Phân bố Valence và Arousal của kho nhạc", fontweight="bold")
    _save(fig, "fig_va_hist.png")


def fig_colors_va(v, a):
    from core.advanced_color_mapping import get_advanced_color_mapper
    mapper = get_advanced_color_mapper()
    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    ax.scatter(v, a, c=GREY, s=5, alpha=0.18, linewidths=0, label="Kho nhạc (5.138 bài)")
    for hx, name in ICEAS_COLS:
        cv, ca = mapper.hsl_to_va(hx)
        edge = "k" if hx.upper() in ("#F2F3F4", "#FFB7C5", "#F3C300") else "white"
        ax.scatter([cv], [ca], c=hx, s=320, edgecolors=edge, linewidths=1.4, zorder=3)
        ax.annotate(name, (cv, ca), fontsize=10, fontweight="bold",
                    xytext=(0, 12), textcoords="offset points", ha="center")
    ax.axvline(0.5, color="k", lw=0.8, alpha=0.4)
    ax.axhline(0.5, color="k", lw=0.8, alpha=0.4)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("Valence"); ax.set_ylabel("Arousal")
    ax.set_title("Ánh xạ 12 màu cơ bản lên mặt phẳng Valence-Arousal")
    ax.legend(loc="lower left", fontsize=9)
    _save(fig, "fig_colors_va.png")


def fig_te_baselines():
    # Values == report Table 4.5 (tools/color_eval_rigor.py output).
    names = ["Ngẫu\nnhiên", "Độ phổ\nbiến", "Chỉ\nValence", "Chỉ\nArousal",
             "Oracle\n(trần)", "Brightify"]
    te = [0.561, 0.513, 0.438, 0.292, 0.021, 0.0242]
    colors = [GREY, GREY, GREY, GREY, "#b0b0b0", ACCENT2]
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    bars = ax.bar(names, te, color=colors, edgecolor="white")
    ax.errorbar(5, 0.0242, yerr=[[0.0242 - 0.0219], [0.0263 - 0.0242]],
                fmt="none", ecolor="k", capsize=4, lw=1.2)
    for b, t in zip(bars, te):
        ax.text(b.get_x() + b.get_width() / 2, t + 0.008, f"{t:.3f}",
                ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Sai số nhắm đích (TE) — thấp hơn là tốt hơn")
    ax.set_title("TE của Brightify so với các đường cơ sở (12 màu, top-k=10)")
    ax.set_ylim(0, 0.62)
    _save(fig, "fig_te_baselines.png")


def fig_ablation():
    with open(os.path.join(DATA, "color_ablation.json"), encoding="utf-8") as f:
        ab = json.load(f)
    steps = list(ab.keys())
    labels = ["So khớp\nphân vị", "+ Đích\nCDF", "+ Nhất quán\nâm thanh", "+ Arousal\nWhiteford"]
    sep = [ab[s]["separation"] for s in steps]
    coh = [ab[s]["coherence"] for s in steps]
    te = [ab[s]["te"] for s in steps]
    x = np.arange(len(steps)); w = 0.26
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    ax.bar(x - w, sep, w, label="Độ tách biệt", color=ACCENT)
    ax.bar(x, coh, w, label="Độ nhất quán âm thanh", color="#5aa469")
    ax.bar(x + w, te, w, label="TE", color=ACCENT2)
    for i in range(len(steps)):
        ax.text(x[i] - w, sep[i] + 0.005, f"{sep[i]:.2f}", ha="center", fontsize=8)
        ax.text(x[i], coh[i] + 0.005, f"{coh[i]:.2f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Giá trị độ đo")
    ax.set_title("Đóng góp tích lũy của từng cải tiến (ablation)")
    ax.legend(fontsize=10)
    _save(fig, "fig_ablation.png")


def fig_pmemo():
    with open(os.path.join(DATA, "pmemo_cross_eval.json"), encoding="utf-8") as f:
        pm = json.load(f)
    cats = ["Valence", "Arousal"]
    rho = [pm["valence"]["transfer_rho"], pm["arousal"]["transfer_rho"]]
    cis = [pm["valence"]["transfer_ci"], pm["arousal"]["transfer_ci"]]
    err = [[rho[i] - cis[i][0] for i in range(2)], [cis[i][1] - rho[i] for i in range(2)]]
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    bars = ax.bar(cats, rho, color=[ACCENT, ACCENT2], width=0.55,
                  yerr=err, capsize=6, edgecolor="white")
    for b, r in zip(bars, rho):
        ax.text(b.get_x() + b.get_width() / 2, r + 0.02, f"ρ={r:.2f}",
                ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, 0.85)
    ax.set_ylabel("Tương quan Spearman ρ (chuyển miền)")
    ax.set_title("Chuyển miền đầu dò cảm xúc sang PMEmo\n(n=767, độc lập với dữ liệu huấn luyện)")
    _save(fig, "fig_pmemo.png")


def fig_latency():
    # Values == report Table table:latency (tools/bench_latency.py, Apple Silicon, 1000 iters).
    ops = ["Gợi ý 1 màu\n(UC02)", "Gợi ý bài\ntương tự (UC01)", "Hành trình\n2 màu"]
    median = [3.1, 4.0, 70.0]
    p95 = [4.4, 4.5, 73.6]
    x = np.arange(len(ops)); w = 0.36
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    b1 = ax.bar(x - w / 2, median, w, label="Trung vị", color=ACCENT)
    b2 = ax.bar(x + w / 2, p95, w, label="p95", color="#9ec3e0")
    ax.set_yscale("log")
    for bars, vals in [(b1, median), (b2, p95)]:
        for b, t in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, t * 1.05, f"{t:g}",
                    ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(ops, fontsize=10)
    ax.set_ylabel("Thời gian (ms, thang log)")
    ax.set_title("Thời gian phản hồi tính toán lõi")
    ax.legend(fontsize=10)
    _save(fig, "fig_latency.png")


def fig_ewe_weights():
    """EWE valence-signal reliability weights. Prefers a saved artifact; otherwise
    uses the shipped, documented reliability weights (config.py:562, v6g/v6h EWE)."""
    candidates = [
        os.path.join(DATA, "va_ewe_weights.json"),
        os.path.join(ROOT, "var", "runtime", "va_ewe_weights.json"),
    ]
    weights = None
    for p in candidates:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                obj = json.load(f)
            weights = obj.get("weights", obj)
            break
    if not weights:
        # Deployed EWE reliability weights (build_labels_repro: vn_lex .35 / vn_sent .22 /
        # emobank .34 / MuQ-valence .09) — 3 lyric signals dominate, audio is auxiliary.
        weights = {"vn_lex": 0.35, "vn_sent": 0.218, "emobank": 0.341, "muq": 0.091}
    order = ["vn_lex", "emobank", "vn_sent", "muq"]
    names = {"vn_lex": "Từ điển\nNRC-VAD", "emobank": "XLM-R\nEmoBank",
             "vn_sent": "ViSoBERT\nUIT-VSMEC", "muq": "MuQ\n(âm thanh)"}
    keys = [k for k in order if k in weights] or list(weights.keys())
    vals = [float(weights[k]) for k in keys]
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    bars = ax.bar([names.get(k, k) for k in keys], vals,
                  color=[ACCENT, ACCENT, ACCENT, "#9ec3e0"][:len(keys)], edgecolor="white", width=0.6)
    ax.tick_params(axis="x", labelsize=9.5)
    for b, t in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, t + 0.005, f"{t:.2f}", ha="center", fontsize=10)
    ax.set_ylabel("Trọng số EWE (∝ độ tin cậy)")
    ax.set_title("Trọng số tổ hợp Valence theo độ tin cậy (EWE)")
    _save(fig, "fig_ewe_weights.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"Generating thesis figures → {OUT}")
    v, a = load_catalog_va()
    print(f"  catalog: {len(v)} songs  | V mean={v.mean():.3f} sd={v.std():.3f}"
          f"  | A mean={a.mean():.3f} sd={a.std():.3f}")
    fig_va_scatter(v, a)
    fig_va_hist(v, a)
    fig_colors_va(v, a)
    fig_te_baselines()
    fig_ablation()
    fig_pmemo()
    fig_latency()
    fig_ewe_weights()
    print("Done.")


if __name__ == "__main__":
    main()
