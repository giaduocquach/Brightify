"""DB-backed retrieval tests — pg_trgm text search + pgvector ANN.

These pin the contract of the optional Postgres serving paths (db/search.py):

  • pg_trgm  : a name substring must find its song (GIN-trigram-accelerated ILIKE).
  • pgvector : MuQ HNSW ANN returns the seed's nearest neighbours, seed excluded.
  • equivalence: the pgvector *retrieve-then-rerank* path returns essentially the
    SAME songs as the full in-memory ranking. This is the property that justifies
    the design — pgvector is a scalability swap for candidate generation, NOT a
    different (weaker) ranker. If the fusion weights changed enough that MuQ no
    longer dominated, the top-300-MuQ candidate pool would stop containing the true
    top-k and this test would fail — which is exactly when the design assumption
    (MuQ-dominant similarity) would no longer hold.

The whole module skips when Postgres is unavailable or unseeded, so the file-only
deployment (no DB) still passes the suite.

Run:  pytest test/test_db_retrieval.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import text

from db.search import trgm_search_track_ids, pgvector_similar_candidates


@pytest.fixture(scope="module")
def db_session():
    """A live Session, or skip the module if Postgres is down / not seeded."""
    try:
        from db.engine import SessionLocal
        s = SessionLocal()
        s.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres unavailable: {e}")
    n = s.execute(text(
        "SELECT count(*) FROM song_embeddings WHERE muq_embedding IS NOT NULL")).scalar()
    if not n:
        s.close()
        pytest.skip("muq_embedding not populated — run `python -m db.seed`")
    yield s
    s.close()


@pytest.fixture(scope="module")
def rec():
    from core.recommendation_engine import get_recommender
    return get_recommender()


def test_trgm_search_finds_known_song(db_session):
    """A substring of a song's title must surface that song via pg_trgm."""
    # Pick a popular ASCII-ish title so the substring has no accent/wildcard edge.
    row = db_session.execute(text(
        "SELECT track_id, track_name FROM songs "
        "WHERE track_name ~ '^[A-Za-z0-9][A-Za-z0-9 ]{6,}$' "
        "ORDER BY popularity DESC NULLS LAST LIMIT 1")).fetchone()
    assert row is not None, "no ASCII title to probe with"
    track_id, name = row[0], row[1]
    needle = name[1:7]                      # interior substring → must ILIKE-match
    ids = trgm_search_track_ids(db_session, needle, limit=500)
    assert track_id in ids, f"{needle!r} did not surface {name!r}"


def test_trgm_search_empty_query_returns_nothing(db_session):
    assert trgm_search_track_ids(db_session, "   ", limit=10) == []


def test_pgvector_candidates_exclude_seed_and_dedup(db_session):
    """ANN returns exactly n distinct neighbours and never the seed itself."""
    seed = db_session.execute(text(
        "SELECT track_id FROM song_embeddings WHERE muq_embedding IS NOT NULL "
        "LIMIT 1")).scalar()
    cands = pgvector_similar_candidates(db_session, seed, n=50)
    assert len(cands) == 50
    assert seed not in cands
    assert len(set(cands)) == 50, "candidate list has duplicates"


def test_pgvector_candidates_missing_seed_is_empty(db_session):
    """A seed with no MuQ vector yields no candidates (not an error)."""
    assert pgvector_similar_candidates(db_session, "___no_such_track___", n=10) == []


@pytest.mark.slow
@pytest.mark.parametrize("idx", [0, 1000, 5000])
def test_pgvector_rerank_matches_memory(rec, db_session, idx):
    """pgvector retrieve-then-rerank ≈ full in-memory ranking (same top-1, ≥8/10).

    Both paths apply the identical fusion + diversity; the pgvector path only
    restricts the candidate pool to the 300 MuQ-nearest. Because MuQ carries 0.76
    of the fusion weight, the true top-k lives inside that pool, so the two rankings
    coincide up to a rare boundary swap.
    """
    seed_tid = str(rec.df.iloc[idx]['track_id'])

    mem = rec.recommend_by_song(idx, top_k=10)
    cands = pgvector_similar_candidates(db_session, seed_tid, n=300)
    restrict = rec._resolve_indices(cands)
    pg = rec.recommend_by_song(idx, top_k=10, restrict_to=restrict)

    def ids_of(d):
        return [rec.df.loc[int(i), 'track_id'] for i in d['original_index']]

    mem_ids, pg_ids = ids_of(mem), ids_of(pg)
    assert mem_ids[0] == pg_ids[0], "top-1 similar song diverged between backends"
    overlap = len(set(mem_ids) & set(pg_ids))
    assert overlap >= 8, f"only {overlap}/10 overlap — candidate pool too narrow"
