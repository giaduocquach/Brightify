"""Smoke tests for unified search — no DB required.

Run:  python -m pytest test/test_search_unified.py -v
  or: python test/test_search_unified.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import types
import unicodedata
import pytest
import pandas as pd
from unittest.mock import MagicMock


# ── import the helper under test ────────────────────────────────────────────
from api.music import _strip_accents


# ══ Unit: _strip_accents ════════════════════════════════════════════════════

class TestStripAccents:
    def test_common_vietnamese(self):
        assert _strip_accents("yêu") == "yeu"
        assert _strip_accents("buồn") == "buon"
        assert _strip_accents("tình") == "tinh"
        assert _strip_accents("nhớ") == "nho"

    def test_already_plain(self):
        assert _strip_accents("love") == "love"

    def test_empty(self):
        assert _strip_accents("") == ""

    def test_mixed(self):
        assert _strip_accents("Sơn Tùng MTP") == "Son Tung MTP"

    def test_roundtrip_lower(self):
        # strip then lower should match query-side processing
        assert _strip_accents("Nơi Này Có Anh").lower() == "noi nay co anh"


# ══ Integration: search endpoint with a minimal mock recommender ════════════

def _make_mock_recommender():
    """Minimal recommender stub with a tiny in-memory DataFrame."""
    df = pd.DataFrame([
        {"track_id": "t1", "track_name": "Yêu Một Người", "primary_artist": "Sơn Tùng", "album_name": "", "plain_lyrics": ""},
        {"track_id": "t2", "track_name": "Buồn Làm Chi", "primary_artist": "Mỹ Tâm", "album_name": "", "plain_lyrics": ""},
        {"track_id": "t3", "track_name": "Happy Song",   "primary_artist": "Various",  "album_name": "", "plain_lyrics": ""},
        {"track_id": "t4", "track_name": "Tình Yêu Mùa Đông", "primary_artist": "Hà Anh Tuấn", "album_name": "", "plain_lyrics": "mùa đông lạnh giá"},
    ])
    rec = MagicMock()
    rec.df = df
    rec.recommend_by_lyrics_keywords.return_value = df.head(0)  # empty related
    return rec


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import api.music as music_module

    rec = _make_mock_recommender()
    monkeypatch.setattr(music_module, "_recommender", rec)
    monkeypatch.setattr(music_module, "_albumart_cache", {})
    monkeypatch.setattr(music_module, "_artistimg_cache", {})

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(music_module.router)
    return TestClient(app)


class TestSearchUnified:
    def test_exact_match_with_diacritics(self, client):
        r = client.get("/api/songs/search/unified?q=Y%C3%AAu")  # "Yêu"
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        ids = [s["track_id"] for s in data["matches"]]
        assert "t1" in ids, "Should match 'Yêu Một Người'"

    def test_diacritic_insensitive_query(self, client):
        r = client.get("/api/songs/search/unified?q=yeu")
        assert r.status_code == 200
        data = r.json()
        ids = [s["track_id"] for s in data["matches"]]
        assert "t1" in ids, "'yeu' should match 'Yêu Một Người'"

    def test_diacritic_insensitive_buon(self, client):
        r = client.get("/api/songs/search/unified?q=buon")
        assert r.status_code == 200
        ids = [s["track_id"] for s in r.json()["matches"]]
        assert "t2" in ids, "'buon' should match 'Buồn Làm Chi'"

    def test_no_results_returns_empty(self, client):
        r = client.get("/api/songs/search/unified?q=xyznotexist")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["matches"] == []

    def test_response_structure(self, client):
        r = client.get("/api/songs/search/unified?q=happy")
        assert r.status_code == 200
        data = r.json()
        assert "success" in data
        assert "matches" in data
        assert "related" in data
        assert "query" in data

    def test_empty_query_rejected(self, client):
        r = client.get("/api/songs/search/unified?q=")
        # FastAPI min_length=1 → 422
        assert r.status_code == 422


# ── standalone runner ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick unit-only check without pytest
    t = TestStripAccents()
    t.test_common_vietnamese()
    t.test_already_plain()
    t.test_empty()
    t.test_mixed()
    t.test_roundtrip_lower()
    print("All _strip_accents unit tests passed.")
