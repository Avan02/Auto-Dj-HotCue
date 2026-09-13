"""Detect beat-grid-aligned phrase boundaries and turn them into hot cues.

Approach: run librosa's beat tracker to get a BPM estimate and a list of
beat times, assume 4/4 time (true for the overwhelming majority of tracks
DJs beatmatch), treat the first detected beat as beat 1 of a bar, and place
a cue every `bars_per_phrase` bars starting from the first beat.

This is a heuristic, not a true downbeat detector: if the first beat isn't
actually a downbeat, every cue will be off by a fixed number of beats. Use
`beat_offset` to nudge alignment after listening to the result.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PhraseCuePlan:
    bpm: float
    beat_times_s: list[float]
    cue_times_s: list[float]


def detect_phrase_cues(
    y: np.ndarray,
    sr: int,
    *,
    bars_per_phrase: int = 8,
    beats_per_bar: int = 4,
    beat_offset: int = 0,
    max_cues: int = 8,
) -> PhraseCuePlan:
    import librosa

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    if len(beat_times) == 0:
        return PhraseCuePlan(bpm=bpm, beat_times_s=[], cue_times_s=[])

    beats_per_phrase = bars_per_phrase * beats_per_bar
    start = beat_offset % max(1, beats_per_phrase)

    cue_times = [
        float(beat_times[i])
        for i in range(start, len(beat_times), beats_per_phrase)
    ][:max_cues]

    return PhraseCuePlan(
        bpm=bpm,
        beat_times_s=[float(t) for t in beat_times],
        cue_times_s=cue_times,
    )
