import json
import zipfile
from pathlib import Path

import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.models import InputItem
from tts_stt_tool.report.audio_set_zip import (
    PackError,
    build_audio_set_zip,
    import_audio_set_zip,
    pack_name,
)
from tts_stt_tool.store.db import ItemStatus, Store

WAV = b"RIFF....WAVEfake-audio-bytes"


def _item(tc, text):
    return InputItem(sheet="S1", tc_id=tc, turn="1", feature="f", priority="P1", region="BAC-HN",
                     speaker="👤 Người dùng", text_raw=text, expected="exp", source_row=5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "tool.db")


@pytest.fixture
def audio_dir(tmp_path):
    d = tmp_path / "audio"
    d.mkdir()
    return d


@pytest.fixture
def set_id(store, audio_dir):
    """TC-1 generated + verified (Đạt, with a WAV); TC-2 still Chờ."""
    sid = store.create_audio_set("bộ 1", "file.xlsx", ["S1"], "Ngọc Huyền",
                                 [_item("TC-1", "bật đèn trần"), _item("TC-2", "tắt đèn")])
    first = store.get_items(sid)[0]
    wav = audio_dir / "aaaa.wav"
    wav.write_bytes(WAV)
    store.record_generated(first["id"], str(wav), 1)
    store.record_verify(first["id"], "bật đèn trần", compare("bật đèn trần", "bật đèn trần"), ItemStatus.PASSED)
    return sid


def _zip(path: Path, manifest, entries: dict[str, bytes] | None = None, raw_manifest: str | None = None):
    with zipfile.ZipFile(path, "w") as z:
        if manifest is not None or raw_manifest is not None:
            z.writestr("manifest.json", raw_manifest if raw_manifest is not None else json.dumps(manifest))
        for name, data in (entries or {}).items():
            z.writestr(name, data)
    return path


def _valid_manifest(items=None):
    return {"format": "tts-stt-audio-set", "version": 1,
            "audio_set": {"name": "X", "source_file": "f.xlsx", "sheets": ["S1"], "voice": None,
                          "voice_trung": None, "voice_nam": None, "created_at": "2026-11-25T10:00:00"},
            "items": items if items is not None else []}


def _row(tc, status, audio=None, **extra):
    return {"tc_id": tc, "status": status, "audio": audio, "text_raw": tc, "text_tts": tc, "enabled": 1,
            "wer": 0.0 if status == "Đạt" else None, "attempts": 1 if audio else 0, "sheet": "S1", **extra}


def test_zip_has_manifest_and_audio_entries(store, set_id, tmp_path):
    out = tmp_path / "out.zip"
    build_audio_set_zip(store, set_id, out)
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist()) == {"manifest.json", "audio/aaaa.wav"}
        manifest = json.loads(z.read("manifest.json"))
        assert z.read("audio/aaaa.wav") == WAV
    assert manifest["format"] == "tts-stt-audio-set" and manifest["version"] == 1
    assert manifest["audio_set"]["name"] == "bộ 1"
    assert [i["audio"] for i in manifest["items"]] == ["audio/aaaa.wav", None]
    assert all("audio_path" not in i for i in manifest["items"])


def test_roundtrip_restores_passed_state_and_audio(store, set_id, audio_dir, tmp_path):
    out = tmp_path / "out.zip"
    build_audio_set_zip(store, set_id, out)
    store.delete_audio_set(set_id)
    (audio_dir / "aaaa.wav").unlink()
    new_dir = tmp_path / "new-audio"
    new_dir.mkdir()

    res = import_audio_set_zip(store, out, new_dir)

    assert res["missing_audio"] == 0
    first, second = store.get_items(res["id"])
    assert first["status"] == ItemStatus.PASSED.value and first["wer"] == 0.0
    assert Path(first["audio_path"]).read_bytes() == WAV
    assert Path(first["audio_path"]).parent == new_dir
    assert second["status"] == ItemStatus.PENDING.value and second["audio_path"] is None


def test_missing_wav_on_disk_exports_as_null_audio(store, set_id, audio_dir, tmp_path):
    (audio_dir / "aaaa.wav").unlink()
    out = tmp_path / "out.zip"
    build_audio_set_zip(store, set_id, out)
    with zipfile.ZipFile(out) as z:
        assert z.namelist() == ["manifest.json"]
        assert [i["audio"] for i in json.loads(z.read("manifest.json"))["items"]] == [None, None]

    res = import_audio_set_zip(store, out, audio_dir)

    assert res["missing_audio"] == 1
    first = store.get_items(res["id"])[0]
    assert first["status"] == ItemStatus.PENDING.value
    assert first["audio_path"] is None and first["wer"] is None and first["attempts"] == 0


def test_missing_entry_in_zip_resets_row_and_counts(store, audio_dir, tmp_path):
    manifest = _valid_manifest([
        _row("TC-1", "Đạt", audio="audio/x.wav"),   # entry not in the zip
        _row("TC-2", "Đạt", audio="audio/ok.wav"),
        _row("TC-3", "Không áp dụng", skip_reason="r", enabled=0),
    ])
    z = _zip(tmp_path / "in.zip", manifest, {"audio/ok.wav": WAV})

    res = import_audio_set_zip(store, z, audio_dir)

    assert res["missing_audio"] == 1
    a, b, c = store.get_items(res["id"])
    assert a["status"] == ItemStatus.PENDING.value and a["wer"] is None and a["audio_path"] is None
    assert b["status"] == ItemStatus.PASSED.value and Path(b["audio_path"]).read_bytes() == WAV
    assert c["status"] == ItemStatus.SKIPPED.value


