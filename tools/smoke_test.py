"""End-to-end API smoke test (2026-05-31).

Boots nothing itself — assumes a server is running at BASE_URL. Hits every major
endpoint with realistic inputs and asserts: HTTP 200 + basic output sanity (non-empty
results where expected). Catches backend regressions across the large change surface
(Phase 1/2 + unified search + AI-Lab merge + color V12 + E-RELABEL emotion labels).

Usage:  python -m tools.smoke_test [BASE_URL]
"""
from __future__ import annotations

import io
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
TIMEOUT = 60

PASS, FAIL = [], []


def _check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))


def get(path, expect_list_key=None, **params):
    try:
        r = requests.get(BASE + path, params=params, timeout=TIMEOUT)
        ok = r.status_code == 200
        detail = f"HTTP {r.status_code}"
        if ok and expect_list_key is not None:
            body = r.json()
            items = body.get(expect_list_key) if isinstance(body, dict) else body
            n = len(items) if items is not None else 0
            ok = n > 0
            detail = f"{n} items"
        _check(f"GET {path}", ok, detail)
        return r
    except Exception as e:
        _check(f"GET {path}", False, str(e)[:80])
        return None


def post(name, path, payload, expect_key="results"):
    try:
        r = requests.post(BASE + path, json=payload, timeout=TIMEOUT)
        ok = r.status_code == 200
        detail = f"HTTP {r.status_code}"
        if ok:
            body = r.json()
            items = body.get(expect_key) if isinstance(body, dict) else None
            n = len(items) if items is not None else 0
            ok = n > 0
            detail = f"{n} {expect_key}"
            if r.status_code == 200 and not ok:
                detail += f" | body keys={list(body)[:6]}"
        else:
            detail += f" | {r.text[:120]}"
        _check(f"POST {path} [{name}]", ok, detail)
        return r
    except Exception as e:
        _check(f"POST {path} [{name}]", False, str(e)[:80])
        return None


def main():
    print(f"=== SMOKE TEST against {BASE} ===\n")

    # ---- System / browse ----
    get("/api/health")
    get("/api/config")
    get("/api/moods")
    get("/api/statistics")
    songs = get("/api/songs", expect_list_key="songs", limit=5)
    get("/api/songs/featured", expect_list_key="songs")
    get("/api/songs/new-releases", expect_list_key="songs")
    get("/api/songs/random", expect_list_key="songs")
    get("/api/artists", expect_list_key="artists")
    get("/api/image/status")

    # discover a valid song id for similar/detail
    song_id = None
    if songs is not None and songs.status_code == 200:
        body = songs.json()
        arr = body.get("songs") or []
        if arr:
            song_id = arr[0].get("track_id") or arr[0].get("id") or arr[0].get("song_index")
    print(f"  (using song_id={song_id} for detail/similar)")
    if song_id is not None:
        get(f"/api/song/{song_id}/similar", expect_list_key="songs")

    # ---- Search (the F3 unified path: name / lyric / vibe) ----
    get("/api/songs/search", q="yêu")
    get("/api/songs/search/unified", q="Sơn Tùng")                 # by name
    get("/api/songs/search/unified", q="đêm mưa buồn nhớ em")      # by lyric/vibe
    get("/api/songs/search/unified", q="nhạc sôi động tiệc tùng")  # by vibe

    # ---- AI recommendations ----
    post("1 color", "/api/recommend/color", {"colors": ["#2c3e66"], "top_k": 5})
    post("3 colors", "/api/recommend/color",
         {"colors": ["#ef4444", "#2c3e66", "#86efac"], "top_k": 9})
    # verify bridge present
    r = requests.post(BASE + "/api/recommend/color",
                      json={"colors": ["#fde047"], "top_k": 3}, timeout=TIMEOUT)
    bridge = r.json().get("query", {}).get("bridge") if r.status_code == 200 else None
    _check("color bridge chip present", bool(bridge),
           f"{bridge[0] if bridge else None}")

    post("lyrics", "/api/recommend/lyrics", {"keywords": "cô đơn trong đêm", "top_k": 5})
    # V23: /emotion-journey endpoint removed (merged into colour 2-colour journey)

    # ---- Image (tiny generated PNG) ----
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (40, 60, 120)).save(buf, format="PNG")
        buf.seek(0)
        r = requests.post(BASE + "/api/recommend/image",
                          files={"file": ("t.png", buf, "image/png")}, timeout=TIMEOUT)
        ok = r.status_code == 200 and len(r.json().get("results", [])) > 0
        _check("POST /api/recommend/image", ok, f"HTTP {r.status_code}")
    except Exception as e:
        _check("POST /api/recommend/image", False, str(e)[:80])

    print(f"\n=== RESULT: {len(PASS)} pass, {len(FAIL)} fail ===")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
