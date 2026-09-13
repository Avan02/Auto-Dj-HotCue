"""Structural hot-cue detection: place cues at drops, breakdowns, and phrase
transitions instead of a uniform every-N-bars grid.

Technique:

1. Beat-track the audio (same as phrase mode) and beat-synchronize a set of
   timbre/harmony features (MFCC + chroma) -- this both denoises the
   features and guarantees every candidate boundary lands exactly on a beat.
2. Build a self-similarity matrix (SSM) from those beat-synced features and
   convolve it with a Foote "checkerboard" kernel to get a novelty curve:
   peaks in this curve are where the music's timbre/harmony changes the
   most abruptly -- i.e. section/phrase transitions. This is a standard,
   well-established MIR technique (Foote, 2000), not a trained model.
3. Separately track beat-synced low-frequency ("bass") energy. A candidate
   boundary where bass energy jumps up sharply is labeled a likely "Drop";
   a sharp drop in overall energy is labeled a likely "Breakdown".
4. Greedily pick the highest-scoring boundaries (novelty + energy-jump
   magnitude), enforcing a minimum spacing so cues don't cluster, always
   keeping an "Intro" cue near the start, up to `max_cues`.

This is heuristic signal processing, not genre-aware machine learning --
it finds *where the audio itself changes character*, which in practice
lines up with drops/breakdowns/transitions for most dance music, but it
can miss or misplace boundaries in unusual arrangements. Always spot-check
results (`--mode structural` without `--apply` first).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class StructuralCue:
    time_s: float
    beat_index: int
    label: str
    score: float


@dataclass
class StructuralCuePlan:
    bpm: float
    beat_times_s: list[float]
    cues: list[StructuralCue] = field(default_factory=list)


def _checkerboard_kernel(half_size: int) -> np.ndarray:
    axis = np.arange(-half_size, half_size + 1)
    x, y = np.meshgrid(axis, axis)
    taper = np.exp(-(x ** 2 + y ** 2) / (2 * (half_size / 1.4 + 1e-9) ** 2))
    checker = np.sign(x) * np.sign(y)
    checker[checker == 0] = 1.0
    return taper * checker


def _novelty_curve(ssm: np.ndarray, half_size: int) -> np.ndarray:
    n = ssm.shape[0]
    kernel = _checkerboard_kernel(half_size)
    ksz = kernel.shape[0]
    padded = np.pad(ssm, half_size, mode="edge")
    novelty = np.zeros(n)
    for i in range(n):
        window = padded[i:i + ksz, i:i + ksz]
        novelty[i] = float(np.sum(window * kernel))
    novelty -= novelty.min()
    peak = novelty.max()
    if peak > 0:
        novelty /= peak
    return novelty


def _normalize(x: np.ndarray) -> np.ndarray:
    x = x - x.min()
    peak = x.max()
    return x / peak if peak > 0 else x


def detect_structural_cues(
    y: np.ndarray,
    sr: int,
    *,
    beats_per_bar: int = 4,
    novelty_window_bars: int = 4,
    min_bars_between_cues: int = 4,
    energy_jump_weight: float = 1.0,
    max_cues: int = 8,
    bass_max_hz: float = 200.0,
) -> StructuralCuePlan:
    import librosa
    from scipy.signal import find_peaks

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if len(beat_frames) < 4:
        return StructuralCuePlan(bpm=bpm, beat_times_s=[float(t) for t in beat_times], cues=[])

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    features = np.vstack([_normalize(chroma), _normalize(mfcc)])
    beat_features = librosa.util.sync(features, beat_frames, aggregate=np.median, pad=True)

    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    bass_mask = freqs <= bass_max_hz
    bass_energy_frames = stft[bass_mask].mean(axis=0)
    bass_energy = librosa.util.sync(bass_energy_frames[np.newaxis, :], beat_frames,
                                     aggregate=np.mean, pad=True)[0]
    rms_frames = librosa.feature.rms(y=y)[0]
    total_energy = librosa.util.sync(rms_frames[np.newaxis, :], beat_frames,
                                      aggregate=np.mean, pad=True)[0]

    n_beats = beat_features.shape[1]
    norm = np.linalg.norm(beat_features, axis=0, keepdims=True)
    norm[norm == 0] = 1.0
    unit = beat_features / norm
    ssm = unit.T @ unit

    half_size = max(2, (novelty_window_bars * beats_per_bar) // 2)
    novelty = _novelty_curve(ssm, half_size)

    min_distance = max(1, min_bars_between_cues * beats_per_bar)
    novelty_peaks, _ = find_peaks(novelty, distance=min_distance, prominence=0.05)

    bass_norm = _normalize(bass_energy)
    energy_norm = _normalize(total_energy)
    window = beats_per_bar

    def energy_jump(idx: int) -> float:
        before = bass_norm[max(0, idx - window):idx].mean() if idx > 0 else bass_norm[0]
        after = bass_norm[idx:idx + window].mean() if idx < len(bass_norm) else bass_norm[-1]
        return float(after - before)

    def energy_drop(idx: int) -> float:
        before = energy_norm[max(0, idx - window):idx].mean() if idx > 0 else energy_norm[0]
        after = energy_norm[idx:idx + window].mean() if idx < len(energy_norm) else energy_norm[-1]
        return float(before - after)

    # Novelty (timbre/harmony change) alone can miss a drop where the main
    # signature is a sudden energy jump rather than a big timbral shift, so
    # independently scan the energy-jump/drop curves for their own peaks and
    # merge those candidate boundaries in too.
    jump_curve = np.array([energy_jump(i) for i in range(n_beats)])
    drop_curve = np.array([energy_drop(i) for i in range(n_beats)])
    jump_peaks, _ = find_peaks(jump_curve, distance=min_distance, prominence=0.15)
    drop_peaks, _ = find_peaks(drop_curve, distance=min_distance, prominence=0.15)

    all_peak_idx = sorted(set(novelty_peaks) | set(jump_peaks) | set(drop_peaks))

    candidates = []
    for idx in all_peak_idx:
        idx = int(min(idx, n_beats - 1))
        jump = energy_jump(idx)
        drop = energy_drop(idx)
        score = novelty[idx] + energy_jump_weight * max(0.0, jump, drop)
        if jump > 0.15:
            label = "Drop"
        elif drop > 0.15:
            label = "Breakdown"
        else:
            label = "Transition"
        candidates.append((idx, label, score))

    # Select real (non-Intro) candidates first, reserving room for a forced
    # Intro cue at the very start. Spacing between two real structural
    # candidates uses the full min_distance, but a *separate*, much tighter
    # threshold governs whether the forced Intro anchor suppresses a real
    # candidate -- an early drop just a bar or two into the track is normal
    # and shouldn't be crowded out just because it's close to beat 0.
    candidates.sort(key=lambda c: c[2], reverse=True)

    selected: list[tuple[int, str, float]] = []
    budget = max(0, max_cues - 1)  # reserve a slot for Intro
    for idx, label, score in candidates:
        if any(abs(idx - s[0]) < min_distance for s in selected):
            continue
        selected.append((idx, label, score))
        if len(selected) >= budget:
            break

    intro_suppression_distance = max(1, beats_per_bar)
    has_near_start_cue = any(idx < intro_suppression_distance for idx, _, _ in selected)
    if not has_near_start_cue and max_cues > 0:
        if len(selected) >= max_cues:
            selected.sort(key=lambda c: c[2])
            selected.pop(0)  # drop the lowest-scoring real candidate to make room
        selected.append((0, "Intro", max((c[2] for c in candidates), default=1.0) + 1e-6))

    selected.sort(key=lambda c: c[0])
    if selected and selected[-1][1] != "Outro" and selected[-1][0] > n_beats - min_distance:
        idx, _, score = selected[-1]
        selected[-1] = (idx, "Outro", score)

    cues = [
        StructuralCue(
            time_s=float(beat_times[min(idx, len(beat_times) - 1)]),
            beat_index=idx,
            label=label,
            score=score,
        )
        for idx, label, score in selected
    ]

    return StructuralCuePlan(bpm=bpm, beat_times_s=[float(t) for t in beat_times], cues=cues)
