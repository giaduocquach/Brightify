"""E-RELABEL v3 trial — zero-shot song emotion via local LLM (Ollama + qwen3:8b).

Compares LLM valence/emotion against v2 (lexicon+audio) and CLAP on a sample,
using the SAME non-circular independent metric as relabel_emotions.py:
title-keyword accuracy (sad-titled → negative label, happy-titled → positive).
No paid API — uses the local Ollama server. One-time offline labelling.

Sampling is biased toward title-keyword songs so the decisive independent metric
has strong signal (these titles are NOT shown to the model differently — it only
reads lyrics, never the keyword logic).

Usage:  python -m tools.relabel_llm [N_per_class]
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.relabel_emotions import SAD_KW, HAPPY_KW

MODEL = "qwen3:8b"
OLLAMA = "http://localhost:11434/api/generate"
NEG = {"sad", "melancholic", "tense", "angry"}
POS = {"happy", "excited", "peaceful", "calm"}
OUT_FILE = "data/emotion_labels_v3_llm_sample.json"
FULL_FILE = "data/emotion_labels_v3.json"
VALID_EMO = {"happy", "excited", "peaceful", "calm",
             "melancholic", "sad", "tense", "angry"}

PROMPT = """Đọc lời bài hát tiếng Việt và đánh giá cảm xúc TỔNG THỂ. Chỉ trả JSON, không giải thích:
{{"valence": <0..1, 0=rất buồn/tiêu cực, 1=rất vui/tích cực>, "arousal": <0..1, 0=rất tĩnh/êm dịu/chậm rãi, 1=rất mạnh mẽ/dữ dội/sôi động>}}

QUAN TRỌNG: valence và arousal ĐỘC LẬP — đừng để cái này quyết định cái kia.
- Bài BUỒN có thể TĨNH (arousal thấp: ballad piano nhẹ) HOẶC DỮ DỘI (arousal cao: rock/rap phẫn nộ, gào thét).
- Bài VUI có thể NHẸ NHÀNG (arousal thấp: acoustic thư giãn) HOẶC SÔI ĐỘNG (arousal cao: dance/EDM tiệc tùng).
- arousal = MỨC NĂNG LƯỢNG/CƯỜNG ĐỘ cảm xúc, KHÔNG phải vui hay buồn.

