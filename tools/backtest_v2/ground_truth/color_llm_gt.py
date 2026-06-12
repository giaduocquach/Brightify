"""L2b ground truth — LLM-as-judge relevance for recommend_by_colors (qwen3:8b, offline).

NON-CIRCULAR design: the judge is shown the colour's HUMAN target mood (derived from
the ICEAS survey in color_norms.py) plus the song's lyrics + audio cues — it never sees
the engine's hsl_to_va output, song_va, or song_emotion_vec. Its 0-3 relevance rating is
an independent second annotator. This separates L1 (is colour->mood right?) from L2 (given
the right mood, does retrieval return mood-appropriate songs?).

POOLING (TREC-style): we judge a pool = production top-N  UNION  N random negatives per
colour. The relevant set = songs rated >= REL_THRESHOLD. Unjudged songs are treated as
non-relevant, so Recall/NDCG are pool-limited — P@K is the honest headline. Including
random negatives keeps precision meaningful and lets a random baseline be scored too.

Caveat (logged in the report): production items are in the pool, so the pool slightly
favours production on recall. Mitigated by random negatives + reporting P@K.

Resumable: judgements cached in color_llm_gt_v1.json keyed by f"{hex}|{track_id}".

Usage: python -m tools.backtest_v2.ground_truth.color_llm_gt [pool_prod] [pool_rand]
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List

import numpy as np
import requests

MODEL = "qwen3:8b"
OLLAMA = "http://localhost:11434/api/generate"
OPENAI_MODEL = "gpt-4o-mini"
# Judge backend: qwen3 (default, Ollama) | gemini | openai. Set BRIGHTIFY_COLOR_JUDGE=openai.
JUDGE_BACKEND = os.environ.get("BRIGHTIFY_COLOR_JUDGE", "qwen3").strip().lower()
_OPENAI_MIN_INTERVAL = float(os.environ.get("OPENAI_MIN_INTERVAL", "0.2"))
_OPENAI_STATE = {"last": 0.0, "client": None}
GT_DIR = "var/runtime/backtest/ground_truth"
# GT filename overridable so a fresh judge writes its own file (no resume-skip).
GT_FILE = os.path.join(GT_DIR, os.environ.get("BRIGHTIFY_COLOR_GT_FILE", "color_llm_gt_v1.json"))

REL_THRESHOLD = 2          # rating >= 2 (of 0..3) => relevant
DEFAULT_POOL_PROD = 20     # top-N from production recommend_by_colors
DEFAULT_POOL_RAND = 20     # random negatives per colour
SEED = 42

# Plain-Vietnamese description of each engine emotion label (the L2 query intent).
MOOD_VI: Dict[str, str] = {
    "happy":       "vui tươi, hạnh phúc, tích cực, rộn ràng",
    "excited":     "phấn khích, sôi động, tràn đầy năng lượng, hứng khởi",
    "peaceful":    "yên bình, thanh thản, dịu dàng, an nhiên",
    "calm":        "bình tĩnh, nhẹ nhàng, thư thái, êm dịu",
    "melancholic": "u sầu, hoài niệm, man mác buồn, tiếc nuối nhẹ",
    "sad":         "buồn bã, đau khổ, mất mát, nước mắt",
    "tense":       "căng thẳng, bồn chồn, lo âu, bất an",
    "angry":       "giận dữ, phẫn nộ, mạnh mẽ dữ dội, bùng nổ",
}

PROMPT = """Bạn là giám khảo âm nhạc. Một người chọn nhạc theo TÂM TRẠNG: "{mood_vi}".
Hãy đánh giá bài hát dưới đây HỢP với tâm trạng đó tới mức nào, dựa trên lời + thể loại.
Chỉ trả JSON, không giải thích: {{"score": <0..3>}}
Thang điểm: 0=không hợp chút nào, 1=hơi liên quan, 2=hợp, 3=rất hợp.

