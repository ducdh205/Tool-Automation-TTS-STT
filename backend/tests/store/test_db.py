import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.models import InputItem
from tts_stt_tool.store.db import ItemStatus, Store

USER = "👤 Người dùng"


def _item(tc, text, speaker=USER, sheet="S1"):
    return InputItem(sheet=sheet, tc_id=tc, turn="1", feature="f", priority="P1", region="BAC-HN",
                     speaker=speaker, text_raw=text, expected="exp", source_row=5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "tool.db")


@pytest.fixture
def set_id(store):
    items = [
        _item("TC-1", "Hey Vita, bật đèn trần"),
        _item("TC-2", "Xe chuyển số D", speaker="🚗 Hệ thống (sự kiện)"),
        _item("TC-3", "Hey Vita"),
    ]
    return store.create_audio_set("bộ 1", "file.xlsx", ["S1"], "Ngọc Huyền", items)


def test_create_classifies_items(store, set_id):
    assert store.summary(set_id) == {ItemStatus.PENDING.value: 1, ItemStatus.SKIPPED.value: 2}
    items = store.get_items(set_id)
    assert [i["text_tts"] for i in items] == ["bật đèn trần", None, None]
    assert items[1]["skip_reason"] == "Dòng hệ thống"
    assert items[1]["enabled"] == 0
    assert items[0]["text_raw"] == "Hey Vita, bật đèn trần"


def test_get_items_filter_by_status(store, set_id):
    assert len(store.get_items(set_id, ItemStatus.SKIPPED)) == 2


def test_list_audio_sets(store, set_id):
    sets = store.list_audio_sets()
    assert sets[0]["id"] == set_id
    assert sets[0]["name"] == "bộ 1"
    assert sets[0]["sheets"] == ["S1"]
    assert sets[0]["voice"] == "Ngọc Huyền"


def test_set_item_text_reenables_skipped(store, set_id):
    skipped = store.get_items(set_id, ItemStatus.SKIPPED)[0]
    store.set_item_text(skipped["id"], "Bật đèn")
    row = store.get_item(skipped["id"])
    assert row["status"] == ItemStatus.PENDING.value
    assert row["enabled"] == 1
    assert row["skip_reason"] is None
    assert row["text_tts"] == "Bật đèn"


