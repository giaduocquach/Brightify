"""Artist-diversity helper extracted from MusicRecommender (behaviour-preserving).
Pure list logic — the recommender passes its `self.artists` array in."""


def cap_per_artist(indices, artists, max_per_artist, top_k):
    """Keep at most `max_per_artist` songs per artist, preserving the input order,
    until `top_k` are collected. Works regardless of DIVERSITY_METHOD. Backfills
    from the surplus if the cap leaves the list short.

    `artists`: per-song-index artist array (or None to disable capping)."""
    if artists is None or not max_per_artist:
        return list(indices)[:top_k]
    out, counts, seen = [], {}, set()
    for idx in indices:
        artist = artists[idx]
        if artist and counts.get(artist, 0) >= max_per_artist:
            continue
        out.append(idx); seen.add(idx)
        if artist:
            counts[artist] = counts.get(artist, 0) + 1
        if len(out) >= top_k:
            return out
    for idx in indices:  # backfill if cap left us short
        if idx not in seen:
            out.append(idx)
            if len(out) >= top_k:
                break
    return out