Tên: {title}
Thể loại/cảm giác (audio): {tags}
Lời:
{lyrics}"""


def _judge(mood_vi: str, title: str, tags: str, lyrics: str) -> int | None:
    """Relevance judge dispatcher (0-3). Backend via BRIGHTIFY_COLOR_JUDGE env.
    Both the GT build loop and similar_discriminant_metrics import this, so the
    env choice routes all consumers consistently."""
    if JUDGE_BACKEND == "openai":
        return _judge_openai(mood_vi, title, tags, lyrics)
    if JUDGE_BACKEND == "gemini":
        return _judge_gemini(mood_vi, title, tags, lyrics)
    return _judge_qwen3(mood_vi, title, tags, lyrics)


def _judge_openai(mood_vi: str, title: str, tags: str, lyrics: str) -> int | None:
    """GPT-4o-mini judge (OpenAI). JSON mode, temp 0, 429-retry with backoff."""
    import re, time as _t
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("OpenAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    if _OPENAI_STATE["client"] is None:
        from openai import OpenAI
        _OPENAI_STATE["client"] = OpenAI(api_key=api_key)
    client = _OPENAI_STATE["client"]
    prompt = (PROMPT + "\nTrả về JSON duy nhất.").format(
        mood_vi=mood_vi, title=title or "",
        tags=tags or "(không rõ)", lyrics=(lyrics or "")[:1200])
    for attempt in range(3):
        wait = _OPENAI_MIN_INTERVAL - (_t.time() - _OPENAI_STATE["last"])
        if wait > 0:
            _t.sleep(wait)
        _OPENAI_STATE["last"] = _t.time()
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=20,
                response_format={"type": "json_object"},
            )
            text = (resp.choices[0].message.content or "").strip()
            m = re.search(r'"score"\s*:\s*([0-3])', text) or re.search(r'\b([0-3])\b', text)
            return int(m.group(1)) if m else None
        except Exception as e:
            if ("429" in str(e) or "rate" in str(e).lower()) and attempt < 2:
                _t.sleep(5 * (attempt + 1)); continue
            return None
    return None


def _judge_qwen3(mood_vi: str, title: str, tags: str, lyrics: str) -> int | None:
    """Qwen3 judge (Ollama, offline). Returns 0-3 relevance score.
    /no_think prefix disables Qwen3 reasoning chain (saves tokens, avoids timeout).
    num_predict=256 enough for {"score": N} JSON.
    """
    import re as _re
    prompt = "/no_think\n" + PROMPT.format(
        mood_vi=mood_vi, title=title or "",
        tags=tags or "(không rõ)", lyrics=(lyrics or "")[:1200])
    try:
        r = requests.post(OLLAMA, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0.0, "num_predict": 256},
        }, timeout=120)
        text = r.json().get("response", "")
        # Strip thinking blocks then parse JSON
        text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
        out  = json.loads(text or "{}")
        s    = int(round(float(out.get("score", 0))))
        return max(0, min(3, s))
    except Exception:
        return None


def _judge_gemini(mood_vi: str, title: str, tags: str, lyrics: str) -> int | None:
    """Gemini 2.5-flash judge (Verga 2024 PoLL: distinct family from Qwen3).
    Same prompt as Qwen3 judge; native Vietnamese; thinking disabled.
    Panickssery 2024 note: Gemini also labeled valence (v5b), but L3 task
    (lyrics mood relevance 0-3) differs from valence scoring — acceptable.
    """
    import os, re
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        prompt = (PROMPT + "\nTrả về JSON duy nhất.").format(
            mood_vi=mood_vi, title=title or "",
            tags=tags or "(không rõ)", lyrics=(lyrics or "")[:1200])
        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0, max_output_tokens=64,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = resp.text.strip()
        text = re.sub(r"```[a-z]*\n?", "", text).strip("`").strip()
        m = re.search(r'"score"\s*:\s*([0-3])', text)
        if m:
            return int(m.group(1))
        # fallback: find any digit 0-3
        m2 = re.search(r'\b([0-3])\b', text)
        return int(m2.group(1)) if m2 else None
    except Exception:
        return None


def build_color_llm_gt(pool_prod: int = DEFAULT_POOL_PROD,
                       pool_rand: int = DEFAULT_POOL_RAND,
                       verbose: bool = True) -> dict:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.color_norms import query_colors

    cat = Catalog.load()
    df = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    rng = np.random.default_rng(SEED)

    def _audio_cue(row) -> str:
        # tempo/energy descriptors (NOT the degenerate MTG mood_tags, NOT engine V-A)
        return f"nhịp {row.get('tempo_category', '?')}, năng lượng {row.get('energy_level', '?')}"

    gt = {}
    if os.path.exists(GT_FILE):
        gt = json.load(open(GT_FILE))
        if verbose:
            done = sum(len(v.get("judged", {})) for v in gt.values())
            print(f"[llm-gt] resuming — {done} cached judgements")

    t0 = time.time(); n_calls = 0
    for q in query_colors():
        hexv, mood = q["hex"], q["target_mood"]
        entry = gt.get(hexv, {"target_mood": mood, "term": q["term"], "judged": {}})
        entry["target_mood"] = mood; entry["term"] = q["term"]
        judged = entry["judged"]

        prod = cat.recommend_by_colors([hexv], top_k=pool_prod)
        rand = rng.choice(cat.n, size=min(pool_rand, cat.n), replace=False).tolist()
        pool = list(dict.fromkeys([int(i) for i in prod] + [int(i) for i in rand]))
        entry["pool_prod"] = [int(i) for i in prod]

        for idx in pool:
            key = str(idx)
            if key in judged:
                continue
            row = df.iloc[idx]
            title = str(row.get("track_name", ""))
            lyrics = str(row.get(lyr_col, "") or "")
            tags = _audio_cue(row)
            if len(lyrics) < 30:
                judged[key] = -1            # unjudgeable (no lyrics) — excluded from GT
                continue
            score = _judge(MOOD_VI.get(mood, mood), title, tags, lyrics)
            judged[key] = -1 if score is None else score
            n_calls += 1
            if verbose and n_calls % 25 == 0:
                rate = (time.time() - t0) / n_calls
                print(f"  judged {n_calls} ({rate:.1f}s/call) — {q['term']}")

        entry["relevant"] = sorted(int(k) for k, v in judged.items() if v >= REL_THRESHOLD)
        gt[hexv] = entry
        os.makedirs(GT_DIR, exist_ok=True)
        json.dump(gt, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
        if verbose:
            print(f"[llm-gt] {q['term']:9s} ({mood:11s}): "
                  f"{len(entry['relevant'])} relevant / {len(judged)} judged")

    print(f"[llm-gt] DONE — {n_calls} new judgements → {GT_FILE}")
    return gt


def load_color_llm_gt(path: str = GT_FILE) -> dict:
    return json.load(open(path))


if __name__ == "__main__":
    pp = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_POOL_PROD
    pr = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_POOL_RAND
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    build_color_llm_gt(pp, pr)
