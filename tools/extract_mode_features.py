"""A1.1 — Extract major-minor mode score from audio (V27).

major-minorness ∈ [0,1] via Krumhansl-Kessler chroma profiles:
  1.0 = strongly major → high valence
  0.0 = strongly minor → low valence

Cross-cultural validation: major/minor predicts ~45% of valence variance
(meta-analysis; AAAI 2026 MoGE arXiv:2512.17946; Spearman 2025).

Run: python -m tools.extract_mode_features [--limit N] [--workers N]
Output: var/runtime/features/mode_scores.json  {track_id: score}
"""
import json, os, sys, argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

MUSIC_DIR  = "music_files"
OUT_PATH   = "var/runtime/features/mode_scores.json"
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# Krumhansl-Kessler 1982 key-profile weights (12 pitch classes, starting C)
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                     2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                     2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def compute_mode_score(audio_path: str, duration: float = 60.0) -> float:
    """Compute major-minorness ∈ [0,1] from first `duration` seconds.

    Uses Krumhansl-Schmuckler key-finding: max correlation of chroma vector
    with KK major/minor profiles over all 12 transpositions.
    Returns (r_major - r_minor + 1) / 2, clipped to [0,1].
    """
    import librosa
    y, sr = librosa.load(audio_path, sr=None, duration=duration, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, bins_per_octave=36)
    chroma_mean = np.mean(chroma, axis=1)

    r_maj = -np.inf
    r_min = -np.inf
    for k in range(12):
        r = np.corrcoef(chroma_mean, np.roll(KK_MAJOR, k))[0, 1]
        if r > r_maj:
            r_maj = r
        r = np.corrcoef(chroma_mean, np.roll(KK_MINOR, k))[0, 1]
        if r > r_min:
            r_min = r

    return float(np.clip((r_maj - r_min + 1) / 2, 0, 1))


def _worker(args):
    track_id, path = args
    try:
        score = compute_mode_score(path)
        return track_id, score, None
    except Exception as e:
        return track_id, None, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',   type=int, default=0,  help='Max tracks (0=all)')
    parser.add_argument('--workers', type=int, default=4,  help='Parallel workers')
    args, _ = parser.parse_known_args()

    # Load catalog to get track_ids
    from core.recommendation_engine import get_recommender
    print("Loading catalog...")
    rec = get_recommender()
    track_ids = rec.df['track_id'].tolist()

    # Load existing results (resume)
    existing = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            existing = json.load(f)
    print(f"Catalog: {len(track_ids)} tracks  Already done: {len(existing)}")

    # Build work list
    work = []
    for tid in track_ids:
        if tid in existing:
            continue
        path = os.path.join(MUSIC_DIR, f"{tid}.mp3")
        if os.path.exists(path):
            work.append((tid, path))
    if args.limit:
        work = work[:args.limit]

    print(f"To process: {len(work)} tracks  workers={args.workers}")
    if not work:
        print("Nothing to do.")
        return

    results = dict(existing)
    errors = 0

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_worker, item): item[0] for item in work}
        done = 0
        for fut in as_completed(futs):
            tid, score, err = fut.result()
            done += 1
            if err:
                errors += 1
                if errors <= 5:
                    print(f"  WARN {tid}: {err}")
            else:
                results[tid] = round(score, 4)
            if done % 100 == 0:
                print(f"  {done}/{len(work)} done  errors={errors}")
                with open(OUT_PATH, 'w') as f:
                    json.dump(results, f)

    with open(OUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nDone. {len(results)} tracks in {OUT_PATH}  errors={errors}")

    # Quick stats
    vals = list(results.values())
    print(f"mode_score stats: mean={np.mean(vals):.3f}  std={np.std(vals):.3f}  "
          f"min={np.min(vals):.3f}  max={np.max(vals):.3f}")
    print(f"Major (≥0.6): {sum(1 for v in vals if v >= 0.6)/len(vals)*100:.1f}%  "
          f"Minor (≤0.4): {sum(1 for v in vals if v <= 0.4)/len(vals)*100:.1f}%")


if __name__ == "__main__":
    main()
