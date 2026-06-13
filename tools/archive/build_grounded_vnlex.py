"""Workstream A — grounded Vietnamese lyrical valence from PUBLISHED lexicons (no self-made).

Replaces the hand-curated in-code VN emotion dict with per-word valence from the OFFICIAL
Vietnamese NRC-VAD lexicon (Mohammad 2018, ACL; v1 multilingual translation, 19,971 terms,
human-rated valence ∈[0,1]). Keeps only the METHOD (clause-scoped negation), not subjective
scores. Every word's valence now traces to NRC-VAD → fully citable.

Per song: tokenise lyrics → match unigrams + bigrams against NRC-VAD-VN → average matched
valences, flipping (1−v) for negated clauses → song valence ∈[0,1].

Output: data/vnlex_grounded_valence.json  + prints coverage + agreement vs hand-lexicon/GPT.
Run: python -m tools.build_grounded_vnlex
"""
from __future__ import annotations
import json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

NRC_VN = "data/external/lexicons/NRC-VAD-Lexicon/OneFilePerLanguage/Vietnamese-NRC-VAD-Lexicon.txt"
VNEMOLEX = "data/external/lexicons/VnEmoLex.xlsx"   # native VN published (Zenodo 801610)
OUT = "data/vnlex_grounded_valence.json"
NEGATORS = {"không", "chẳng", "chả", "đừng", "chưa", "đâu", "khỏi", "kohng", "ko", "k"}
MIN_WORDS = 2  # need ≥2 matched affective words to score a song


def _load_vnemolex():
    """Native VN polarity → valence proxy. Positive→0.75, Negative→0.25 (both/neither → skip)."""
    import pandas as pd
    df = pd.read_excel(VNEMOLEX)
    out = {}
    for r in df.itertuples(index=False):
        w = str(getattr(r, "Vietnamese", "")).strip().lower()
        pos, neg = int(getattr(r, "Positive", 0) or 0), int(getattr(r, "Negative", 0) or 0)
        if not w or pos == neg:        # neutral / ambiguous → no valence signal
            continue
        out[w] = 0.75 if pos else 0.25
    return out


def _load_nrc_vn():
    """Vietnamese word(lower) → valence[0,1]. Keep affective words (|v-0.5|>0.12) for signal."""
    uni, bi = {}, {}
    for ln in open(NRC_VN, encoding="utf-8").read().splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 5:
            continue
        try:
            v = float(p[1])
        except ValueError:
            continue
        w = p[4].strip().lower()
        if not w or abs(v - 0.5) < 0.12:   # drop near-neutral words (no valence signal)
            continue
        toks = w.split()
        if len(toks) == 1:
            uni[w] = v
        elif len(toks) == 2:
            bi[w] = v
    return uni, bi


def main() -> int:
    import pandas as pd
    uni, bi = _load_nrc_vn()
    print(f"[grounded] NRC-VAD-VN affective words: {len(uni)} unigram, {len(bi)} bigram")
    # ── cross-check + augment with native VnEmoLex (improves auto-translation quality) ──
    vnemo = _load_vnemolex()
    dropped = added = 0
    for w, vv in list(uni.items()):                 # drop NRC unigrams whose SIGN conflicts native
        ev = vnemo.get(w)
        if ev is not None and (vv - 0.5) * (ev - 0.5) < 0:   # opposite polarity → likely mistranslation
            del uni[w]; dropped += 1
    for w, ev in vnemo.items():                      # add native words NRC lacks
        if " " not in w and w not in uni:
            uni[w] = ev; added += 1
    print(f"[grounded] VnEmoLex cross-check: dropped {dropped} sign-conflict (mistranslation), "
          f"added {added} native words → {len(uni)} unigram total")
    df = pd.read_csv(cfg.PROCESSED_FILE)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "plain_lyrics"] if c in df.columns)
    tids = df["track_id"].astype(str).tolist()
    lyrics = df[lyc].fillna("").astype(str).tolist()

    out, n_matched = {}, []
    for tid, lyr in zip(tids, lyrics):
        toks = re.findall(r"[a-zàáâãèéêìíòóôõùúýăđĩũơưạ-ỹ]+", lyr.lower())
        if len(toks) < 3:
            continue
        vals = []
        i = 0
        while i < len(toks):
            t = toks[i]
            v = None; step = 1
            if i + 1 < len(toks) and f"{t} {toks[i+1]}" in bi:   # bigram first
                v = bi[f"{t} {toks[i+1]}"]; step = 2
            elif t in uni:
                v = uni[t]
            if v is not None:
                # clause-scoped negation: a negator within the previous 3 tokens flips polarity
                neg = any(toks[j] in NEGATORS for j in range(max(0, i - 3), i))
                vals.append((1.0 - v) if neg else v)
            i += step
        if len(vals) >= MIN_WORDS:
            out[tid] = round(float(np.mean(vals)), 4)
            n_matched.append(len(vals))
    json.dump(out, open(OUT, "w"), ensure_ascii=False)
    cov = len(out) / len(tids)
    print(f"[grounded] scored {len(out)}/{len(tids)} ({cov:.1%}), median matched words={np.median(n_matched):.0f} → {OUT}")

    # ── agreement vs hand-lexicon + GPT + served valence ──
    from scipy.stats import spearmanr
    def jv(p, f):
        if not os.path.exists(p): return {}
        d = json.load(open(p)); o = {}
        for t, x in d.items():
            val = (x.get(f) if (f and isinstance(x, dict)) else (x.get("valence") if isinstance(x, dict) else x))
            if val is not None: o[t] = float(val)
        return o
    refs = {"hand-lexicon (vn_lex)": jv("data/emotion_labels_v6c.json", "valence_vnlex"),
            "GPT (offline ref)": jv("data/va_reference_gpt.json", "valence"),
            "served v6g valence": jv(cfg.RELABELED_EMOTIONS_FILE, "valence")}
    print("\n=== grounded NRC-VAD-VN valence agreement (Spearman) ===")
    for nm, ref in refs.items():
        common = [t for t in out if t in ref]
        if len(common) < 20: print(f"  {nm:24} (n={len(common)})"); continue
        a = np.array([out[t] for t in common]); b = np.array([ref[t] for t in common])
        print(f"  {nm:24} ρ={spearmanr(a,b).correlation:+.3f}  n={len(common)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
