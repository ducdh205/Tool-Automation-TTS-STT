"""An app run written back into the 36-column testcase form (a new file; the input is never modified)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter

from tts_stt_tool.report.excel import BOLD, _app_overview, format_ops
from tts_stt_tool.report.layout import DEFAULT_SHEET, case_folders
from tts_stt_tool.store.db import AppStatus, Store

OVERVIEW_SHEET = "Tổng hợp phiên"
FORM_HEADERS = [
    "TC_ID", "Cụm tính năng", "Use case / Req ID", "Mục đích kiểm thử", "Mức ưu tiên", "Loại test",
    "Mã lĩnh vực KT (A–V)", "Vùng miền", "Bước / Lượt", "Tiền điều kiện & môi trường", "Các bước thực hiện",
    "Người nói", "Câu nói (utterance)", "Kết quả mong đợi", "Độ trễ tối đa (giây)", "Kết quả thực tế",
    "Độ trễ thực tế (giây)", "KQ Wake", "KQ ASR", "KQ NLU", "KQ Hành động", "KQ Phản hồi", "KQ Độ trễ",
    "KẾT QUẢ TỔNG", "Bug ID", "Bằng chứng (link video/log)", "Thông tin lần chạy", "Ghi chú",
    "AI chấm (Pass/Fail)", "Lý do AI chấm", "Langfuse: các bước (B1…Bn)", "Langfuse: bước lỗi đầu tiên",
    "Langfuse: hệ thống đi qua", "Langfuse: cloud nghe (STT)", "Langfuse: chi tiết key (log bug)",
    "Langfuse: cảnh báo",
]
FORM_GROUPS = [
    ("A", "I", "THÔNG TIN CHUNG"), ("J", "M", "ĐẦU VÀO"), ("N", "O", "MONG ĐỢI"), ("P", "Q", "THỰC TẾ"),
    ("R", "X", "ĐÁNH GIÁ THEO TẦNG"), ("Y", "AD", "THEO DÕI"),
    ("AE", "AJ", "LANGFUSE (tool tự điền sau khi 🔄 Đồng bộ Langfuse)"),
]
LEGEND = ("Cột nền xanh nhạt: người thiết kế test điền · Cột nền vàng: tester điền khi chạy test · "
          "Cột nền xám: tự tính, không sửa · Test đa lượt: cùng TC_ID, mỗi lượt một dòng (Bước 1, 2, 3…)")
_BLUE, _YELLOW, _GRAY = "FFDDEBF7", "FFFFF2CC", "FFD9D9D9"
_WIDTHS = {"A": 13, "C": 28, "D": 42, "J": 44, "K": 50, "M": 38, "N": 50, "P": 38, "Z": 29, "AB": 40}
_WRAP = ("M", "N", "P", "AB")
_NOTE = column_index_from_string("AB") - 1
# Without a stored form row (sets imported before the form was kept): the columns the DB has.
_FALLBACK = {"A": "tc_id", "B": "feature", "E": "priority", "H": "region", "I": "turn", "L": "speaker",
             "M": "text_raw", "N": "expected"}


def _fill(col: str) -> str:
    i = column_index_from_string(col)
    if i <= column_index_from_string("O"):
        return _BLUE
    if col == "X" or i >= column_index_from_string("AC"):
        return _GRAY
    return _YELLOW


def _pct(x: float | None) -> str:
    return f"{(x or 0) * 100:.0f}%"


def form_values(result: dict[str, Any], run: dict[str, Any], folder: str, original_note: str) -> dict[str, str]:
    """The cells the tool fills for one row: P, S, X, Z, AA, AB."""
    status = result["status"]
    tested = status in (AppStatus.PASSED.value, AppStatus.FAILED.value)
    if tested:
        actual = result.get("app_text") or "(app không trả câu)"
    elif status == AppStatus.OP_ERROR.value:
        actual = f"Lỗi thao tác: {result.get('error') or ''}"
    else:
        actual = ""
    run_info = f"Phiên #{run['id']} · {run.get('device_model') or run.get('serial')} · {run.get('profile_name')}"
    if run.get("app_version"):
        run_info += f" v{run['app_version']}"
    run_info += f" · {(run.get('created_at') or '')[:16].replace('T', ' ')}"
    note = original_note
    if tested:
        detail = f"WER {_pct(result.get('wer'))} · CER {_pct(result.get('cer'))}"
        if any(o.get("op") != "equal" for o in result.get("ops") or []):
            detail += f" · sai: {format_ops(result['ops'])}"
        if result.get("text_tts") and result["text_tts"] != result.get("text_raw"):
            detail += f" · câu đã đọc: {result['text_tts']}"
        note = f"{note}\n{detail}" if note else detail
    return {
        "P": actual,
        "S": {AppStatus.PASSED.value: "Pass", AppStatus.FAILED.value: "Fail"}.get(status, ""),
        "X": "Fail" if status == AppStatus.FAILED.value else "",
        "Z": folder + "/",
        "AA": run_info,
        "AB": note,
    }


def _cell_value(text: str) -> Any:
    return int(text) if text.isdigit() else (text or None)


def _sheet_header(ws: Any, title: str) -> None:
    last = get_column_letter(len(FORM_HEADERS))
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells(f"A1:{last}1")
    ws["A2"] = LEGEND
    ws.merge_cells(f"A2:{last}2")
    for start, end, label in FORM_GROUPS:
        ws[f"{start}3"] = label
        ws[f"{start}3"].font = BOLD
        ws.merge_cells(f"{start}3:{end}3")
    for i, name in enumerate(FORM_HEADERS, start=1):
        col = get_column_letter(i)
        c = ws.cell(row=4, column=i, value=name)
        c.font = BOLD
        c.fill = PatternFill("solid", fgColor=_fill(col))
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[col].width = _WIDTHS.get(col, 13)


def build_form_report(store: Store, run_id: int, out_path: Path) -> Path:
    run = store.get_app_run(run_id) or {"id": run_id}
    audio_set = store.get_audio_set(run.get("audio_set_id")) or {}
    results = store.app_results(run_id)
    cells = store.form_cells(audio_set.get("id")) if audio_set else {}
    folders = case_folders(results)

    wb = Workbook()
    overview = wb.active
    overview.title = OVERVIEW_SHEET
    for label, value in (("Bộ audio", audio_set.get("name")), ("File nguồn", audio_set.get("source_file"))):
        overview.append([label, value])
        overview.cell(row=overview.max_row, column=1).font = BOLD
    _app_overview(overview, store, run_id, results)
    overview.column_dimensions["A"].width = 30
    overview.column_dimensions["B"].width = 28

    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_sheet.setdefault(r.get("sheet") or DEFAULT_SHEET, []).append(r)
    order = [s for s in audio_set.get("sheets", []) if s in by_sheet] + \
            [s for s in by_sheet if s not in audio_set.get("sheets", [])]
    for sheet in order:
        ws = wb.create_sheet(sheet[:31])
        _sheet_header(ws, f"{audio_set.get('name', '')} · Phiên #{run_id} — kết quả test ASR tự động")
        rows = sorted(by_sheet[sheet], key=lambda r: (r.get("source_row") or 0, r["id"]))
        for n, r in enumerate(rows, start=5):
            form = cells.get(r["item_id"])
            if form:
                base = (list(form) + [""] * len(FORM_HEADERS))[:len(FORM_HEADERS)]
            else:
                base = [""] * len(FORM_HEADERS)
                for col, key in _FALLBACK.items():
                    base[column_index_from_string(col) - 1] = str(r.get(key) or "")
            values = form_values(r, run, folders[r["id"]], base[_NOTE] if form else "")
            for col, v in values.items():
                base[column_index_from_string(col) - 1] = v
            for i, text in enumerate(base, start=1):
                c = ws.cell(row=n, column=i, value=_cell_value(text))
                c.alignment = Alignment(vertical="top", wrap_text=get_column_letter(i) in _WRAP)
        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(FORM_HEADERS))}{4 + len(rows)}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
