"""Regression tests for endless-radio exclusion (exclude_ids).

The recommend-by-colour, mood-journey, and similar-song paths all accept
`exclude_ids` so the frontend can keep the queue fresh (no hard loop → avoids the
inverted-U repeat-exposure satiation curve). These tests pin the contract that an
excluded track NEVER reappears in the next batch, while the batch stays full.

Slow: require the catalog + models on disk (engine load).
Run:  pytest test/test_endless_radio.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(scope="module")
def rec():
    from core.recommendation_engine import get_recommender
    return get_recommender()


def _track_ids(rec, df):
    """Map a result df back to its track_ids via original_index (label == position)."""
    return [rec.df.loc[int(i), 'track_id'] for i in df['original_index']]


@pytest.mark.slow
def test_color_excludes_played(rec):
    """A 2nd colour batch must contain none of the 1st batch's tracks when excluded."""
    first = rec.recommend_by_colors('#F38400', top_k=10)          # orange
    played = _track_ids(rec, first)
    nxt = rec.recommend_by_colors('#F38400', top_k=10, exclude_ids=played)
    assert not (set(played) & set(_track_ids(rec, nxt))), "excluded tracks leaked back in"
    assert len(nxt) >= 5, "exclusion must not starve the batch"


@pytest.mark.slow
def test_journey_excludes_played(rec):
    """The 2-colour mood-journey path must also honour exclude_ids."""
    a, b = '#848482', '#F3C300'                                   # grey → yellow
    first = rec.recommend_by_colors([a, b], top_k=10)
    played = _track_ids(rec, first)
    nxt = rec.recommend_by_colors([a, b], top_k=10, exclude_ids=played)
    assert not (set(played) & set(_track_ids(rec, nxt))), "journey re-picked played tracks"


@pytest.mark.slow
def test_similar_excludes_played(rec):
    """Re-querying similars with the previous batch excluded yields fresh songs."""
    seed = 0
    first = rec.recommend_by_song(seed, top_k=10)
    played = _track_ids(rec, first)
    nxt = rec.recommend_by_song(seed, top_k=10, exclude_ids=played)
    nxt_ids = _track_ids(rec, nxt)
    assert seed not in [int(i) for i in nxt['original_index']], "seed song must stay excluded"
    assert not (set(played) & set(nxt_ids)), "excluded similars leaked back in"


@pytest.mark.slow
def test_exclude_empty_is_noop(rec):
    """Empty/None exclude_ids must behave exactly like the no-arg call."""
    base = _track_ids(rec, rec.recommend_by_colors('#F38400', top_k=10))
    same = _track_ids(rec, rec.recommend_by_colors('#F38400', top_k=10, exclude_ids=[]))
    assert base == same, "empty exclude_ids changed the ranking"
