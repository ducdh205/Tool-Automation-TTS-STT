import openpyxl

from backend.tests.helpers import SAMPLE_XLSX
from backend.tests.report.conftest import SHEET, make_session
from tts_stt_tool.report.form_export import FORM_HEADERS, build_form_report, form_values

RUN = {"id": 12, "serial": "SER123", "device_model": "Pixel 7", "profile_name": "Vita Work (dev)",
       "app_version": "1.2.3", "created_at": "2026-11-20T15:30:12"}


def res(**kw):
    base = {"status": "Đúng", "app_text": "", "error": None, "wer": 0.0, "cer": 0.0, "ops": [],
            "text_tts": "mở cửa sổ", "text_raw": "mở cửa sổ"}
    return base | kw


def test_headers_match_the_sample_form():
    ws = openpyxl.load_workbook(SAMPLE_XLSX, read_only=True)["Ionizer via voice command"]
    row4 = next(ws.iter_rows(min_row=4, max_row=4, max_col=36, values_only=True))
    assert list(row4) == FORM_HEADERS


def test_form_values_wrong_text():
    v = form_values(res(status="Sai", app_text="mở cửa số", wer=0.25, cer=0.08,
                        ops=[{"op": "equal", "ref": "mở", "hyp": "mở"}, {"op": "sub", "ref": "sổ", "hyp": "số"}],
                        text_raw="Hey Vita, mở cửa sổ"),
                    RUN, "S/FAIL_TC1", "ghi chú gốc")
    assert v["P"] == "mở cửa số" and v["S"] == "Fail" and v["X"] == "Fail" and v["Z"] == "S/FAIL_TC1/"
    assert v["AA"] == "Phiên #12 · Pixel 7 · Vita Work (dev) v1.2.3 · 2026-11-20 15:30"
    assert v["AB"] == "ghi chú gốc\nWER 25% · CER 8% · sai: sổ→số · câu đã đọc: mở cửa sổ"


def test_form_values_pass_and_op_error_and_pending():
    v = form_values(res(status="Đúng", app_text=""), RUN | {"device_model": None, "app_version": None}, "f", "")
    assert v["P"] == "(app không trả câu)" and v["S"] == "Pass" and v["X"] == ""
    assert v["AA"] == "Phiên #12 · SER123 · Vita Work (dev) · 2026-11-20 15:30"
    assert v["AB"] == "WER 0% · CER 0%"
    v = form_values(res(status="Lỗi thao tác", error="Mic không bật", wer=None, cer=None), RUN, "f", "gốc")
    assert v["P"] == "Lỗi thao tác: Mic không bật" and v["S"] == "" and v["X"] == "" and v["AB"] == "gốc"
    v = form_values(res(status="Chờ", wer=None, cer=None), RUN, "f", "")
    assert v["P"] == "" and v["S"] == "" and v["AB"] == ""


def test_build_form_report_layout(tmp_path, session):
    out = build_form_report(session.store, session.run_id, tmp_path / "f.xlsx")
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Tổng hợp phiên", SHEET]
    ws = wb[SHEET]
    assert [ws.cell(4, c).value for c in range(1, 37)] == FORM_HEADERS
    assert ws["A3"].value == "THÔNG TIN CHUNG" and ws["P3"].value == "THỰC TẾ"
    assert "P3:Q3" in {str(m) for m in ws.merged_cells.ranges}
    assert ws["A4"].fill.fgColor.rgb == "FFDDEBF7"
    assert ws["P4"].fill.fgColor.rgb == "FFFFF2CC" and ws["AB4"].fill.fgColor.rgb == "FFFFF2CC"
    assert ws["X4"].fill.fgColor.rgb == "FFD9D9D9" and ws["AJ4"].fill.fgColor.rgb == "FFD9D9D9"
    assert ws.freeze_panes == "A5" and ws.auto_filter.ref == "A4:AJ7"
    assert [ws[f"A{r}"].value for r in (5, 6, 7)] == ["TC1", "TC2", "TC3"]
    assert ws["C5"].value == "UC_01" and ws["I5"].value == 1
    assert [ws[f"S{r}"].value for r in (5, 6, 7)] == ["Pass", "Fail", None]
    assert [ws[f"X{r}"].value for r in (5, 6, 7)] == [None, "Fail", None]
    assert ws["Z6"].value == f"{SHEET}/FAIL_TC2/"
    assert ws["AB6"].value.startswith("ghi chú gốc\nWER")
    assert ws["P7"].value == "Lỗi thao tác: Mic không bật"
    overview = wb["Tổng hợp phiên"]
    values = [c.value for row in overview.iter_rows() for c in row if c.value is not None]
    assert "Bộ điều khiển" in values and "Tỉ lệ đúng của app" in values


def test_form_export_without_form_json(tmp_path):
    s = make_session(tmp_path, form=False)
    wb = openpyxl.load_workbook(build_form_report(s.store, s.run_id, tmp_path / "f.xlsx"))
    ws = wb[SHEET]
    assert ws["A5"].value == "TC1" and ws["M5"].value == "Bật ionizer" and ws["N5"].value == "Ionizer bật"
    assert ws["C5"].value is None and ws["S5"].value == "Pass"


def test_text_cells_keep_leading_zeros_and_odd_digits(tmp_path):
    from backend.tests.report.conftest import input_item
    from tts_stt_tool.compare.score import compare
    from tts_stt_tool.store.db import AppStatus, ItemStatus, Store

    store = Store(tmp_path / "t.db")
    item = input_item("TC9", "2", "0912345678", 5)
    item.form[3] = "²"
    set_id = store.create_audio_set("b", "f.xlsx", [SHEET], "v", [item])
    row = store.get_items(set_id)[0]
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    store.record_generated(row["id"], str(wav), 1)
    store.record_verify(row["id"], row["text_tts"], compare(row["text_tts"], row["text_tts"]), ItemStatus.PASSED)
    run_id = store.create_app_run(set_id, "S", "M", "p", None)
    rid = store.app_results(run_id)[0]["id"]
    store.record_app_result(rid, AppStatus.PASSED, "0912345678", compare("0912345678", "0912345678"), None, "")
    ws = openpyxl.load_workbook(build_form_report(store, run_id, tmp_path / "f.xlsx"))[SHEET]
    assert ws["M5"].value == "0912345678" and ws["P5"].value == "0912345678"
    assert ws["D5"].value == "²"
    assert ws["I5"].value == 2  # the turn column stays numeric like the source form
