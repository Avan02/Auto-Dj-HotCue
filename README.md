# Auto Dj HotCue

Automatically detects beat-grid-aligned phrase points in your MP3s and
writes them as Serato DJ hot cues, so they show up on your hot cue pads
without manually dropping them yourself.

## How it works

1. Loads each MP3 and runs beat tracking (via [librosa](https://librosa.org))
   to estimate BPM and beat positions.
2. Assumes 4/4 time and treats the first detected beat as beat 1 of a bar,
   then places a hot cue every N bars (`--bars-per-phrase`, default 8) —
   this lines cues up with typical 8/16/32-bar phrase structure in most
   dance music.
3. Writes those cue points into the file's **Serato Markers2** tag, the
   same ID3 GEOB frame Serato itself uses to store hot cues.

## ⚠️ Important caveats before you run this on your library

- **The Serato tag format is reverse-engineered, not official.** It's the
  same community-documented format used by other cross-compatible tools
  (see [Holzhaus/serato-tags](https://github.com/Holzhaus/serato-tags)),
  but Serato could change it, and edge cases may not be covered.
- **This tool only writes `CUE` entries and preserves anything else already
  in the tag** (saved loops, track color, etc.) — but it does not touch the
  older `Serato Markers_` tag, so very old Serato versions (pre-2.x) may not
  see the cues.
- **Beat 1 detection is a heuristic**, not true downbeat detection. If your
  cues consistently land a beat or two early/late, use `--beat-offset` to
  shift them.
- **By default, a backup copy of every file is made** before it's modified
  (into `.serato-autocue-backup/` next to the original). Don't disable this
  (`--no-backup`) unless you have your own backup strategy.
- Always run without `--apply` first (the default) to preview what would
  happen, and test on a copy of a few tracks before pointing this at your
  whole library.

## Install

```bash
pip install -r requirements.txt
```

MP3 decoding needs the `ffmpeg` binary on your PATH:

```bash
brew install ffmpeg
```

## Usage

Preview only (no files are modified):

```bash
python -m serato_autocue.cli /path/to/track-or-folder
```

Actually write the hot cues:

```bash
python -m serato_autocue.cli /path/to/folder --apply
```

Useful flags:

| Flag | Meaning |
|---|---|
| `--bars-per-phrase N` | place a cue every N bars (default 8) |
| `--beat-offset N` | shift phrase alignment by N beats |
| `--max-cues N` | cap the number of cues written (Serato max: 8) |
| `--force` | overwrite files that already have hot cues (default: skip them) |
| `--no-backup` | skip the pre-write backup copy (not recommended) |
| `--backup-dir DIR` | write backups somewhere other than `.serato-autocue-backup/` |

## Running tests

```bash
pytest
```

The tests cover the Markers2 binary encode/decode round-trip. They can't
verify that real Serato accepts the output (no Serato install in CI) — that
part is on you, on a backup copy, before trusting this on your library.
