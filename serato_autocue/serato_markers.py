"""Read/write the "Serato Markers2" GEOB tag embedded in MP3 ID3 frames.

This is a reverse-engineered, community-documented binary format (the same
one used by cross-compatible tools such as Mixxx) -- it is not an official
Serato format. See: https://github.com/Holzhaus/serato-tags

Layout of the *decoded* payload (i.e. after stripping the 2-byte version
header and base64-decoding):

    entry := name (null-terminated ASCII) + length (uint32 BE) + data
    payload := entry* + b"\x00" (terminator) [+ zero padding to >= 470 bytes]

Only the "CUE" entry type is written/parsed here since that's all a hot-cue
tool needs; unrecognized entries found in an existing tag are preserved
verbatim so we don't clobber saved loops, track color, etc.
"""
from __future__ import annotations

import base64
import struct
from dataclasses import dataclass, field

GEOB_DESCRIPTION = "Serato Markers2"
_VERSION_HEADER = b"\x01\x01"
_MIN_PAYLOAD_LEN = 470
_LINE_LEN = 72


@dataclass
class CuePoint:
    index: int  # hot cue slot, 0-7
    position_ms: int
    color: tuple[int, int, int] = (0xCC, 0x00, 0x00)
    name: str = ""

    def encode(self) -> bytes:
        body = bytearray()
        body += b"\x00"  # reserved
        body += struct.pack(">B", self.index)
        body += struct.pack(">I", self.position_ms)
        body += b"\x00"  # reserved
        body += bytes(self.color)
        body += b"\x00\x00"  # reserved
        body += self.name.encode("utf-8") + b"\x00"
        return bytes(body)

    @classmethod
    def decode(cls, data: bytes) -> "CuePoint":
        index = data[1]
        position_ms = struct.unpack(">I", data[2:6])[0]
        color = (data[7], data[8], data[9])
        name = data[12:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return cls(index=index, position_ms=position_ms, color=color, name=name)


@dataclass
class RawEntry:
    """An entry type we don't interpret -- kept as opaque bytes on rewrite."""
    name: str
    data: bytes


@dataclass
class Markers2Tag:
    cues: list[CuePoint] = field(default_factory=list)
    other_entries: list[RawEntry] = field(default_factory=list)

    def to_geob_data(self) -> bytes:
        payload = bytearray()
        for cue in sorted(self.cues, key=lambda c: c.index):
            body = cue.encode()
            payload += b"CUE\x00" + struct.pack(">I", len(body)) + body
        for entry in self.other_entries:
            payload += entry.name.encode("ascii") + b"\x00"
            payload += struct.pack(">I", len(entry.data)) + entry.data
        payload += b"\x00"  # terminator
        if len(payload) < _MIN_PAYLOAD_LEN:
            payload += b"\x00" * (_MIN_PAYLOAD_LEN - len(payload))

        b64 = base64.b64encode(bytes(payload))
        lines = [b64[i:i + _LINE_LEN] for i in range(0, len(b64), _LINE_LEN)]
        return _VERSION_HEADER + b"\n".join(lines)

    @classmethod
    def from_geob_data(cls, data: bytes) -> "Markers2Tag":
        if data[:2] != _VERSION_HEADER:
            raise ValueError(f"unexpected Markers2 version header: {data[:2]!r}")
        b64 = data[2:].replace(b"\n", b"")
        payload = base64.b64decode(b64)

        cues: list[CuePoint] = []
        other: list[RawEntry] = []
        pos = 0
        while pos < len(payload):
            name_end = payload.index(b"\x00", pos)
            name = payload[pos:name_end].decode("ascii")
            if name == "":
                break  # terminator reached
            len_start = name_end + 1
            (entry_len,) = struct.unpack(">I", payload[len_start:len_start + 4])
            data_start = len_start + 4
            entry_data = payload[data_start:data_start + entry_len]
            if name == "CUE":
                cues.append(CuePoint.decode(entry_data))
            else:
                other.append(RawEntry(name=name, data=entry_data))
            pos = data_start + entry_len

        return cls(cues=cues, other_entries=other)
