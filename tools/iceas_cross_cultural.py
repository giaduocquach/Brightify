"""#2 — Bound the VN-extrapolation risk with DATA: how stable is the colour→valence mapping
across the 30 ICEAS countries? If colour-emotion structure is consistent across cultures (esp.
Asian ones), extrapolating the ICEAS-fit to Vietnam (not in ICEAS-30) is empirically defensible.

Per (country, colour): valence = mean over emotion terms of NRC-VAD(emotion-valence) weighted by
how often that emotion was endorsed for that colour. Then correlate each country's colour→valence
vector against the global average → cross-cultural stability. Report Asian countries separately.

Run: python -m tools.iceas_cross_cultural
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAW = "data/external/color_norms/jonauskaite_ICEAS_raw.csv"
NRC = "data/external/lexicons/NRC-VAD-Lexicon/OneFilePerLanguage/Vietnamese-NRC-VAD-Lexicon.txt"
ASIAN = {"china","vietnam","thailand","indonesia","malaysia","philippines","singapore","japan",
         "korea","south korea","taiwan","hong kong","india","cambodia","laos","myanmar"}
MIN_PARTICIPANTS = 30   # per country to be reliable


def _nrc_valence() -> dict:
    out = {}
    for ln in open(NRC, encoding="utf-8").read().splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 2:
            try: out[p[0].strip().lower()] = float(p[1])
            except ValueError: pass
    return out


def main() -> int:
    from scipy.stats import spearmanr
    df = pd.read_csv(RAW)
    nrc = _nrc_valence()
    # emotion columns = those whose name matches an NRC-VAD English word
    meta = {"user","lang","lang_full","start","end","troubleseeing","colorimportance","mothertongue",
            "fluentenglish","residencecountry","origincountry","origincountry_full","gender",
            "birthyear","age","total_time","time_first4","colour"}
    emo_cols = [c for c in df.columns if c not in meta and c.lower() in nrc]
    print(f"[iceas] {len(emo_cols)} emotion terms mapped to NRC-VAD valence (of {len(df.columns)-len(meta)} candidates)")
    ev = np.array([nrc[c.lower()] for c in emo_cols])

    country_col = "origincountry_full" if "origincountry_full" in df.columns else "origincountry"
    df[country_col] = df[country_col].astype(str).str.strip().str.lower()
    colours = sorted(df["colour"].dropna().astype(str).unique())

    # per (country, colour): valence = weighted mean of emotion valences (weights = endorsement)
    def country_vec(sub):
        out = {}
        for col, g in sub.groupby("colour"):
            w = g[emo_cols].fillna(0).values.astype(float)   # participants × emotions
            freq = w.mean(0)                                  # endorsement freq per emotion
            if freq.sum() > 1e-9:
                out[str(col)] = float((freq * ev).sum() / freq.sum())
        return out

    global_vec = country_vec(df)
    gv = np.array([global_vec.get(c, np.nan) for c in colours])

    counts = df[country_col].value_counts()
    rows = []
    for ctry, n in counts.items():
        if n < MIN_PARTICIPANTS or ctry in ("nan",""):
            continue
        cv_d = country_vec(df[df[country_col] == ctry])
        cv = np.array([cv_d.get(c, np.nan) for c in colours])
        m = ~np.isnan(cv) & ~np.isnan(gv)
        if m.sum() < 4:
            continue
        rho = spearmanr(cv[m], gv[m]).correlation
        rows.append((ctry, int(n), rho, ctry in ASIAN))

    rows.sort(key=lambda r: -r[2])
    rhos = [r[2] for r in rows]
    print(f"\n[iceas] colour→valence stability vs GLOBAL avg, across {len(rows)} countries (≥{MIN_PARTICIPANTS} ppl):")
    print(f"  median ρ = {np.median(rhos):.3f}   min = {np.min(rhos):.3f}   max = {np.max(rhos):.3f}")
    asian = [r for r in rows if r[3]]
    if asian:
        print(f"  ASIAN countries (cultural proxy for VN):")
        for ctry, n, rho, _ in asian:
            print(f"    {ctry:18} n={n:5}  ρ_vs_global={rho:+.3f}")
        print(f"  → Asian median ρ = {np.median([r[2] for r in asian]):.3f}")
    print(f"\n  Bottom 5 (least aligned):")
    for ctry, n, rho, isa in rows[-5:]:
        print(f"    {ctry:18} n={n:5}  ρ={rho:+.3f}{'  [Asian]' if isa else ''}")
    print(f"\n  Interpretation: high cross-cultural ρ (esp. Asian) ⇒ colour→valence is culturally"
          f" stable ⇒ extrapolating the ICEAS-fit to Vietnam (not in ICEAS-30) is data-supported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