def test_set_item_text_resets_audio_and_verify(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    store.record_generated(item["id"], "a.wav", 1)
    store.record_verify(item["id"], "bật đèn trần", compare("bật đèn trần", "bật đèn trần"), ItemStatus.PASSED)
    store.set_item_text(item["id"], "bật đèn trần nhé")
    row = store.get_item(item["id"])
    assert row["status"] == ItemStatus.PENDING.value
    assert row["audio_path"] is None
    assert row["ref_text"] is None
    assert row["wer"] is None
    assert row["attempts"] == 0


def test_record_verify_saves_scores(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    store.record_generated(item["id"], "a.wav", 2)
    r = compare("mua sữa", "mua sửa")
    store.record_verify(item["id"], "mua sửa", r, ItemStatus.AUDIO_FAILED)
    row = store.get_item(item["id"])
    assert row["wer"] == 0.5
    assert row["ref_text"] == "mua sửa"
    assert row["attempts"] == 2
    assert {"op": "sub", "ref": "sữa", "hyp": "sửa"} in row["ops"]
    assert row["status"] == ItemStatus.AUDIO_FAILED.value


def test_generate_queue_retries_errors_and_skips_disabled(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    assert [i["id"] for i in store.items_for_generate(set_id, None)] == [item["id"]]
    store.record_error(item["id"], "boom")
    assert store.get_item(item["id"])["status"] == ItemStatus.ERROR.value
    assert len(store.items_for_generate(set_id, None)) == 1  # errors are retried
    store.set_enabled(item["id"], False)
    assert store.items_for_generate(set_id, None) == []


def test_persists_across_instances(tmp_path, set_id, store):
    again = Store(tmp_path / "tool.db")
    assert again.summary(set_id) == store.summary(set_id)


@pytest.fixture
def staged(store):
    """Three items: A no audio, B generated, C verified as audio failed."""
    set_id = store.create_audio_set("b", "f.xlsx", ["S1"], "v",
                                    [_item("A", "bật đèn"), _item("B", "tắt đèn"), _item("C", "mở cốp")])
    a, b, c = (i["id"] for i in store.get_items(set_id))
    store.record_generated(b, "b.wav", 1)
    store.record_generated(c, "c.wav", 1)
    store.record_verify(c, "mở cố", compare("mở cốp", "mở cố"), ItemStatus.AUDIO_FAILED)
    return set_id, (a, b, c)


def _ids(rows):
    return [r["id"] for r in rows]


def test_selection_queries(store, staged):
    set_id, (a, b, c) = staged
    assert _ids(store.items_for_generate(set_id, None)) == [a]
    assert _ids(store.items_for_generate(set_id, [b, c])) == []
    assert _ids(store.items_for_verify(set_id, None)) == [b]
    assert _ids(store.items_for_verify(set_id, [a, c])) == [c]
    assert _ids(store.items_for_regenerate(set_id, None)) == [c]
    assert _ids(store.items_for_regenerate(set_id, [b])) == [b]


def test_selection_ignores_other_sets_and_disabled(store, staged):
    set_id, (a, b, c) = staged
    other = store.create_audio_set("o", "f.xlsx", ["S1"], "v", [_item("Z", "đóng cốp")])
    z = store.get_items(other)[0]["id"]
    assert _ids(store.items_for_generate(set_id, [a, z])) == [a]
    store.set_enabled(a, False)
    assert _ids(store.items_for_generate(set_id, None)) == []


def test_error_items_split_by_audio(store, staged):
    set_id, (a, b, c) = staged
    store.record_error(a, "tts hỏng")
    store.record_error(b, "stt hỏng")
    assert _ids(store.items_for_generate(set_id, None)) == [a]
    assert _ids(store.items_for_verify(set_id, None)) == [b]


def test_record_generated_clears_verify(store, staged):
    _, (_, _, c) = staged
    store.record_generated(c, "c2.wav", 2)
    it = store.get_item(c)
    assert it["status"] == ItemStatus.GENERATED.value
    assert it["ref_text"] is None and it["wer"] is None and it["cer"] is None and it["ops"] == []
    assert it["attempts"] == 2


def test_migrates_old_schema(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, audio_set_id INTEGER NOT NULL, sheet TEXT, tc_id TEXT,"
        " turn TEXT, feature TEXT, priority TEXT, region TEXT, speaker TEXT, expected TEXT, source_row INTEGER,"
        " text_raw TEXT, text_tts TEXT, skip_reason TEXT, enabled INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL,"
        " audio_path TEXT, attempts INTEGER NOT NULL DEFAULT 0, ref_text TEXT, wer REAL, cer REAL, ops_json TEXT,"
        " error TEXT, updated_at TEXT);"
        "CREATE TABLE app_results (id INTEGER PRIMARY KEY, app_run_id INTEGER NOT NULL, item_id INTEGER NOT NULL,"
        " status TEXT NOT NULL, app_text TEXT, wer REAL, cer REAL, ops_json TEXT, error TEXT, log TEXT,"
        " updated_at TEXT);"
    )
    conn.close()
    Store(path)
    conn = sqlite3.connect(path)
    assert "form_json" in {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert "screenshot_path" in {r[1] for r in conn.execute("PRAGMA table_info(app_results)")}
    conn.close()


def test_delete_audio_set_cascades_and_reports_files(store, set_id):
    item = store.items_for_generate(set_id, None)[0]
    store.record_generated(item["id"], "/a/only-mine.wav", 1)
    run_id = store.create_app_run(set_id, "SER", None, "p", None)
    other = store.create_audio_set("bộ 2", "file.xlsx", ["S1"], None, [_item("TC-9", "Hey Vita, bật đèn")])

    gone = store.delete_audio_set(set_id)

    assert gone == {"run_ids": [run_id], "audio_paths": ["/a/only-mine.wav"]}
    assert store.get_audio_set(set_id) is None
    assert store.get_items(set_id) == []
    assert store.get_app_run(run_id) is None
    assert [s["id"] for s in store.list_audio_sets()] == [other]


def test_delete_audio_set_keeps_wav_shared_with_another_set(store, set_id):
    other = store.create_audio_set("bộ 2", "file.xlsx", ["S1"], None, [_item("TC-9", "Hey Vita, bật đèn trần")])
    for sid in (set_id, other):
        it = store.items_for_generate(sid, None)[0]
        store.record_generated(it["id"], "/a/shared.wav", 1)

    assert store.delete_audio_set(set_id)["audio_paths"] == []


def test_delete_unknown_audio_set_returns_none(store):
    assert store.delete_audio_set(999) is None


def test_delete_all_audio_sets_cascades(store, set_id):
    run_id = store.create_app_run(set_id, "SER", None, "p", None)
    store.create_audio_set("bộ 2", "file.xlsx", ["S1"], None, [_item("TC-9", "Hey Vita, bật đèn")])

    assert store.delete_all_audio_sets() == 2
    assert store.list_audio_sets() == []
    assert store.get_items(set_id) == []
    assert store.get_app_run(run_id) is None
    assert store.delete_all_audio_sets() == 0


def _roundtrip(store, set_id):
    data = store.export_audio_set(set_id)
    return store.import_audio_set(data["audio_set"], data["items"])


def test_export_audio_set_roundtrip_keeps_state(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    store.record_generated(item["id"], "/a/x.wav", 2)
    store.record_verify(item["id"], "bật đèn trần", compare("bật đèn trần", "bật đèn trần"), ItemStatus.PASSED)

    new_id = _roundtrip(store, set_id)

    assert new_id != set_id
    cols = ("tc_id", "status", "audio_path", "wer", "cer", "ref_text", "attempts", "ops", "enabled",
            "skip_reason", "text_raw", "text_tts", "sheet", "region", "source_row")
    old = [{c: i[c] for c in cols} for i in store.get_items(set_id)]
    new = [{c: i[c] for c in cols} for i in store.get_items(new_id)]
    assert new == old
    assert any(i["status"] == ItemStatus.PASSED.value and i["audio_path"] == "/a/x.wav" for i in new)
    meta = store.get_audio_set(new_id)
    assert meta["sheets"] == ["S1"] and meta["voice"] == "Ngọc Huyền" and meta["source_file"] == "file.xlsx"


def test_import_audio_set_makes_name_unique(store, set_id):
    data = store.export_audio_set(set_id)
    a = store.import_audio_set(data["audio_set"], data["items"])
    b = store.import_audio_set(data["audio_set"], data["items"])
    assert store.get_audio_set(a)["name"] == "bộ 1 (2)"
    assert store.get_audio_set(b)["name"] == "bộ 1 (3)"
    assert store.get_audio_set(set_id)["name"] == "bộ 1"


def test_export_audio_set_keeps_legacy_form_json(store, set_id):
    """Sets made before the 36-column form was dropped still carry form_json: it must survive the trip."""
    first = store.get_items(set_id)[0]["id"]
    with store._conn() as c:
        c.execute("UPDATE items SET form_json=? WHERE id=?", ('["a", "b"]', first))

    new_id = _roundtrip(store, set_id)

    assert [i["form_json"] for i in store.export_audio_set(new_id)["items"]] ==         [i["form_json"] for i in store.export_audio_set(set_id)["items"]]
    assert store.export_audio_set(new_id)["items"][0]["form_json"] == '["a", "b"]'


def test_export_unknown_audio_set_returns_none(store):
    assert store.export_audio_set(999) is None


def test_import_does_not_copy_app_runs(store, set_id):
    store.create_app_run(set_id, "SER", None, "p", None)
    new_id = _roundtrip(store, set_id)
    assert store.list_app_runs(new_id) == []
    assert len(store.list_app_runs(set_id)) == 1

def test_reset_progress_keeps_rows_and_clears_results(store, set_id):
    before = store.get_items(set_id)
    item = store.items_for_generate(set_id, None)[0]
    store.record_generated(item["id"], "/a/x.wav", 2)
    run_id = store.create_app_run(set_id, "SER", None, "p", None)

    store.reset_progress()

    after = store.get_items(set_id)
    assert [i["id"] for i in after] == [i["id"] for i in before]
    assert [i["status"] for i in after] == [i["status"] for i in before]  # "Không áp dụng" stays
    assert all(i["audio_path"] is None and i["error"] is None and i["attempts"] == 0 for i in after)
    assert store.get_app_run(run_id) is None


def test_set_source_roundtrip(store, set_id):
    s = store.get_audio_set(set_id)
    assert s["source_path"] is None and s["header_row"] is None
    store.set_source(set_id, "x/a.xlsx", 3)
    s = store.get_audio_set(set_id)
    assert s["source_path"] == "x/a.xlsx" and s["header_row"] == 3


def test_old_db_gets_source_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE audio_sets (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_file TEXT NOT NULL,"
        " sheets_json TEXT NOT NULL, voice TEXT, created_at TEXT NOT NULL);"
        "INSERT INTO audio_sets(name, source_file, sheets_json, created_at) VALUES ('a', 'a.xlsx', '[]', 'x');"
    )
    conn.close()
    store = Store(path)
    s = store.get_audio_set(1)
    assert s["source_path"] is None and s["header_row"] is None
    store.set_source(1, "a.xlsx", 2)
    assert store.get_audio_set(1)["header_row"] == 2
