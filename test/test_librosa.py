"""
Test librosa: audio feature extraction from existing music files
Compare capabilities with essentia for the Brightify recommendation system
"""
import time
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MUSIC_DIR = PROJECT_ROOT / "music_files"


def get_sample_mp3s(n=5):
    """Get N sample MP3 files from music_files/"""
    files = sorted(MUSIC_DIR.glob("*.mp3"))
    if not files:
        print("⚠️ No MP3 files found in music_files/")
        return []
    step = max(1, len(files) // n)
    samples = [files[i] for i in range(0, len(files), step)][:n]
    print(f"  Selected {len(samples)} samples from {len(files)} total MP3s")
    for f in samples:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"    - {f.name} ({size_mb:.1f} MB)")
    return samples


def test_basic_features():
    """Extract basic audio features using librosa"""
    print("=" * 70)
    print("TEST 1: librosa basic feature extraction")
    print("=" * 70)

    try:
        import librosa
        import numpy as np
    except ImportError:
        print("  ❌ librosa not installed")
        return {"error": "not installed"}

    samples = get_sample_mp3s(5)
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        t0 = time.time()
        try:
            # Load audio
            y, sr = librosa.load(str(fpath), sr=22050)
            load_time = time.time() - t0

            t1 = time.time()
            features = {}

            # Duration
            features["duration_s"] = round(len(y) / sr, 2)

            # Tempo (BPM)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            # tempo can be an array in newer versions
            if hasattr(tempo, "__len__"):
                tempo = float(tempo[0]) if len(tempo) > 0 else 0.0
            features["tempo_bpm"] = round(float(tempo), 1)
            features["beats_count"] = len(beat_frames)

            # RMS Energy
            rms = librosa.feature.rms(y=y)[0]
            features["rms_energy_mean"] = round(float(np.mean(rms)), 6)
            features["rms_energy_std"] = round(float(np.std(rms)), 6)

            # Spectral Centroid
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            features["spectral_centroid_mean"] = round(float(np.mean(centroid)), 2)

            # Spectral Rolloff
            rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            features["spectral_rolloff_mean"] = round(float(np.mean(rolloff)), 2)

            # Zero Crossing Rate
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            features["zero_crossing_rate_mean"] = round(float(np.mean(zcr)), 6)

            # MFCCs (13 coefficients)
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            features["mfcc_means"] = [round(float(m), 3) for m in np.mean(mfccs, axis=1)]

            # Chroma features
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            features["chroma_means"] = [round(float(c), 4) for c in np.mean(chroma, axis=1)]

            # Tonnetz (tonal centroid)
            try:
                tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
                features["tonnetz_means"] = [round(float(t), 4) for t in np.mean(tonnetz, axis=1)]
            except Exception:
                features["tonnetz_means"] = None

            extract_time = time.time() - t1
            total_time = time.time() - t0

            res = {
                "file": fpath.name,
                "features": features,
                "load_time_s": round(load_time, 3),
                "extract_time_s": round(extract_time, 3),
                "total_time_s": round(total_time, 3),
                "success": True,
            }
            print(f"    ✅ {total_time:.2f}s | BPM={features['tempo_bpm']} "
                  f"RMS={features['rms_energy_mean']:.4f} "
                  f"Centroid={features['spectral_centroid_mean']:.0f}Hz")
            results.append(res)

        except Exception as e:
            print(f"    ❌ Error: {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def test_key_detection():
    """Attempt key/scale detection using chroma features"""
    print("\n" + "=" * 70)
    print("TEST 2: librosa key detection via chroma")
    print("=" * 70)

    try:
        import librosa
        import numpy as np
    except ImportError:
        return {"error": "not installed"}

    KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    # Krumhansl-Schmuckler key profiles
    MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    samples = get_sample_mp3s(3)
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        try:
            y, sr = librosa.load(str(fpath), sr=22050)
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            chroma_avg = np.mean(chroma, axis=1)

            # Correlate with all 24 keys (12 major + 12 minor)
            best_corr = -1
            best_key = "?"
            best_scale = "?"

            for i in range(12):
                rolled_major = np.roll(MAJOR_PROFILE, i)
                rolled_minor = np.roll(MINOR_PROFILE, i)

                corr_major = float(np.corrcoef(chroma_avg, rolled_major)[0, 1])
                corr_minor = float(np.corrcoef(chroma_avg, rolled_minor)[0, 1])

                if corr_major > best_corr:
                    best_corr = corr_major
                    best_key = KEY_NAMES[i]
                    best_scale = "major"
                if corr_minor > best_corr:
                    best_corr = corr_minor
                    best_key = KEY_NAMES[i]
                    best_scale = "minor"

            res = {
                "file": fpath.name,
                "key": best_key,
                "scale": best_scale,
                "correlation": round(best_corr, 4),
                "success": True,
            }
            print(f"    Key: {best_key} {best_scale} (corr={best_corr:.3f})")
            results.append(res)

        except Exception as e:
            print(f"    ❌ {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def test_onset_and_segments():
    """Test onset detection and segment boundaries"""
    print("\n" + "=" * 70)
    print("TEST 3: librosa onset detection & segmentation")
    print("=" * 70)

    try:
        import librosa
        import numpy as np
    except ImportError:
        return {"error": "not installed"}

    samples = get_sample_mp3s(3)
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        t0 = time.time()
        try:
            y, sr = librosa.load(str(fpath), sr=22050)

            # Onset detection
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)

            # Spectral contrast for segmentation
            S = np.abs(librosa.stft(y))
            contrast = librosa.feature.spectral_contrast(S=S, sr=sr)

            elapsed = time.time() - t0
            res = {
                "file": fpath.name,
                "onsets_count": len(onset_frames),
                "onset_rate_per_sec": round(len(onset_frames) / (len(y) / sr), 2),
                "first_5_onsets_s": [round(float(t), 2) for t in onset_times[:5]],
                "spectral_contrast_shape": list(contrast.shape),
                "extract_time_s": round(elapsed, 3),
                "success": True,
            }
            print(f"    ✅ {elapsed:.2f}s | {len(onset_frames)} onsets, "
                  f"rate={res['onset_rate_per_sec']}/s")
            results.append(res)

        except Exception as e:
            print(f"    ❌ {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def test_performance_benchmark():
    """Benchmark librosa feature extraction speed"""
    print("\n" + "=" * 70)
    print("TEST 4: librosa performance benchmark")
    print("=" * 70)

    try:
        import librosa
        import numpy as np
    except ImportError:
        return {"error": "not installed"}

    samples = get_sample_mp3s(3)
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        timings = {}

        t0 = time.time()
        y, sr = librosa.load(str(fpath), sr=22050)
        timings["load"] = round(time.time() - t0, 3)

        t0 = time.time()
        librosa.beat.beat_track(y=y, sr=sr)
        timings["tempo"] = round(time.time() - t0, 3)

        t0 = time.time()
        librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        timings["mfcc"] = round(time.time() - t0, 3)

        t0 = time.time()
        librosa.feature.chroma_stft(y=y, sr=sr)
        timings["chroma"] = round(time.time() - t0, 3)

        t0 = time.time()
        librosa.feature.rms(y=y)
        librosa.feature.spectral_centroid(y=y, sr=sr)
        librosa.feature.spectral_rolloff(y=y, sr=sr)
        librosa.feature.zero_crossing_rate(y)
        timings["spectral_bundle"] = round(time.time() - t0, 3)

        t0 = time.time()
        librosa.onset.onset_detect(y=y, sr=sr)
        timings["onset"] = round(time.time() - t0, 3)

        timings["total"] = round(sum(timings.values()), 3)
        duration = len(y) / sr

        res = {
            "file": fpath.name,
            "duration_s": round(duration, 1),
            "timings": timings,
            "realtime_factor": round(timings["total"] / duration, 3),
            "success": True,
        }
        print(f"    Duration: {duration:.1f}s | Total: {timings['total']:.2f}s "
              f"({res['realtime_factor']:.2f}x realtime)")
        for k, v in timings.items():
            if k != "total":
                print(f"      {k}: {v:.3f}s")
        results.append(res)

    return results


def main():
    print("🔧 librosa Test Suite")
    print()

    all_results = {}

    try:
        import librosa
        ver = librosa.__version__
        print(f"librosa version: {ver}\n")
        all_results["version"] = ver
    except ImportError:
        print("❌ librosa not installed. Install with:")
        print("   pip install librosa")
        all_results["error"] = "not installed"
        out_path = PROJECT_ROOT / "test" / "results_librosa.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        return

    all_results["basic_features"] = test_basic_features()
    all_results["key_detection"] = test_key_detection()
    all_results["onset_segments"] = test_onset_and_segments()
    all_results["performance"] = test_performance_benchmark()

    # Save
    out_path = PROJECT_ROOT / "test" / "results_librosa.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📁 Results saved to {out_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: librosa")
    print("=" * 70)
    basic = all_results.get("basic_features", [])
    if isinstance(basic, list):
        ok = sum(1 for r in basic if r.get("success"))
        avg_t = sum(r.get("total_time_s", 0) for r in basic if r.get("success"))
        avg_t = avg_t / ok if ok else 0
        print(f"  Basic extraction: {ok}/{len(basic)} success, avg {avg_t:.2f}s/file")
    kd = all_results.get("key_detection", [])
    if isinstance(kd, list):
        ok = sum(1 for r in kd if r.get("success"))
        print(f"  Key detection:    {ok}/{len(kd)} success")
    perf = all_results.get("performance", [])
    if isinstance(perf, list) and perf:
        avg_rt = sum(r.get("realtime_factor", 0) for r in perf if r.get("success"))
        ok = sum(1 for r in perf if r.get("success"))
        avg_rt = avg_rt / ok if ok else 0
        print(f"  Avg speed:        {avg_rt:.2f}x realtime")


if __name__ == "__main__":
    main()
