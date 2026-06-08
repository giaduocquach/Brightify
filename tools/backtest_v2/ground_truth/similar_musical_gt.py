"""LLM-as-judge ground truth for recommend_by_song — MUSICAL similarity (v1).

WHY a new GT (vs similar_llm_gt_v2): the product goal for "gợi ý theo bài" was
redefined to *most musically similar* (genre / tempo / energy / overall musical
feel), NOT lyric-topic similar. The existing similar_llm_gt_v2 judge prompt says
"Chỉ dựa vào lời và cảm giác âm nhạc" and feeds 800 chars of lyrics → it rewards
LYRICAL similarity, which is exactly why weight optimisation landed on lyrics=0.50.
To tune weights toward MUSICAL similarity we need a GT whose relevance reflects
musical character, with lyrics demoted to a minor cue ("chủ yếu nhạc, lời là phụ").

Literature: acoustic similarity > textual similarity for perceived music
similarity (Content-Based Music Similarity; arXiv 2604.23077). Musical character
is multidimensional (timbre/rhythm/harmony) and only partially text-describable —
which is *why* the audio embedding (MERT) should dominate the fusion.

JUDGE: qwen3:8b via Ollama (the project's existing primary judge). NOTE — the
original plan was Gemini-2.5-flash, but that key currently returns 429
(monthly spend cap). qwen3:8b is the established local judge in similar_llm_gt.py;
single-judge, de-circularized (no fused_emotion / engine V-A in the prompt).
Set BRIGHTIFY_MUSICAL_JUDGE=gemini to switch back once the cap resets.

MUSICAL descriptor shown to the judge uses only the RELIABLE fields (tempo_category,
energy_level, danceability, BPM, mode) — Essentia tag columns (instrument_tags,
mood_tags, acousticness, instrumentalness) are degenerate/NaN on this catalog and
are intentionally omitted. Lyrics snippet is short (180 chars) and labelled "phụ".

TREC-style pooling: pool = production top-N UNION N random negatives per seed.
Resumable: cache in similar_musical_gt_v1.json keyed by seed; value holds per-cand
scores. Relevance = score >= 2.

Usage: python -m tools.backtest_v2.ground_truth.similar_musical_gt [n_seeds] [pool_prod] [pool_rand]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional

import numpy as np

JUDGE_BACKEND = os.environ.get("BRIGHTIFY_MUSICAL_JUDGE", "qwen3").strip().lower()
MODEL_PRIMARY = "qwen3:8b"
OLLAMA        = "http://localhost:11434/api/generate"
GEMINI_MODEL  = "models/gemini-2.5-flash"

GT_DIR  = "var/runtime/backtest/ground_truth"
GT_FILE = os.path.join(GT_DIR, "similar_musical_gt_v1.json")

REL_THRESHOLD     = 2     # score >= 2 (of 0..3) => musically relevant
DEFAULT_N_SEEDS   = 20
DEFAULT_POOL_PROD = 12
DEFAULT_POOL_RAND = 8
SEED_RNG          = 42

# ── MUSICAL-similarity prompt: music is primary, lyrics are a minor cue ───────
PROMPT = """/no_think
Bạn là nhà phê bình âm nhạc Việt Nam. Chấm mức độ hai bài hát TƯƠNG TỰ VỀ CHẤT NHẠC:
thể loại, nhịp độ/tiết tấu, mức năng lượng, độ "nhảy", giọng trưởng/thứ, không khí âm nhạc tổng thể.
TRỌNG TÂM LÀ ÂM NHẠC. Lời chỉ là yếu tố PHỤ (gợi ý nhẹ về thể loại).
KHÔNG xét nghệ sĩ, độ nổi tiếng, hay nội dung/chủ đề của lời.
Trả JSON duy nhất: {{"score": <0..3>}}

0=khác hẳn về nhạc  1=hơi giống nhạc  2=giống nhạc  3=rất giống (nghe liền mạch cùng playlist)

=== BÀI GỐC ===
Tên: {seed_title}
Đặc trưng âm nhạc: {seed_feat}
Lời (trích ngắn, phụ):
{seed_lyrics}

