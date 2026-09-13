from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .id3_io import read_markers2, write_markers2
from .phrase_cues import detect_phrase_cues
from .serato_markers import CuePoint, Markers2Tag
from .structure import detect_structural_cues

CUE_COLORS = [
    (0xCC, 0x00, 0x00),
    (0xCC, 0x88, 0x00),
    (0xCC, 0xCC, 0x00),
    (0x00, 0xCC, 0x00),
    (0x00, 0xCC, 0xCC),
    (0x00, 0x00, 0xCC),
    (0x88, 0x00, 0xCC),
    (0xCC, 0x00, 0x88),
]

LABEL_COLORS = {
    "Intro": (0x00, 0xCC, 0x00),
    "Drop": (0xCC, 0x00, 0x00),
    "Breakdown": (0x00, 0x88, 0xCC),
    "Transition": (0xCC, 0xCC, 0x00),
    "Outro": (0x88, 0x00, 0xCC),
}


def find_mp3s(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.mp3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serato-autocue",
        description="Detect hot cue points and write them into Serato MP3 tags.",
    )
    parser.add_argument("path", type=Path, help="MP3 file or a folder to scan recursively")
    parser.add_argument(
        "--mode", choices=["structural", "phrase"], default="structural",
        help=(
            "structural (default): place cues at detected drops/breakdowns/transitions. "
            "phrase: place a cue every --bars-per-phrase bars, uniformly."
        ),
    )
    parser.add_argument(
        "--bars-per-phrase", type=int, default=8,
        help="[phrase mode] place a cue every N bars (default: 8)",
    )
    parser.add_argument(
        "--beat-offset", type=int, default=0,
        help="[phrase mode] shift phrase alignment by this many beats if downbeats land off (default: 0)",
    )
    parser.add_argument(
        "--min-bars-between-cues", type=int, default=4,
        help="[structural mode] minimum spacing between cues, in bars (default: 4)",
    )
    parser.add_argument(
        "--novelty-window-bars", type=int, default=4,
        help="[structural mode] size of the structural-change detection window, in bars (default: 4)",
    )
    parser.add_argument(
        "--max-cues", type=int, default=8,
        help="Serato supports 8 hot cue pads (default: 8, max: 8)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually write tags. Without this flag, only a report is printed.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite existing CUE entries instead of skipping files that already have them",
    )
    parser.add_argument(
        "--backup-dir", type=Path, default=None,
        help="directory to copy original files into before writing (default: <folder>/.serato-autocue-backup next to each file)",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="DANGEROUS: skip making a backup copy before writing tags",
    )
    return parser


def _phrase_cues(y, sr, args) -> list[CuePoint]:
    plan = detect_phrase_cues(
        y, sr,
        bars_per_phrase=args.bars_per_phrase,
        beat_offset=args.beat_offset,
        max_cues=args.max_cues,
    )
    if not plan.cue_times_s:
        return []
    print(f"  bpm ~= {plan.bpm:.1f}, {len(plan.cue_times_s)} phrase cue(s):")
    cues = []
    for i, t in enumerate(plan.cue_times_s):
        mins, secs = divmod(t, 60)
        print(f"    cue {i}: {int(mins):02d}:{secs:05.2f}  Phrase {i + 1}")
        cues.append(CuePoint(
            index=i,
            position_ms=int(round(t * 1000)),
            color=CUE_COLORS[i % len(CUE_COLORS)],
            name=f"Phrase {i + 1}",
        ))
    return cues


def _structural_cues(y, sr, args) -> list[CuePoint]:
    plan = detect_structural_cues(
        y, sr,
        min_bars_between_cues=args.min_bars_between_cues,
        novelty_window_bars=args.novelty_window_bars,
        max_cues=args.max_cues,
    )
    if not plan.cues:
        return []
    print(f"  bpm ~= {plan.bpm:.1f}, {len(plan.cues)} structural cue(s):")
    cues = []
    for i, c in enumerate(plan.cues):
        mins, secs = divmod(c.time_s, 60)
        print(f"    cue {i}: {int(mins):02d}:{secs:05.2f}  {c.label} (score {c.score:.2f})")
        cues.append(CuePoint(
            index=i,
            position_ms=int(round(c.time_s * 1000)),
            color=LABEL_COLORS.get(c.label, CUE_COLORS[i % len(CUE_COLORS)]),
            name=c.label,
        ))
    return cues


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.max_cues > 8:
        print("error: Serato only supports 8 hot cue pads (--max-cues <= 8)", file=sys.stderr)
        return 2

    files = find_mp3s(args.path)
    if not files:
        print(f"no .mp3 files found under {args.path}", file=sys.stderr)
        return 1

    try:
        import librosa
    except ImportError:
        print(
            "error: librosa is required for audio analysis.\n"
            "Install dependencies with: pip install -r requirements.txt\n"
            "(MP3 decoding also needs the ffmpeg binary on your PATH.)",
            file=sys.stderr,
        )
        return 2

    exit_code = 0
    for path in files:
        print(f"\n{path}")
        existing = read_markers2(path)
        if existing and existing.cues and not args.force:
            print(f"  already has {len(existing.cues)} hot cue(s) — skipping (use --force to overwrite)")
            continue

        try:
            y, sr = librosa.load(path, sr=None, mono=True)
        except Exception as exc:  # noqa: BLE001 - report and continue with other files
            print(f"  failed to decode audio: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if args.mode == "phrase":
            cues = _phrase_cues(y, sr, args)
        else:
            cues = _structural_cues(y, sr, args)

        if not cues:
            print("  no cues detected, skipping")
            continue

        if not args.apply:
            continue

        tag = Markers2Tag(cues=cues, other_entries=existing.other_entries if existing else [])
        backup_dir = None
        if not args.no_backup:
            backup_dir = args.backup_dir or (path.parent / ".serato-autocue-backup")
        try:
            backup_path = write_markers2(path, tag, backup_dir=backup_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"  failed to write tags: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if backup_path:
            print(f"  backed up original to {backup_path}")
        print("  wrote hot cues")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
