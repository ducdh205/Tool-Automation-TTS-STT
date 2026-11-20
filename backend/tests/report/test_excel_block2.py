import openpyxl
import pytest

from backend.tests.report.test_excel import find_value
from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.models import InputItem
from tts_stt_tool.report.excel import (
    APP_HEADERS,
    SHEET_APP,
    SHEET_OP_ERRORS,
    SHEET_OVERVIEW,
    build_block1_report,
)
from tts_stt_tool.store.db import AppStatus, ItemStatus, Store


@pytest.fixture
def run(tmp_path):
    store = Store(tmp_path / "t.db")
    texts = ["bật đèn", "tắt đèn", "mở cốp", "đóng cốp"]
    items = [InputItem(sheet="A" if i < 2 else "B", tc_id=f"TC-{i}", turn="1", feature="f", priority="P1",
                       region="", speaker="👤 Người dùng", text_raw=t, expected="", source_row=5) for i, t in enumerate(texts)]
    set_id = store.create_audio_set("bộ", "f.xlsx", ["A", "B"], "v", items)
    for r in store.get_items(set_id):
        store.record_generated(r["id"], f"{r['id']}.wav", 1)
        store.record_verify(r["id"], r["text_tts"], compare(r["text_tts"], r["text_tts"]), ItemStatus.PASSED)
    run_id = store.create_app_run(set_id, "SER1", "22120RN86G", "Vita Work (dev)", "1.0.7")
    res = store.app_results(run_id)
    store.record_app_result(res[0]["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "")
    store.record_app_result(res[1]["id"], AppStatus.PASSED, "tắt đèn", compare("tắt đèn", "tắt đèn"), None, "")
    store.record_app_result(res[2]["id"], AppStatus.FAILED, "mở cố", compare("mở cốp", "mở cố"), None, "")
    store.record_app_result(res[3]["id"], AppStatus.OP_ERROR, None, None, "Không thấy nút mic", "Bấm …")
    return store, set_id, run_id, Settings(data_dir=tmp_path)


def test_block2_sheets_and_rate(run, tmp_path):
    store, set_id, run_id, settings = run
    wb = openpyxl.load_workbook(build_block1_report(store, set_id, settings, tmp_path / "r.xlsx", app_run_id=run_id))
    assert SHEET_APP in wb.sheetnames and SHEET_OP_ERRORS in wb.sheetnames
    ov = wb[SHEET_OVERVIEW]
    assert find_value(ov, "Tỉ lệ đúng của app").value == pytest.approx(2 / 3)
    assert find_value(ov, "Thiết bị").value == "22120RN86G (SER1)"
    assert find_value(ov, "Phiên bản app").value == "1.0.7"
    app = wb[SHEET_APP]
    assert [c.value for c in app[1]] == APP_HEADERS
    assert app.max_row == 1 + 3  # op errors listed separately
    assert wb[SHEET_OP_ERRORS].max_row == 2
    labels = [c.value for c in ov["A"]]
    assert labels.count("A") >= 1 and labels.count("B") >= 1


def test_no_block2_without_run(run, tmp_path):
    store, set_id, _, settings = run
    wb = openpyxl.load_workbook(build_block1_report(store, set_id, settings, tmp_path / "r.xlsx"))
    assert SHEET_APP not in wb.sheetnames