@pytest.mark.parametrize("entry", ["audio/../evil.wav", "../evil.wav", "/abs.wav", "audio/sub/x.wav", "audio/a b.wav"])
def test_rejects_path_traversal_entries(store, audio_dir, tmp_path, entry):
    manifest = _valid_manifest([_row("TC-1", "Đạt", audio=entry)])
    z = _zip(tmp_path / "in.zip", manifest, {entry: WAV})

    with pytest.raises(PackError):
        import_audio_set_zip(store, z, audio_dir)

    assert store.list_audio_sets() == []
    assert not (tmp_path / "evil.wav").exists() and not (tmp_path.parent / "evil.wav").exists()
    assert list(audio_dir.iterdir()) == []


def test_rejects_manifest_pointing_outside_audio_folder(store, audio_dir, tmp_path):
    manifest = _valid_manifest([_row("TC-1", "Đạt", audio="../evil.wav")])
    z = _zip(tmp_path / "in.zip", manifest)
    with pytest.raises(PackError):
        import_audio_set_zip(store, z, audio_dir)
    assert store.list_audio_sets() == []


def test_rejects_bad_files(store, audio_dir, tmp_path):
    not_zip = tmp_path / "bad.zip"
    not_zip.write_bytes(b"not a zip")
    cases = [
        not_zip,
        _zip(tmp_path / "nomanifest.zip", None, {"audio/a.wav": WAV}),
        _zip(tmp_path / "notjson.zip", None, raw_manifest="{oops"),
        _zip(tmp_path / "list.zip", None, raw_manifest="[]"),
        _zip(tmp_path / "format.zip", {**_valid_manifest(), "format": "other"}),
        _zip(tmp_path / "version.zip", {**_valid_manifest(), "version": 2}),
    ]
    for case in cases:
        with pytest.raises(PackError):
            import_audio_set_zip(store, case, audio_dir)
    assert store.list_audio_sets() == []


def test_import_twice_gives_two_sets_and_one_wav(store, set_id, audio_dir, tmp_path):
    out = tmp_path / "out.zip"
    build_audio_set_zip(store, set_id, out)

    a = import_audio_set_zip(store, out, audio_dir)["id"]
    b = import_audio_set_zip(store, out, audio_dir)["id"]

    assert store.get_audio_set(a)["name"] == "bộ 1 (2)" and store.get_audio_set(b)["name"] == "bộ 1 (3)"
    assert [p.name for p in audio_dir.iterdir()] == ["aaaa.wav"]


def test_pack_name_is_filesystem_safe():
    name = pack_name({"name": 'a/b:c*"d'})
    assert name.endswith(".zip") and not any(ch in name for ch in '/:*"')


def _bad_zip(tmp_path, bad_item=None, audio_set=None, entry_name=None):
    """A zip whose first row is fine (with a WAV) and whose second row / set carries the bad value."""
    manifest = _valid_manifest([_row("TC-1", "Đạt", audio="audio/ok.wav"), {**_row("TC-2", "Chờ"), **(bad_item or {})}])
    manifest["audio_set"].update(audio_set or {})
    entries = {"audio/ok.wav": WAV}
    if entry_name:
        manifest["items"][0]["audio"] = entry_name
        entries = {entry_name: WAV}
    return _zip(tmp_path / "in.zip", manifest, entries)


@pytest.mark.parametrize("bad", [
    {"tc_id": [1, 2]}, {"feature": {"a": 1}}, {"status": ["Đạt"]}, {"status": "foo"}, {"source_row": 2**70},
    {"wer": "high"}, {"enabled": "yes"}, {"form_json": "nope"}, {"form_json": '{"a": 1}'},
    {"ops_json": "{not json"}, {"ops_json": 5},
])
def test_rejects_item_values_the_db_cannot_hold(store, audio_dir, tmp_path, bad):
    z = _bad_zip(tmp_path, bad_item=bad)
    with pytest.raises(PackError):
        import_audio_set_zip(store, z, audio_dir)
    assert store.list_audio_sets() == []
    assert list(audio_dir.iterdir()) == []  # validated before any WAV is copied


@pytest.mark.parametrize("bad", [{"name": ["a"]}, {"sheets": "S1"}, {"sheets": [1]}, {"voice": 5},
                                 {"source_file": {"x": 1}}])
def test_rejects_bad_set_fields(store, audio_dir, tmp_path, bad):
    z = _bad_zip(tmp_path, audio_set=bad)
    with pytest.raises(PackError):
        import_audio_set_zip(store, z, audio_dir)
    assert store.list_audio_sets() == []
    assert list(audio_dir.iterdir()) == []


def test_wav_name_must_match_exactly_not_just_at_line_end(store, audio_dir, tmp_path):
    z = _bad_zip(tmp_path, entry_name="audio/ab.wav\n")
    with pytest.raises(PackError):
        import_audio_set_zip(store, z, audio_dir)
    assert store.list_audio_sets() == [] and list(audio_dir.iterdir()) == []


def test_good_json_columns_round_trip_through_validation(store, audio_dir, tmp_path):
    z = _bad_zip(tmp_path, bad_item={"form_json": json.dumps(["a", "b"]), "ops_json": "[]", "wer": 0.25,
                                     "source_row": 7, "status": "Lỗi", "error": "boom"})
    res = import_audio_set_zip(store, z, audio_dir)
    row = store.export_audio_set(res["id"])["items"][1]
    assert row["form_json"] == json.dumps(["a", "b"]) and row["status"] == "Lỗi" and row["wer"] == 0.25
