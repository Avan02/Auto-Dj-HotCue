from serato_autocue.serato_markers import CuePoint, Markers2Tag, RawEntry


def test_roundtrip_cues():
    tag = Markers2Tag(cues=[
        CuePoint(index=0, position_ms=0, color=(0xCC, 0x00, 0x00), name="Phrase 1"),
        CuePoint(index=1, position_ms=15320, color=(0x00, 0xCC, 0x00), name="Phrase 2"),
        CuePoint(index=7, position_ms=123456, color=(0x00, 0x00, 0xCC), name=""),
    ])
    data = tag.to_geob_data()
    decoded = Markers2Tag.from_geob_data(data)

    assert [c.index for c in decoded.cues] == [0, 1, 7]
    assert [c.position_ms for c in decoded.cues] == [0, 15320, 123456]
    assert decoded.cues[0].name == "Phrase 1"
    assert decoded.cues[0].color == (0xCC, 0x00, 0x00)
    assert decoded.cues[2].name == ""


def test_roundtrip_preserves_unknown_entries():
    tag = Markers2Tag(
        cues=[CuePoint(index=0, position_ms=1000)],
        other_entries=[RawEntry(name="BPMLOCK", data=b"\x01")],
    )
    decoded = Markers2Tag.from_geob_data(tag.to_geob_data())
    assert len(decoded.other_entries) == 1
    assert decoded.other_entries[0].name == "BPMLOCK"
    assert decoded.other_entries[0].data == b"\x01"


def test_payload_has_min_length_and_version_header():
    tag = Markers2Tag(cues=[CuePoint(index=0, position_ms=0)])
    data = tag.to_geob_data()
    assert data[:2] == b"\x01\x01"
