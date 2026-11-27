import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.models import InputItem
from tts_stt_tool.store.db import AppStatus, ItemStatus, Store


def _item(tc, text):
    return InputItem(sheet="S", tc_id=tc, turn="1", feature="f", priority="P1", region="BAC-HN",
                     speaker="👤 Người dùng", text_raw=text, expected="", source_row=5)


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "v", [_item("1", "bật đèn"), _item("2", "tắt đèn"), _item("3", "mở cốp")])
    rows = store.get_items(set_id)
    for r, st in zip(rows, [ItemStatus.PASSED, ItemStatus.PASSED, ItemStatus.AUDIO_FAILED], strict=True):
        store.record_generated(r["id"], f"{r['id']}.wav", 1)
        store.record_verify(r["id"], r["text_tts"], compare(r["text_tts"], r["text_tts"]), st)
    return store, set_id


def test_run_contains_every_item_with_audio(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "22120RN86G", "Vita Work (dev)", "1.2.3")
    results = store.app_results(run_id)
    assert [r["text_tts"] for r in results] == ["bật đèn", "tắt đèn", "mở cốp"]
    assert [r["verify"] for r in results] == ["Đạt", "Đạt", "Không đạt"]
    assert all(r["status"] == AppStatus.PENDING.value for r in results)
    assert results[0]["audio_path"].endswith(".wav")
    assert results[0]["tc_id"] == "1"


