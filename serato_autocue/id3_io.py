"""Read/write the Serato Markers2 GEOB frame on an actual MP3 file."""
from __future__ import annotations

import shutil
from pathlib import Path

from mutagen.id3 import GEOB, ID3, ID3NoHeaderError

from .serato_markers import GEOB_DESCRIPTION, Markers2Tag


def read_markers2(path: Path) -> Markers2Tag | None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return None
    for frame in tags.getall("GEOB"):
        if frame.desc == GEOB_DESCRIPTION:
            return Markers2Tag.from_geob_data(frame.data)
    return None


def write_markers2(path: Path, tag: Markers2Tag, *, backup_dir: Path | None) -> Path | None:
    """Write `tag` into `path`'s ID3 GEOB frame. Returns the backup file path
    (or None if backup_dir was None), and never touches the file until the
    backup has been written successfully.
    """
    backup_path = None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / path.name
        if backup_path.exists():
            raise FileExistsError(
                f"backup already exists, refusing to overwrite: {backup_path}"
            )
        shutil.copy2(path, backup_path)

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    for frame in tags.getall("GEOB"):
        if frame.desc == GEOB_DESCRIPTION:
            tags.remove(frame)

    tags.add(
        GEOB(
            encoding=0,
            mime="application/octet-stream",
            filename="",
            desc=GEOB_DESCRIPTION,
            data=tag.to_geob_data(),
        )
    )
    tags.save(path, v2_version=3)
    return backup_path