Tên: {title}
Lời:
{lyrics}"""


def llm_label(title: str, lyrics: str) -> dict | None:
    prompt = PROMPT.format(title=title or "", lyrics=(lyrics or "")[:1500])
    try:
        r = requests.post(OLLAMA, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "format": "json", "think": False, "options": {"temperature": 0.1},
        }, timeout=120)
        out = json.loads(r.json().get("response", "{}"))
        v = float(out.get("valence", 0.5))
        a = float(out.get("arousal", 0.5))
        return {"valence": max(0.0, min(1.0, v)), "arousal": max(0.0, min(1.0, a))}
    except Exception:
        return None


def title_acc(df, label_col):
    titles = df["track_name"].fillna("")
    sad = df[titles.str.contains(SAD_KW, case=False, regex=True)]
    hap = df[titles.str.contains(HAPPY_KW, case=False, regex=True)
             & ~titles.str.contains(SAD_KW, case=False, regex=True)]
    sa = sad[label_col].isin(NEG).mean() if len(sad) else float("nan")
    ha = hap[label_col].isin(POS).mean() if len(hap) else float("nan")
    bal = np.nanmean([sa, ha])
    return sa, ha, bal, len(sad), len(hap)


def run_full():
    """Label the WHOLE catalog with LLM valence + emotion → production v3 file.

    v3 entry = {valence: LLM, arousal: v2 audio-arousal, label: quadrant(LLM-val,
    audio-arousal)}. Songs without usable lyrics fall back to the v2 entry.
    Resumable: re-reads FULL_FILE and skips track_ids already labelled.
    """
    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()

    df = pd.read_csv(cfg.PROCESSED_FILE)
    if "track_id" not in df.columns:
        df["track_id"] = range(len(df))
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    v2 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))

    out = {}
    if os.path.exists(FULL_FILE):
        out = json.load(open(FULL_FILE))
        done = sum(1 for v in out.values() if v.get("src") == "llm2")
        print(f"[v3-full] found {len(out)} entries, {done} already done with 2-dim LLM")

    # Re-do any entry not yet labelled by the 2-dim LLM method (src != 'llm2')
    todo = [r for r in df.itertuples()
            if out.get(str(r.track_id), {}).get("src") != "llm2"]
    print(f"[v3-full] {len(todo)} songs to label 2-dim (of {len(df)})")
    t0 = time.time()
    for i, row in enumerate(todo, 1):
        tid = str(row.track_id)
        lyr = getattr(row, lyr_col, "") or ""
        v2e = v2.get(tid, {})
        if len(str(lyr)) > 30:
            res = llm_label(row.track_name, lyr)
            if res:
                lv, la = res["valence"], res["arousal"]
                out[tid] = {"valence": round(lv, 4), "arousal": round(la, 4),
                            "label": fusion.get_emotion_label(lv, la), "src": "llm2"}
            else:
                out[tid] = {**v2e, "src": "v2_fallback"}  # LLM failed → keep v2
        else:
            out[tid] = {**v2e, "src": "v2_no_lyrics"}     # no lyrics → keep v2
        if i % 50 == 0:
            json.dump(out, open(FULL_FILE, "w"), ensure_ascii=False)
            eta = (time.time() - t0) / i * (len(todo) - i) / 60
            print(f"  {i}/{len(todo)}  ({(time.time()-t0)/i:.1f}s/song, ETA {eta:.0f} min)")
    json.dump(out, open(FULL_FILE, "w"), ensure_ascii=False)
    print(f"[v3-full] DONE — {len(out)} labels → {FULL_FILE}")
    dist = pd.Series([v.get("label") for v in out.values()]).value_counts()
    print("\n=== v3 distribution ===\n" + dist.to_string())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        return run_full()
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    df = pd.read_csv(cfg.PROCESSED_FILE)
    if "track_id" not in df.columns:
        df["track_id"] = range(len(df))
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    df = df[df[lyr_col].fillna("").str.len() > 30].copy()

    titles = df["track_name"].fillna("")
    sad = df[titles.str.contains(SAD_KW, case=False, regex=True)].head(n_per)
    hap = df[titles.str.contains(HAPPY_KW, case=False, regex=True)
             & ~titles.str.contains(SAD_KW, case=False, regex=True)].head(n_per)
    sample = pd.concat([sad, hap]).drop_duplicates("track_id")
    print(f"[v3] sample = {len(sample)} songs ({len(sad)} sad-titled + {len(hap)} happy-titled)")

    # reference labels
    clap = json.load(open(cfg.CLAP_EMOTIONS_FILE))
    v2 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))

    llm = {}
    t0 = time.time()
    for i, row in enumerate(sample.itertuples(), 1):
        res = llm_label(row.track_name, getattr(row, lyr_col))
        if res:
            llm[str(row.track_id)] = res
        if i % 20 == 0:
            print(f"  {i}/{len(sample)}  ({(time.time()-t0)/i:.1f}s/song)")
    json.dump(llm, open(OUT_FILE, "w"), ensure_ascii=False)
    print(f"[v3] labelled {len(llm)}/{len(sample)} → {OUT_FILE}")

    # build comparison frame on the sample
    s = sample.copy()
    s["clap_label"] = s["track_id"].astype(str).map(clap)
    s["v2_label"] = s["track_id"].astype(str).map(lambda t: v2.get(t, {}).get("label"))
    s["llm_label"] = s["track_id"].astype(str).map(lambda t: llm.get(t, {}).get("emotion"))
    # v3 = LLM valence + v2 audio arousal → quadrant label (isolates valence source)
    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()
    def _v3(t):
        if t not in llm: return None
        lv = llm[t]["valence"]; av = v2.get(t, {}).get("arousal", 0.5)
        return fusion.get_emotion_label(lv, av)
    s["v3_label"] = s["track_id"].astype(str).map(_v3)
    s = s[s["llm_label"].notna()]

    print("\n=== TITLE-KEYWORD ACCURACY [independent] on the SAME sample ===")
    print("                       sad→neg   happy→pos   balanced")
    for name, col in [("CLAP", "clap_label"), ("v2 (lexicon+audio)", "v2_label"),
                      ("LLM emotion direct", "llm_label"), ("v3 (LLM-val+audio)", "v3_label")]:
        sa, ha, bal, ns, nh = title_acc(s, col)
        print(f"  {name:22} {sa*100:5.1f}%   {ha*100:6.1f}%   {bal*100:6.1f}%")
    print(f"\n  (sample: {len(s)} songs with valid LLM labels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