def test_record_and_summary(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    a, b, c = store.app_results(run_id)
    store.record_app_result(a["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "log a")
    store.record_app_result(b["id"], AppStatus.OP_ERROR, None, None, "Không thấy nút mic", "log b")
    assert store.app_summary(run_id) == {AppStatus.PASSED.value: 1, AppStatus.OP_ERROR.value: 1,
                                         AppStatus.PENDING.value: 1}
    rows = {r["id"]: r for r in store.app_results(run_id)}
    assert rows[a["id"]]["wer"] == 0 and rows[a["id"]]["app_text"] == "bật đèn"
    assert rows[b["id"]]["error"] == "Không thấy nút mic"
    assert [r["id"] for r in store.pending_for_block2(run_id)] == [b["id"], c["id"]]


def test_runs_are_independent_and_listed(env):
    store, set_id = env
    r1 = store.create_app_run(set_id, "A", "m", "p", None)
    r2 = store.create_app_run(set_id, "B", "m", "p", None)
    first = store.app_results(r1)[0]
    store.record_app_result(first["id"], AppStatus.FAILED, "bật đen", compare("bật đèn", "bật đen"), None, "")
    assert store.app_summary(r2) == {AppStatus.PENDING.value: 3}
    runs = store.list_app_runs(set_id)
    assert [r["id"] for r in runs] == [r2, r1]
    assert runs[1]["summary"] == {AppStatus.FAILED.value: 1, AppStatus.PENDING.value: 2}
    assert store.get_app_run(r1)["serial"] == "A"


def test_results_keep_text_and_audio_snapshot(env):
    """Review2 #6: editing a sentence after the run was created must not change what was tested."""
    store, set_id = env
    run_id = store.create_app_run(set_id, "S", "m", "p", None)
    row = store.app_results(run_id)[0]
    store.set_item_text(row["item_id"], "câu đã sửa")
    again = store.app_results(run_id)[0]
    assert again["text_tts"] == "bật đèn"
    assert again["audio_path"] == row["audio_path"] and again["audio_path"]
    assert [r["id"] for r in store.pending_for_block2(run_id)][0] == row["id"]


def test_create_app_run_with_item_ids(env):
    store, set_id = env
    ids = [i["id"] for i in store.get_items(set_id)]
    run_id = store.create_app_run(set_id, "SER", None, "p", None, item_ids=[ids[1], ids[2]])
    assert [r["item_id"] for r in store.app_results(run_id)] == [ids[1], ids[2]]  # audio failed still runs


def test_unverified_and_disabled_rows(tmp_path):
    store = Store(tmp_path / "t.db")
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "v", [_item("1", "a"), _item("2", "b"), _item("3", "c")])
    a, b, c = store.get_items(set_id)
    store.record_generated(a["id"], "a.wav", 1)  # generated, not verified yet
    store.record_generated(b["id"], "b.wav", 1)
    store.set_enabled(b["id"], False)  # disabled rows stay out
    assert store.get_item(a["id"])["verify"] == "Chưa" and c["verify"] == "Chưa"
    assert store.count_with_audio(set_id) == 1
    run_id = store.create_app_run(set_id, "SER", None, "p", None)
    assert [(r["item_id"], r["verify"]) for r in store.app_results(run_id)] == [(a["id"], "Chưa")]
    # the verify column follows the item, so a later verify shows up on the existing run
    store.record_verify(a["id"], "a", compare("a", "a"), ItemStatus.PASSED)
    assert store.app_results(run_id)[0]["verify"] == "Đạt"


def test_screenshot_path_and_source_row(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER", None, "p", None)
    rid = store.app_results(run_id)[0]["id"]
    store.record_app_result(rid, AppStatus.FAILED, "x", None, None, "log", screenshot_path="C:/shots/1.png")
    row = store.get_app_result(rid)
    assert row["screenshot_path"] == "C:/shots/1.png"
    assert row["source_row"] == 5 and row["speaker"] == "👤 Người dùng" and row["region"] == "BAC-HN"


def test_rerun_keeps_other_results_and_archives_the_old_one(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    a, b, c = store.app_results(run_id)
    store.record_app_result(a["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "log a")
    store.record_app_result(b["id"], AppStatus.FAILED, "tắt đen", compare("tắt đèn", "tắt đen"), None, "log b",
                            screenshot_path="b.png")
    store.record_app_result(c["id"], AppStatus.PASSED, "mở cốp", compare("mở cốp", "mở cốp"), None, "log c")

    assert store.rerun_app_results(run_id, [b["item_id"]]) == 1

    rows = {r["item_id"]: r for r in store.app_results(run_id)}
    assert rows[a["item_id"]]["status"] == AppStatus.PASSED.value and rows[a["item_id"]]["history"] == []
    again = rows[b["item_id"]]
    assert again["id"] == b["id"]  # same row: the run stays complete
    assert (again["status"], again["app_text"], again["wer"], again["log"], again["screenshot_path"]) == (
        AppStatus.PENDING.value, None, None, None, None)
    assert [(h["status"], h["app_text"], h["screenshot_path"]) for h in again["history"]] == [
        (AppStatus.FAILED.value, "tắt đen", "b.png")]
    assert [r["id"] for r in store.pending_for_block2(run_id)] == [b["id"]]
    assert store.app_summary(run_id) == {AppStatus.PASSED.value: 2, AppStatus.PENDING.value: 1}


def test_rerun_history_is_newest_first(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    a = store.app_results(run_id)[0]
    for heard in ("bật đen", "bậc đèn"):
        store.record_app_result(a["id"], AppStatus.FAILED, heard, compare("bật đèn", heard), None, "")
        store.rerun_app_results(run_id, [a["item_id"]])
    assert [h["app_text"] for h in store.get_app_result(a["id"])["history"]] == ["bậc đèn", "bật đen"]


def test_rerun_of_pending_row_archives_nothing(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    a = store.app_results(run_id)[0]
    assert store.rerun_app_results(run_id, [a["item_id"]]) == 1
    assert store.get_app_result(a["id"])["history"] == []


def test_rerun_adds_items_missing_from_the_run_and_takes_current_audio(env):
    store, set_id = env
    first = store.get_items(set_id)[0]
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None, item_ids=[first["id"]])
    a = store.app_results(run_id)[0]
    store.record_app_result(a["id"], AppStatus.FAILED, "x", compare("bật đèn", "x"), None, "")
    store.record_generated(first["id"], "new.wav", 2)  # audio regenerated in step 1 since the run
    other = store.get_items(set_id)[1]

    assert store.rerun_app_results(run_id, [first["id"], other["id"]]) == 2

    rows = {r["item_id"]: r for r in store.app_results(run_id)}
    assert set(rows) == {first["id"], other["id"]}
    assert rows[first["id"]]["audio_path"] == "new.wav"
    assert rows[first["id"]]["history"][0]["audio_path"].endswith(f"{first['id']}.wav")
    assert rows[other["id"]]["status"] == AppStatus.PENDING.value


def test_rerun_ignores_items_without_audio_or_from_another_set(env):
    store, set_id = env
    other_set = store.create_audio_set("o", "o.xlsx", ["S"], "v", [_item("9", "xin chào")])
    foreign = store.get_items(other_set)[0]["id"]
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    assert store.rerun_app_results(run_id, [foreign]) == 0
    assert len(store.app_results(run_id)) == 3


def test_link_pair_sets_both(env):
    store, set_id = env
    a = store.create_app_run(set_id, "A", "m", "p", None)
    b = store.create_app_run(set_id, "B", "m", "p", None)
    store.link_pair(a, b)
    assert store.get_app_run(a)["pair_run_id"] == b
    assert store.get_app_run(b)["pair_run_id"] == a
    assert {r["id"]: r["pair_run_id"] for r in store.list_app_runs(set_id)} == {a: b, b: a}


def test_delete_one_of_pair_unlinks_other(env):
    store, set_id = env
    a = store.create_app_run(set_id, "A", "m", "p", None)
    b = store.create_app_run(set_id, "B", "m", "p", None)
    store.link_pair(a, b)
    store.delete_app_run(a)
    assert store.get_app_run(b)["pair_run_id"] is None


def test_old_db_gets_pair_column(tmp_path):
    import sqlite3

    path = tmp_path / "t.db"
    Store(path)
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE app_runs DROP COLUMN pair_run_id")
    conn.commit()
    conn.close()
    store = Store(path)
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "v", [_item("1", "bật đèn")])
    a = store.create_app_run(set_id, "A", "m", "p", None)
    assert store.get_app_run(a)["pair_run_id"] is None


def test_run_keeps_its_platform(env):
    store, set_id = env
    a = store.create_app_run(set_id, "U", "iPhone 15", "p", None, platform="ios")
    assert store.get_app_run(a)["platform"] == "ios"
    assert store.get_app_run(store.create_app_run(set_id, "A", "m", "p", None))["platform"] is None
