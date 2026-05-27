"""Drop-one-signal ablation → rank signals by importance. §11.2 — Phase 3.

For each signal in {timbral, rhythmic, tonal, lyrics, va, emotion, mood}:
zero its weight, normalize the rest, re-run, record ΔNDCG@10 / ΔILD / ΔMoodCoherence.
Largest |ΔNDCG@10| = most important signal → upgrade that pillar first.
"""

from __future__ import annotations

from typing import Any

SIGNALS = ["timbral", "rhythmic", "tonal", "lyrics", "va", "emotion", "mood"]


def run_ablation(runner: Any, ground_truth: Any = None):
    raise NotImplementedError("run_ablation — Phase 3")
