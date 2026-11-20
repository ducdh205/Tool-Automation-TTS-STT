"""Block 1 Excel / CSV reports."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from tts_stt_tool.config import Settings
from tts_stt_tool.store.db import ItemStatus, Store

SHEET_OVERVIEW = "Tổng quan"
SHEET_VERIFY = "Khối 1 – Verify"
SHEET_FAILED = "Audio không đạt"
SHEET_SKIPPED = "Không áp dụng"
SHEET_ERRORS = "Lỗi"

DETAIL_HEADERS = [
    "Sheet", "TC_ID", "Lượt", "Cụm tính năng", "Ưu tiên", "Câu gốc", "Câu đọc",
    "Text STT tham chiếu", "WER", "CER", "Từ sai", "Số lần sinh", "Trạng thái",
]
SKIPPED_HEADERS = ["Sheet", "TC_ID", "Lượt", "Người nói", "Câu gốc", "Lý do"]
ERROR_HEADERS = ["Sheet", "TC_ID", "Lượt", "Câu đọc", "Lỗi"]

RED_FILL = PatternFill("solid", fgColor="FFFFC7CE")
HEADER_FILL = PatternFill("solid", fgColor="FFDDEBF7")
BOLD = Font(bold=True)
PCT = "0.0%"
_VERIFIED = (ItemStatus.PASSED.value, ItemStatus.AUDIO_FAILED.value)
_WIDTHS = {"Câu gốc": 45, "Câu đọc": 45, "Text STT tham chiếu": 45, "Từ sai": 30, "Lỗi": 50,
           "Lý do": 25, "Sheet": 30, "Trạng thái": 16, "Cụm tính năng": 18}


def format_ops(ops: list[dict[str, Any]]) -> str:
    parts = []
    for o in ops:
        if o["op"] == "sub":
            parts.append(f"{o['ref']}→{o['hyp']}")
        elif o["op"] == "del":
            parts.append(f"-{o['ref']}")
        elif o["op"] == "ins":
            parts.append(f"+{o['hyp']}")
    return "; ".join(parts)


def _detail_row(i: dict[str, Any]) -> list[Any]:
    return [
        i["sheet"], i["tc_id"], i["turn"], i["feature"], i["priority"], i["text_raw"], i["text_tts"],
        i["ref_text"], i["wer"], i["cer"], format_ops(i["ops"]), i["attempts"], i["status"],
    ]


def reject_ratio(summary: dict[str, int]) -> float:
    failed = summary.get(ItemStatus.AUDIO_FAILED.value, 0)
    verified = failed + summary.get(ItemStatus.PASSED.value, 0)
    return failed / verified if verified else 0.0


def _table(ws: Any, headers: list[str], rows: list[list[Any]], pct_cols: tuple[str, ...] = ()) -> None:
    ws.append(headers)
    for c in ws[1]:
        c.font = BOLD
        c.fill = HEADER_FILL
    for r in rows:
        ws.append(r)
    for idx, h in enumerate(headers, start=1):
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = _WIDTHS.get(h, 12)
        if h in pct_cols:
            for cell in ws[letter][1:]:
                cell.number_format = PCT
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions


def _overview(ws: Any, store: Store, audio_set_id: int, settings: Settings, items: list[dict]) -> None:
    s = store.get_audio_set(audio_set_id) or {}
    summary = store.summary(audio_set_id)
    verified = [i for i in items if i["status"] in _VERIFIED]
    ratio = reject_ratio(summary)

    ws["A1"] = "BÁO CÁO KHỐI 1 – VERIFY AUDIO"
    ws["A1"].font = Font(bold=True, size=14)
    pairs: list[tuple[str, Any, str | None]] = [
        ("Bộ audio", s.get("name"), None),
        ("File input", s.get("source_file"), None),
        ("Sheet", ", ".join(s.get("sheets", [])), None),
        ("Giọng", s.get("voice"), None),
        ("Tạo lúc", s.get("created_at"), None),
        ("Xuất lúc", datetime.now().isoformat(timespec="seconds"), None),
        ("Tổng số dòng", len(items), None),
    ]
    pairs += [(st.value, summary.get(st.value, 0), None) for st in ItemStatus]
    avg = lambda key: sum(i[key] or 0 for i in verified) / len(verified) if verified else 0  # noqa: E731
    pairs += [
        ("WER trung bình", avg("wer"), PCT),
        ("CER trung bình", avg("cer"), PCT),
        ("Tỉ lệ audio bị loại", ratio, PCT),
    ]
    row = 3
    for label, value, fmt in pairs:
        ws.cell(row=row, column=1, value=label).font = BOLD
        cell = ws.cell(row=row, column=2, value=value)
        if fmt:
            cell.number_format = fmt
        if label == "Tỉ lệ audio bị loại" and ratio > settings.reject_warn_ratio:
            cell.fill = RED_FILL
            warn = ws.cell(row=row + 1, column=1, value=(
                f"⚠ Tỉ lệ audio bị loại vượt ngưỡng {settings.reject_warn_ratio:.0%} — "
                "kết quả có thể không đại diện cho toàn bộ file input."))
            warn.font = Font(bold=True, color="FF9C0006")
            warn.fill = RED_FILL
            row += 1
        row += 1

    row += 1
    headers = ["Theo sheet", "Số câu", "Đạt", "Audio không đạt", "Không áp dụng", "Lỗi", "Tỉ lệ loại"]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = BOLD
        c.fill = HEADER_FILL
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in items:
        per[i["sheet"]][i["status"]] += 1
        per[i["sheet"]]["_n"] += 1
    for sheet, counts in per.items():
        row += 1
        ws.cell(row=row, column=1, value=sheet)
        ws.cell(row=row, column=2, value=counts["_n"])
        ws.cell(row=row, column=3, value=counts[ItemStatus.PASSED.value])
        ws.cell(row=row, column=4, value=counts[ItemStatus.AUDIO_FAILED.value])
        ws.cell(row=row, column=5, value=counts[ItemStatus.SKIPPED.value])
        ws.cell(row=row, column=6, value=counts[ItemStatus.ERROR.value])
        c = ws.cell(row=row, column=7, value=reject_ratio(counts))
        c.number_format = PCT
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 40
    for letter in "CDEFG":
        ws.column_dimensions[letter].width = 16


def build_block1_report(
    store: Store, audio_set_id: int, settings: Settings, out_path: Path, app_run_id: int | None = None
) -> Path:
    """Write the Block 1 workbook. ``app_run_id`` is reserved for Block 2 (plan 2)."""
    items = store.get_items(audio_set_id)
    wb = Workbook()
    _overview(wb.active, store, audio_set_id, settings, items)
    wb.active.title = SHEET_OVERVIEW

    active = [i for i in items if i["status"] != ItemStatus.SKIPPED.value]
    _table(wb.create_sheet(SHEET_VERIFY), DETAIL_HEADERS, [_detail_row(i) for i in active], ("WER", "CER"))
    failed = [i for i in items if i["status"] == ItemStatus.AUDIO_FAILED.value]
    _table(wb.create_sheet(SHEET_FAILED), DETAIL_HEADERS, [_detail_row(i) for i in failed], ("WER", "CER"))
    skipped = [i for i in items if i["status"] == ItemStatus.SKIPPED.value]
    _table(wb.create_sheet(SHEET_SKIPPED), SKIPPED_HEADERS,
           [[i["sheet"], i["tc_id"], i["turn"], i["speaker"], i["text_raw"], i["skip_reason"]] for i in skipped])
    errors = [i for i in items if i["status"] == ItemStatus.ERROR.value]
    _table(wb.create_sheet(SHEET_ERRORS), ERROR_HEADERS,
           [[i["sheet"], i["tc_id"], i["turn"], i["text_tts"], i["error"]] for i in errors])
    for ws in wb.worksheets[1:]:
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def export_block1_csv(store: Store, audio_set_id: int, out_path: Path) -> Path:
    items = [i for i in store.get_items(audio_set_id) if i["status"] != ItemStatus.SKIPPED.value]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(DETAIL_HEADERS)
        w.writerows(_detail_row(i) for i in items)
    return out_path
