# Existing catalog re-filter

- Input tracks: 5,447
- Kept tracks: 5,138
- Removed tracks: 309
- Non-original versions: 0
- Duplicate song entities: 0
- Exact duplicate name/artist: 0
- Short tracks: 301
- Seasonal tracks: 0
- Other catalog filters: 0
- MP3 files quarantined: 309
- Backup: `backups/catalog_refilter_20260608_144954`

## Filter output

```text
# Brightify Phase 2 – Filter Report
Generated: 2026-06-08 14:49:54
Input: `vietnamese_music_processed_full.csv` — **5,447** rows

[Filter 1] Missing required fields: removed 0 → 5,447
[Filter 2] Duplicate track_id: removed 0 → 5,447
[Filter 2b] Artist name normalization: no variants found
[Filter 3] Duplicate name+artist (diacritics-normalized): removed 0 → 5,447
[Filter 3b] Duplicate song entities (feat/credit/primary variants): removed 0 → 5,447
[Filter 4] Duration out of range (<2m30s except allowlist, or >6m): removed 302 → 5,145
[Filter 5] Non-Vietnamese re-check: removed 0 → 5,145
[Filter 6] Children's music: removed 0 → 5,145
[Filter 6b] Non-artist channels: removed 0 → 5,145
[Filter 6c] Old-genre artists: removed 0 → 5,145
[Filter 6d] Non-original versions removed: 0 → 5,145
[Filter 6d2] Low-value soundtrack scores removed: 0 → 5,145
[Filter 6d3] Verified bad/legacy/audio content: removed 7 → 5,138
[Filter 6e] Foreign artists: removed 0 → 5,138
[Filter 6f] Seasonal music (Tết + Giáng Sinh/Noel): removed 0 → 5,138
[Filter 6g] Release year < 2013 (cols: year+album_release_year+upload_year+upload_date): removed 0 (225 with unknown year kept) → 5,138
[Filter 6h] Profanity in track title: removed 0 → 5,138
[Filter 6i] Profanity-heavy lyrics: removed 0 → 5,138
[Filter 7] Foreign-dominant tracks: removed 0 → 5,138
[Filter 7b] Pure-ASCII foreign tracks: removed 0 → 5,138
[Filter 7c] Foreign-language lyrics: removed 0 → 5,138
[Filter 8] Low-quality/obscure artists (blocklist + max_pop<15): removed 0 → 5,138
[Filter 8d] Low YouTube views (< 100,000, no popularity override): removed 0; releases from 2022 keep at 50,000+ → 5,138

## Summary
- Input: 5,447
- Output: 5,138
- Removed: 309 (5.7%)
```
