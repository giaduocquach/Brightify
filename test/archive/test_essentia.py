"""
Test essentia: audio feature extraction from existing music files
Compare with Spotify's 12 audio features (danceability, energy, valence, tempo, etc.)
"""
import time
import os
import sys
import json
import glob
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
    # Pick evenly spaced samples
    step = max(1, len(files) // n)
    samples = [files[i] for i in range(0, len(files), step)][:n]
    print(f"  Selected {len(samples)} samples from {len(files)} total MP3s")
    for f in samples:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"    - {f.name} ({size_mb:.1f} MB)")
    return samples


def test_basic_features():
    """Extract basic audio features using essentia standard mode"""
    print("=" * 70)
    print("TEST 1: essentia basic feature extraction")
    print("=" * 70)

    try:
        import essentia
        import essentia.standard as es
    except ImportError:
        print("  ❌ essentia not installed")
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
            loader = es.MonoLoader(filename=str(fpath), sampleRate=44100)
            audio = loader()
            load_time = time.time() - t0

            t1 = time.time()
            features = {}

            # Rhythm / Tempo
            rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
            bpm, beats, beats_conf, _, beats_intervals = rhythm_extractor(audio)
            features["tempo_bpm"] = round(float(bpm), 1)
            features["beats_count"] = len(beats)

            # Key detection
            key_extractor = es.KeyExtractor()
            key, scale, key_strength = key_extractor(audio)
            features["key"] = key
            features["scale"] = scale
            features["key_strength"] = round(float(key_strength), 3)

            # Energy & Loudness
            energy = es.Energy()(audio)
            features["energy"] = round(float(energy), 4)
            loudness = es.Loudness()(audio)
            features["loudness"] = round(float(loudness), 4)
            dynamic_complexity, loudness_band = es.DynamicComplexity()(audio)
            features["dynamic_complexity"] = round(float(dynamic_complexity), 4)

            # Spectral features
            spectrum = es.Spectrum()(audio)
            spectral_centroid = es.Centroid(range=22050)(spectrum)
            features["spectral_centroid"] = round(float(spectral_centroid), 4)

            # Danceability
            danceability, _ = es.Danceability()(audio)
            features["danceability"] = round(float(danceability), 4)

            # Duration
            features["duration_s"] = round(len(audio) / 44100, 2)

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
            print(f"    ✅ {total_time:.2f}s | BPM={bpm:.0f} Key={key}{scale} "
                  f"Danceability={danceability:.3f} Energy={energy:.1f}")
            results.append(res)

        except Exception as e:
            print(f"    ❌ Error: {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def test_music_extractor():
    """Use essentia MusicExtractor for comprehensive analysis"""
    print("\n" + "=" * 70)
    print("TEST 2: essentia MusicExtractor (comprehensive)")
    print("=" * 70)

    try:
        import essentia.standard as es
    except ImportError:
        return {"error": "not installed"}

    samples = get_sample_mp3s(2)  # Fewer samples, this is slower
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        t0 = time.time()
        try:
            features, features_frames = es.MusicExtractor(
                lowlevelStats=["mean", "stdev"],
                rhythmStats=["mean", "stdev"],
                tonalStats=["mean", "stdev"],
            )(str(fpath))

            elapsed = time.time() - t0

            # Collect key features
            summary = {}
            interesting_keys = [
                "rhythm.bpm",
                "rhythm.beats_count",
                "rhythm.danceability",
                "tonal.key_edma.key", "tonal.key_edma.scale",
                "tonal.key_edma.strength",
                "tonal.chords_key", "tonal.chords_scale",
                "lowlevel.average_loudness",
                "lowlevel.dynamic_complexity",
                "lowlevel.spectral_centroid.mean",
                "lowlevel.mfcc.mean",
                "lowlevel.dissonance.mean",
                "metadata.audio_properties.length",
                "metadata.audio_properties.bit_rate",
                "metadata.audio_properties.sample_rate",
            ]
            for k in interesting_keys:
                try:
                    val = features[k]
                    if hasattr(val, "__len__") and len(val) > 5:
                        val = list(val[:5])  # Truncate arrays
                    elif hasattr(val, "item"):
                        val = val.item()
                    summary[k] = val
                except Exception:
                    pass

            # Count total descriptors
            desc_names = features.descriptorNames()
            res = {
                "file": fpath.name,
                "total_descriptors": len(desc_names),
                "extract_time_s": round(elapsed, 2),
                "key_features": summary,
                "success": True,
            }
            print(f"    ✅ {elapsed:.1f}s | {len(desc_names)} descriptors extracted")
            for k, v in summary.items():
                if not isinstance(v, list):
                    print(f"       {k}: {v}")
            results.append(res)

        except Exception as e:
            print(f"    ❌ Error: {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def test_tempo_accuracy():
    """Test tempo detection consistency across methods"""
    print("\n" + "=" * 70)
    print("TEST 3: essentia tempo detection (multi-method)")
    print("=" * 70)

    try:
        import essentia
        import essentia.standard as es
    except ImportError:
        return {"error": "not installed"}

    samples = get_sample_mp3s(3)
    if not samples:
        return {"error": "no samples"}

    results = []
    for fpath in samples:
        print(f"\n  Processing: {fpath.name}")
        try:
            audio = es.MonoLoader(filename=str(fpath), sampleRate=44100)()

            methods = {}
            for method in ["multifeature", "degara"]:
                try:
                    bpm, _, _, _, _ = es.RhythmExtractor2013(method=method)(audio)
                    methods[method] = round(float(bpm), 1)
                except Exception as e:
                    methods[method] = f"error: {e}"

            # Also try PercivalBpmEstimator
            try:
                bpm = es.PercivalBpmEstimator()(audio)
                methods["percival"] = round(float(bpm), 1)
            except Exception as e:
                methods["percival"] = f"error: {e}"

            res = {"file": fpath.name, "bpm_by_method": methods, "success": True}
            print(f"    BPMs: {methods}")
            results.append(res)

        except Exception as e:
            print(f"    ❌ {e}")
            results.append({"file": fpath.name, "success": False, "error": str(e)})

    return results


def make_serializable(obj):
    """Convert numpy types to native Python for JSON serialization"""
    import numpy as np
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def main():
    print("🔧 essentia Test Suite")
    print()

    all_results = {}

    # Check installation
    try:
        import essentia
        ver = getattr(essentia, "__version__", "unknown")
        print(f"essentia version: {ver}\n")
        all_results["version"] = ver
    except ImportError:
        print("❌ essentia not installed. Install with:")
        print("   pip install essentia")
        all_results["error"] = "not installed"
        out_path = PROJECT_ROOT / "test" / "results_essentia.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        return

    all_results["basic_features"] = test_basic_features()
    all_results["music_extractor"] = test_music_extractor()
    all_results["tempo_accuracy"] = test_tempo_accuracy()

    # Serialize and save
    all_results = make_serializable(all_results)
    out_path = PROJECT_ROOT / "test" / "results_essentia.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📁 Results saved to {out_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: essentia")
    print("=" * 70)
    basic = all_results.get("basic_features", [])
    if isinstance(basic, list):
        ok = sum(1 for r in basic if r.get("success"))
        avg_t = sum(r.get("total_time_s", 0) for r in basic if r.get("success"))
        avg_t = avg_t / ok if ok else 0
        print(f"  Basic extraction: {ok}/{len(basic)} success, avg {avg_t:.2f}s/file")
    me = all_results.get("music_extractor", [])
    if isinstance(me, list):
        ok = sum(1 for r in me if r.get("success"))
        print(f"  MusicExtractor:   {ok}/{len(me)} success")
    ta = all_results.get("tempo_accuracy", [])
    if isinstance(ta, list):
        ok = sum(1 for r in ta if r.get("success"))
        print(f"  Tempo accuracy:   {ok}/{len(ta)} success")


if __name__ == "__main__":
    main()
