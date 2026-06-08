#!/usr/bin/env python3
"""Audit catalog audio for instrumental, spoken-word, fragment, and duration issues."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "vietnamese_music_processed_full.csv"
DEFAULT_MUSIC_DIR = PROJECT_ROOT / "music_files"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "catalog_audio_quality_audit.csv"
MODEL_DIR = PROJECT_ROOT / "models_cache"

_FRAGMENT_RE = re.compile(
    r"\b(?:audio cut|short version|snippet|teaser|intro|interlude|outro|"
    r"prologue|epilogue|special thanks|opening|ending|skit|"
    r"part\s*\d+|pt\.?\s*\d+|tap\s*\d+|tập\s*\d+)\b|"
    r"(?:^|\s)[#\[]\d+[\]\s]*$",
    re.IGNORECASE,
)
_PROGRAM_RE = re.compile(
    r"\b(?:san dau ca tu|sàn đấu ca từ|gameshow|talkshow|podcast|"
    r"phong tra|phòng trà|liveshow|live show|concert|minishow)\b",
    re.IGNORECASE,
)
_SCORE_RE = re.compile(
    r"\b(?:original motion picture soundtrack|motion picture soundtrack|"
    r"film score|background score|score|theme|soundtrack|ost)\b",
    re.IGNORECASE,
)


def _actual_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return round(float(result.stdout.strip()), 3)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _candidate_mask(df: pd.DataFrame) -> pd.Series:
    duration = pd.to_numeric(df.get("track_duration_ms"), errors="coerce") / 1000
    context = (
        df.get("track_name", pd.Series("", index=df.index)).fillna("").astype(str)
        + " "
        + df.get("album_name", pd.Series("", index=df.index)).fillna("").astype(str)
    )
    instrumentalness = pd.to_numeric(
        df.get("instrumentalness", pd.Series(np.nan, index=df.index)),
        errors="coerce",
    )
    speechiness = pd.to_numeric(
        df.get("speechiness", pd.Series(np.nan, index=df.index)),
        errors="coerce",
    )
    return (
        duration.lt(150)
        | duration.gt(300)
        | duration.isna()
        | context.str.contains(_FRAGMENT_RE, na=False)
        | context.str.contains(_PROGRAM_RE, na=False)
        | context.str.contains(_SCORE_RE, na=False)
        | instrumentalness.isna()
        | speechiness.isna()
        | instrumentalness.ge(0.65)
        | speechiness.ge(0.55)
    )


class AudioModels:
    def __init__(self, with_yamnet: bool):
        import essentia
        import essentia.standard as es

        essentia.log.infoActive = False
        essentia.log.warningActive = False
        self.es = es
        self.embedding_model = es.TensorflowPredictEffnetDiscogs(
            graphFilename=str(MODEL_DIR / "discogs-effnet-bs64-1.pb"),
            output="PartitionedCall:1",
        )
        self.voice_model = es.TensorflowPredict2D(
            graphFilename=str(MODEL_DIR / "voice_instrumental-discogs-effnet-1.pb"),
            output="model/Softmax",
        )
        self.yamnet = None
        self.yamnet_classes: list[str] = []
        if with_yamnet:
            metadata_path = MODEL_DIR / "audioset-yamnet-1.json"
            model_path = MODEL_DIR / "audioset-yamnet-1.pb"
            if metadata_path.exists() and model_path.exists():
                self.yamnet_classes = json.loads(
                    metadata_path.read_text(encoding="utf-8")
                )["classes"]
                self.yamnet = es.TensorflowPredictVGGish(
                    graphFilename=str(model_path),
                    input="melspectrogram",
                    output="activations",
                )

    def analyze(self, mp3_path: Path, run_yamnet: bool) -> dict:
        audio = self.es.MonoLoader(
            filename=str(mp3_path),
            sampleRate=16000,
            resampleQuality=4,
        )()
        voice_predictions = self.voice_model(self.embedding_model(audio))
        voice_average = np.mean(voice_predictions, axis=0)
        result = {
            "instrumental_probability": round(float(voice_average[0]), 5),
            "voice_probability": round(float(voice_average[1]), 5),
        }
        if not run_yamnet or self.yamnet is None:
            return result

        predictions = self.yamnet(audio)
        classes = self.yamnet_classes
        speech_labels = {
            "Speech",
            "Child speech, kid speaking",
            "Conversation",
            "Narration, monologue",
            "Babbling",
            "Speech synthesizer",
            "Chatter",
            "Hubbub, speech noise, speech babble",
        }
        singing_labels = {"Singing", "Rapping", "Vocal music", "Song"}
        music_labels = {
            "Music",
            "Musical instrument",
            "Pop music",
            "Hip hop music",
            "Electronic music",
            "Dance music",
            "Background music",
            "Soundtrack music",
            "Song",
        }
        speech_idx = [i for i, label in enumerate(classes) if label in speech_labels]
        singing_idx = [i for i, label in enumerate(classes) if label in singing_labels]
        music_idx = [i for i, label in enumerate(classes) if label in music_labels]
        speech_frames = np.max(predictions[:, speech_idx], axis=1)
        singing_frames = np.max(predictions[:, singing_idx], axis=1)
        music_frames = np.max(predictions[:, music_idx], axis=1)
        result.update(
            {
                "yamnet_speech_mean": round(float(np.mean(speech_frames)), 5),
                "yamnet_speech_p90": round(float(np.quantile(speech_frames, 0.9)), 5),
                "yamnet_speech_max": round(float(np.max(speech_frames)), 5),
                "yamnet_singing_mean": round(float(np.mean(singing_frames)), 5),
                "yamnet_music_mean": round(float(np.mean(music_frames)), 5),
                "speech_dominant_fraction": round(
                    float(np.mean((speech_frames >= 0.10) & (speech_frames > music_frames))),
                    5,
                ),
                "low_music_fraction": round(float(np.mean(music_frames < 0.10)), 5),
            }
        )
        return result


def _should_run_yamnet(row: pd.Series, actual_duration: float | None) -> bool:
    context = f"{row.get('track_name', '')} {row.get('album_name', '')}"
    duration = actual_duration
    if duration is None:
        raw = pd.to_numeric(pd.Series([row.get("track_duration_ms")]), errors="coerce").iloc[0]
        duration = float(raw) / 1000 if pd.notna(raw) else None
    return bool(
        duration is None
        or duration < 150
        or _FRAGMENT_RE.search(context)
        or _PROGRAM_RE.search(context)
        or _SCORE_RE.search(context)
    )


def audit(
    catalog_path: Path,
    music_dir: Path,
    output_path: Path,
    resume: bool,
    limit: int | None,
    shard_index: int = 0,
    shard_count: int = 1,
) -> pd.DataFrame:
    catalog = pd.read_csv(catalog_path)
    candidates = catalog.loc[_candidate_mask(catalog)].copy()
    if shard_count > 1:
        candidates = candidates.iloc[shard_index::shard_count].copy()
    if limit:
        candidates = candidates.head(limit)

    existing = pd.DataFrame()
    if resume and output_path.exists():
        existing = pd.read_csv(output_path)
    done_ids = set(existing.get("track_id", pd.Series(dtype=str)).astype(str))
    pending = candidates[~candidates["track_id"].astype(str).isin(done_ids)]
    models = AudioModels(with_yamnet=True)
    records: list[dict] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for _, row in tqdm(pending.iterrows(), total=len(pending), desc="Audio quality audit"):
        track_id = str(row["track_id"])
        mp3_path = music_dir / f"{track_id}.mp3"
        record = {
            "track_id": track_id,
            "track_name": row.get("track_name"),
            "artists": row.get("artists"),
            "primary_artist": row.get("primary_artist"),
            "album_name": row.get("album_name"),
            "metadata_duration_s": (
                round(float(row["track_duration_ms"]) / 1000, 3)
                if pd.notna(row.get("track_duration_ms"))
                else None
            ),
            "mp3_exists": mp3_path.exists(),
        }
        if mp3_path.exists():
            actual_duration = _actual_duration(mp3_path)
            record["actual_duration_s"] = actual_duration
            try:
                record.update(
                    models.analyze(
                        mp3_path,
                        run_yamnet=_should_run_yamnet(row, actual_duration),
                    )
                )
            except Exception as exc:
                record["analysis_error"] = str(exc)
        records.append(record)
        if len(records) % 25 == 0:
            combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
            combined.to_csv(output_path, index=False, encoding="utf-8-sig")

    combined = pd.concat([existing, pd.DataFrame(records)], ignore_index=True)
    combined = combined.drop_duplicates("track_id", keep="last")
    combined.to_csv(output_path, index=False, encoding="utf-8-sig")
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--music-dir", type=Path, default=DEFAULT_MUSIC_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index must be between 0 and --shard-count - 1")
    result = audit(
        args.catalog.resolve(),
        args.music_dir.resolve(),
        args.output.resolve(),
        args.resume,
        args.limit,
        args.shard_index,
        args.shard_count,
    )
    print(f"Audited: {len(result):,}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
