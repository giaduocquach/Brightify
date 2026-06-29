"""DB-backed retrieval helpers — pg_trgm fuzzy text search + pgvector ANN.

These back the *optional* DB serving paths. The in-memory hot path (numpy matmul
over precomputed features) remains the default; callers fall back to it when the
database is unavailable, so the app still runs file-only with no Postgres.

- ``trgm_search_track_ids``  : library text search via pg_trgm (GIN trigram index
  on ``songs.track_name``); case-insensitive substring + typo-tolerant similarity.
- ``pgvector_similar_candidates`` : similar-song candidate retrieval via pgvector
  HNSW ANN on ``song_embeddings.muq_embedding`` (the dominant audio signal, 0.76).
"""
from __future__ import annotations

from sqlalchemy import text


def trgm_search_track_ids(session, query: str, limit: int = 200) -> list[str]:
    """Return track_ids matching ``query`` by name/artist, best first.

    Uses pg_trgm: ``ILIKE`` (substring, GIN-trigram-accelerated) unioned with the
    ``%`` similarity operator (typo tolerance), ranked by trigram similarity then
    popularity. Accent-sensitive + case-insensitive — same membership as the
    in-memory ``/songs`` substring filter, plus fuzzy matches.
    """
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = session.execute(
        text(
            """
            SELECT track_id
            FROM songs
            WHERE track_name ILIKE :like
               OR primary_artist_name ILIKE :like
               OR track_name % :q
               OR primary_artist_name % :q
            ORDER BY GREATEST(
                         similarity(track_name, :q),
                         similarity(COALESCE(primary_artist_name, ''), :q)
                     ) DESC,
                     popularity DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"like": like, "q": q, "limit": int(limit)},
    ).fetchall()
    return [r[0] for r in rows]


def pgvector_similar_candidates(session, seed_track_id: str, n: int = 300) -> list[str]:
    """Return the ``n`` nearest track_ids to ``seed_track_id`` by MuQ cosine.

    HNSW ANN over ``song_embeddings.muq_embedding`` (``vector_cosine_ops``). This is
    the candidate-generation stage of a retrieve-then-rerank pipeline: the caller
    re-scores these with the full fusion (MuQ + V-A + lyrics). Excludes the seed;
    returns ``[]`` if the seed has no MuQ vector.
    """
    # Fetch the seed vector first (as pgvector's text form), then rank against it.
    # A correlated subquery in ORDER BY would degrade to NULL distances for a missing
    # seed (returning arbitrary rows) — fetching explicitly lets us return [] instead.
    vec = session.execute(
        text("SELECT muq_embedding::text FROM song_embeddings WHERE track_id = :seed"),
        {"seed": seed_track_id},
    ).scalar()
    if vec is None:
        return []
    # HNSW returns at most hnsw.ef_search rows (default 40), and the seed itself is
    # the nearest hit — the `!= :seed` post-filter then drops it, leaving ef-1. Use
    # 2·n so a LIMIT n still yields n candidates (and recall improves). is_local=true
    # scopes the setting to this transaction.
    session.execute(text("SELECT set_config('hnsw.ef_search', :ef, true)"),
                    {"ef": str(max(int(n) * 2, 40))})
    rows = session.execute(
        text(
            """
            SELECT track_id
            FROM song_embeddings
            WHERE track_id != :seed
              AND muq_embedding IS NOT NULL
            ORDER BY muq_embedding <=> CAST(:vec AS vector)
            LIMIT :n
            """
        ),
        {"seed": seed_track_id, "vec": vec, "n": int(n)},
    ).fetchall()
    return [r[0] for r in rows]
