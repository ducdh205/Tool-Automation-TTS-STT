"""An app run with one result of each kind, shared by the result-export and session-zip tests."""

from types import SimpleNamespace

import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.models import InputItem
from tts_stt_tool.store.db import AppStatus, ItemStatus, Store

SHEET = "Ionizer via voice command"


def input_item(tc, turn, text, row):
    return InputItem(sheet=SHEET, tc_id=tc, turn=turn, feature="Bật ionizer", priority="P0 - Smoke",
                     region="BAC-HN", speaker="👤 Người dùng", text_raw=text, expected="Ionizer bật",
                     source_row=row)


def make_session(tmp_path):
    store = Store(tmp_path / "t.db")
    settings = Settings(data_dir=tmp_path)
    items = [
        input_item("TC1", "1", "Bật ionizer", 5),
        input_item("TC2", "1", "Hey Vita, mở cửa sổ", 6),
        input_item("TC3", "1", "Tắt đèn", 7),
    ]
    set_id = store.create_audio_set("Bộ điều khiển", "DieuKhienXe_Pre.xlsx", [SHEET], "Ngọc Huyền", items)
    audio = tmp_path / "audio"
    audio.mkdir()
    for it in store.get_items(set_id):
        wav = audio / f"{it['id']}.wav"
        wav.write_bytes(b"RIFF-fake-" + str(it["id"]).encode())
        store.record_generated(it["id"], str(wav), 1)
        store.record_verify(it["id"], it["text_tts"], compare(it["text_tts"], it["text_tts"]), ItemStatus.PASSED)
    run_id = store.create_app_run(set_id, "SER123", "Pixel 7", "Vita Work (dev)", "1.2.3")
    ok, wrong, broken = store.app_results(run_id)
    shots = tmp_path / "shots"
    shots.mkdir()
    (shots / "2.png").write_bytes(b"\x89PNG-wrong")
    (shots / "3.png").write_bytes(b"\x89PNG-op")
    store.record_app_result(ok["id"], AppStatus.PASSED, "bật ionizer", compare("bật ionizer", "bật ionizer"),
                            None, "Bấm mic\nApp nhận: bật ionizer")
    store.record_app_result(wrong["id"], AppStatus.FAILED, "mở cửa số", compare("mở cửa sổ", "mở cửa số"),
                            None, "Bấm mic\nApp nhận: mở cửa số", screenshot_path=str(shots / "2.png"))
    store.record_app_result(broken["id"], AppStatus.OP_ERROR, None, None, "Mic không bật", "Bấm mic",
                            screenshot_path=str(shots / "3.png"))
    by_tc = {r["tc_id"]: r for r in store.app_results(run_id)}
    return SimpleNamespace(store=store, settings=settings, set_id=set_id, run_id=run_id, by_tc=by_tc)


@pytest.fixture
def session(tmp_path):
    return make_session(tmp_path)
