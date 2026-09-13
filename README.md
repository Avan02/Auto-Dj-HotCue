# Auto Dj HotCue

Automatically detects hot cue points in your MP3s — drops, breakdowns,
phrase transitions, or a plain beat-grid — and writes them as Serato DJ hot
cues, so they show up on your hot cue pads without manually dropping them
yourself.

## Two detection modes

### `structural` (default)

Finds where the track's structure actually changes, instead of chopping it
into a uniform grid:

1. Loads each MP3 and runs beat tracking (via [librosa](https://librosa.org))
   to estimate BPM and beat positions, and beat-synchronizes chroma + MFCC
   features (so section boundaries snap to the beat grid).
2. Builds a self-similarity matrix from those features and convolves it
   with a Foote "checkerboard" kernel to get a novelty curve — peaks are
   where the track's timbre/harmony changes most abruptly (section/phrase
   transitions). This is a standard, well-established music-structure-
   analysis technique, not a trained/genre-specific model.
3. Separately tracks beat-synced low-frequency ("bass") energy and overall
   energy. A boundary where bass energy jumps up sharply is labeled a
   likely **Drop**; a sharp drop in overall energy is labeled a likely
   **Breakdown**; anything else that showed up as a novelty peak is labeled
   a **Transition**. The very start of the track is always anchored as
   **Intro**.
4. Greedily picks the highest-scoring boundaries, enforcing a minimum
   spacing (`--min-bars-between-cues`, default 4 bars) so cues don't
   cluster, up to `--max-cues` (Serato max: 8).

This is heuristic signal processing that finds where the *audio itself*
changes character — it works well for typical dance-music arrangements but
can miss or misplace boundaries in unusual ones. Always preview first.

### `phrase`

The older, simpler mode: assumes 4/4 time, treats the first detected beat
as beat 1 of a bar, and places a hot cue every N bars
(`--bars-per-phrase`, default 8) — a uniform grid with no awareness of the
track's actual structure. Useful as a fallback, or for mashup/mixing prep
where you want cues regardless of song structure.

Both modes write cue points into the file's **Serato Markers2** tag, the
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
- **Beat 1 detection is a heuristic**, not true downbeat detection. In
  `phrase` mode, if cues consistently land a beat or two early/late, use
  `--beat-offset` to shift them; `structural` mode snaps to whichever beat
  the boundary actually lands on, so it isn't affected by this.
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

Use `phrase` mode instead of the `structural` default:

```bash
python -m serato_autocue.cli /path/to/folder --mode phrase --apply
```

Useful flags:

| Flag | Meaning |
|---|---|
| `--mode {structural,phrase}` | detection mode (default: `structural`) |
| `--min-bars-between-cues N` | [structural] minimum spacing between cues, in bars (default 4) |
| `--novelty-window-bars N` | [structural] size of the structural-change detection window, in bars (default 4) |
| `--bars-per-phrase N` | [phrase] place a cue every N bars (default 8) |
| `--beat-offset N` | [phrase] shift phrase alignment by N beats |
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