=== BÀI SO SÁNH ===
Tên: {cand_title}
Đặc trưng âm nhạc: {cand_feat}
Lời (trích ngắn, phụ):
{cand_lyrics}"""


def _call_ollama(model: str, prompt: str, timeout: int = 90) -> Optional[int]:
    """Call Ollama model, parse JSON score 0-3. Returns None on failure."""
    import requests
    try:
        r = requests.post(OLLAMA, json={
            "model": model, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0.0, "num_predict": 64},
        }, timeout=timeout)
        text = r.json().get("response", "")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        out  = json.loads(text or "{}")
        s    = int(round(float(out.get("score", 0))))
        return max(0, min(3, s))
    except Exception:
        return None


# Free-tier gemini-2.5-flash is RPM-limited; pace calls + retry on 429 so the
# judge does not silently degrade to None (which would poison the GT with -1).
_GEMINI_MIN_INTERVAL = float(os.environ.get("GEMINI_MIN_INTERVAL", "4.2"))  # ~14 RPM
_GEMINI_STATE = {"client": None, "last": 0.0}


def _gemini_client():
    if _GEMINI_STATE["client"] is None:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.getcwd(), ".env"))
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None
        from google import genai
        _GEMINI_STATE["client"] = genai.Client(api_key=api_key)
    return _GEMINI_STATE["client"]


def _call_gemini(prompt: str, max_retries: int = 4) -> Optional[int]:
    """Gemini 2.5-flash judge. Throttled + retry on 429. Returns 0-3 or None."""
    client = _gemini_client()
    if client is None:
        return None
    from google.genai import types
    for attempt in range(max_retries):
        # Throttle to stay under the RPM cap.
        wait = _GEMINI_MIN_INTERVAL - (time.time() - _GEMINI_STATE["last"])
        if wait > 0:
            time.sleep(wait)
        _GEMINI_STATE["last"] = time.time()
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt + "\nTrả về JSON duy nhất.",
                config=types.GenerateContentConfig(
                    temperature=0.0, max_output_tokens=64,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)),
            )
            text = re.sub(r"```[a-z]*\n?", "", (resp.text or "")).strip("`").strip()
            m = re.search(r'"score"\s*:\s*([0-3])', text) or re.search(r'\b([0-3])\b', text)
            return int(m.group(1)) if m else None
        except Exception as e:
            msg = str(e)
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg) and attempt < max_retries - 1:
                time.sleep(8 * (attempt + 1))   # backoff: 8s, 16s, 24s
                continue
            return None
    return None


def _judge(seed_title, seed_feat, seed_lyrics, cand_title, cand_feat, cand_lyrics) -> Optional[int]:
    prompt = PROMPT.format(
        seed_title=seed_title or "", seed_feat=seed_feat or "(không rõ)",
        seed_lyrics=(seed_lyrics or "")[:180],
        cand_title=cand_title or "", cand_feat=cand_feat or "(không rõ)",
        cand_lyrics=(cand_lyrics or "")[:180],
    )
    if JUDGE_BACKEND == "gemini":
        return _call_gemini(prompt)
    return _call_ollama(MODEL_PRIMARY, prompt)


def _dance_cat(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if np.isnan(v):
        return ""
    return "thấp" if v < 0.34 else ("vừa" if v < 0.66 else "cao")


def _musical_feat(row) -> str:
    """Compact musical fingerprint from RELIABLE fields only (no degenerate tags)."""
    parts: List[str] = []
    tempo_cat = str(row.get("tempo_category", "") or "").strip()
    bpm = row.get("tempo")
    try:
        bpm_txt = f" (~{int(round(float(bpm)))} BPM)" if bpm is not None and not np.isnan(float(bpm)) else ""
    except (TypeError, ValueError):
        bpm_txt = ""
    if tempo_cat:
        parts.append(f"nhịp {tempo_cat}{bpm_txt}")
    energy = str(row.get("energy_level", "") or "").strip()
    if energy:
        parts.append(f"năng lượng {energy}")
    dc = _dance_cat(row.get("danceability"))
    if dc:
        parts.append(f"độ nhảy {dc}")
    mode = row.get("mode")
    try:
        if mode is not None and not np.isnan(float(mode)):
            parts.append("giọng Trưởng" if int(float(mode)) == 1 else "giọng Thứ")
    except (TypeError, ValueError):
        pass
    return ", ".join(parts) if parts else "(không rõ)"


def _song_info(row, lyr_col: str):
    title  = str(row.get("track_name", "") or "")
    feat   = _musical_feat(row)
    lyrics = str(row.get(lyr_col, "") or "")
    return title, feat, lyrics


def _stratified_seeds(df, n: int, rng: np.random.Generator) -> List[int]:
    """Sample n seed indices stratified by fused_emotion when available."""
    if "fused_emotion" not in df.columns:
        return rng.choice(len(df), size=min(n, len(df)), replace=False).tolist()
    groups = df.groupby("fused_emotion").indices
    per_group = max(1, n // len(groups))
    seeds: List[int] = []
    for idxs in groups.values():
        k = min(per_group, len(idxs))
        seeds.extend(int(i) for i in rng.choice(idxs, size=k, replace=False))
    chosen    = set(seeds)
    remaining = [i for i in range(len(df)) if i not in chosen]
    if len(seeds) < n and remaining:
        extra = min(n - len(seeds), len(remaining))
        seeds.extend(int(i) for i in rng.choice(remaining, size=extra, replace=False))
    return seeds[:n]


def build_similar_musical_gt(n_seeds: int  = DEFAULT_N_SEEDS,
                             pool_prod: int = DEFAULT_POOL_PROD,
                             pool_rand: int = DEFAULT_POOL_RAND,
                             verbose:  bool = True) -> dict:
    from tools.backtest_v2.catalog import Catalog

    cat = Catalog.load()
    df  = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    rng = np.random.default_rng(SEED_RNG)

    gt: dict = {}
    if os.path.exists(GT_FILE):
        gt = json.load(open(GT_FILE))
        if verbose:
            cached = sum(1 for v in gt.values()
                         for sc in v.get("judged", {}).values() if sc >= 0)
            print(f"[musical-gt] resuming — {cached} judgements cached  (backend={JUDGE_BACKEND})")

    seeds = _stratified_seeds(df, n_seeds, rng)
    t0 = time.time(); n_calls = 0

    for seed_idx in seeds:
        key_s = str(seed_idx)
        entry = gt.get(key_s, {"seed_idx": seed_idx, "judged": {}})
        judged = entry["judged"]

        seed_row = df.iloc[seed_idx]
        s_title, s_feat, s_lyrics = _song_info(seed_row, lyr_col)
        entry["seed_title"] = s_title

        prod = cat.recommend_by_song(seed_idx, top_k=pool_prod)
        rand = rng.choice(cat.n, size=min(pool_rand, cat.n), replace=False).tolist()
        pool = list(dict.fromkeys([int(i) for i in prod] + [int(i) for i in rand]))
        entry["pool_prod"] = [int(i) for i in prod]

        for cand_idx in pool:
            ckey = str(cand_idx)
            if ckey in judged:               # already judged (resume)
                continue
            if cand_idx == seed_idx:
                continue
            cand_row = df.iloc[cand_idx]
            c_title, c_feat, c_lyrics = _song_info(cand_row, lyr_col)
            if len(s_lyrics) < 30 or len(c_lyrics) < 30:
                judged[ckey] = -1            # unjudgeable (no lyrics)
                continue
            sc = _judge(s_title, s_feat, s_lyrics, c_title, c_feat, c_lyrics)
            judged[ckey] = -1 if sc is None else sc
            n_calls += 1
            if verbose and n_calls % 25 == 0:
                rate = (time.time() - t0) / max(n_calls, 1)
                print(f"  judged {n_calls} ({rate:.1f}s/call)")

        entry["relevant"] = sorted(int(k) for k, v in judged.items() if v >= REL_THRESHOLD)
        gt[key_s] = entry
        os.makedirs(GT_DIR, exist_ok=True)
        json.dump(gt, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
        if verbose:
            n_judged = sum(1 for v in judged.values() if v >= 0)
            print(f"[musical-gt] seed {seed_idx:4d} ({s_title[:26]:26s}): "
                  f"{len(entry['relevant'])} relevant / {n_judged} judged")

    print(f"[musical-gt] DONE — {n_calls} new calls → {GT_FILE}")
    return gt


def load_similar_musical_gt(path: str = GT_FILE) -> dict:
    return json.load(open(path))


def build_query_gt_mapping(gt: dict) -> Dict[int, List[int]]:
    """Convert gt dict → {seed_idx: [relevant_idx, ...]} (drop empty)."""
    return {int(k): v["relevant"] for k, v in gt.items() if v.get("relevant")}


if __name__ == "__main__":
    ns = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_SEEDS
    pp = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_POOL_PROD
    pr = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_POOL_RAND
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    build_similar_musical_gt(ns, pp, pr)
