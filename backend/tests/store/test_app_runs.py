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


def test_run_contains_only_passed_items(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "22120RN86G", "Vita Work (dev)", "1.2.3")
    results = store.app_results(run_id)
    assert [r["text_tts"] for r in results] == ["bật đèn", "tắt đèn"]
    assert all(r["status"] == AppStatus.PENDING.value for r in results)
    assert results[0]["audio_path"].endswith(".wav")
    assert results[0]["tc_id"] == "1"


def test_record_and_summary(env):
    store, set_id = env
    run_id = store.create_app_run(set_id, "SER1", "m", "p", None)
    a, b = store.app_results(run_id)
    store.record_app_result(a["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "log a")
    store.record_app_result(b["id"], AppStatus.OP_ERROR, None, None, "Không thấy nút mic", "log b")
    assert store.app_summary(run_id) == {AppStatus.PASSED.value: 1, AppStatus.OP_ERROR.value: 1}
    rows = {r["id"]: r for r in store.app_results(run_id)}
    assert rows[a["id"]]["wer"] == 0 and rows[a["id"]]["app_text"] == "bật đèn"
    assert rows[b["id"]]["error"] == "Không thấy nút mic"
    assert [r["id"] for r in store.pending_for_block2(run_id)] == [b["id"]]


def test_runs_are_independent_and_listed(env):
    store, set_id = env
    r1 = store.create_app_run(set_id, "A", "m", "p", None)
    r2 = store.create_app_run(set_id, "B", "m", "p", None)
    first = store.app_results(r1)[0]
    store.record_app_result(first["id"], AppStatus.FAILED, "bật đen", compare("bật đèn", "bật đen"), None, "")
    assert store.app_summary(r2) == {AppStatus.PENDING.value: 2}
    runs = store.list_app_runs(set_id)
    assert [r["id"] for r in runs] == [r2, r1]
    assert runs[1]["summary"] == {AppStatus.FAILED.value: 1, AppStatus.PENDING.value: 1}
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
