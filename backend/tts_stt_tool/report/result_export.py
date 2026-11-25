"""An app run written into a copy of the audio set's input file (the kept copy itself is never modified).

The selected sheets keep their content and formatting; a summary sheet goes first and each sheet
gets four result columns (text, verdict, note, screenshot) after its last used column. Without the input file (csv input, sets made
before the file was kept, file gone) every sheet is a plain table instead.
"""

from __future__ import annotations

import io
import re
from copy import copy
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.styles import Alignment, PatternFill
from openpyxl.utils import get_column_letter, range_boundaries

from tts_stt_tool.report.excel import BOLD, HEADER_FILL, _app_overview, format_ops
from tts_stt_tool.report.layout import DEFAULT_SHEET
from tts_stt_tool.store.db import AppStatus, Store

OVERVIEW_SHEET = "Tổng hợp phiên"
RESULT_HEADERS = ["Text app nghe được", "Kết quả", "Ghi chú", "Ảnh màn hình"]
_RESULT_WIDTHS = (40, 14, 50, 22)
_RESULT_WRAP = (True, False, True, True)
SHOT_HEIGHT_PX = 240
_SHOT_ROW_PT = SHOT_HEIGHT_PX * 0.75 + 6  # row height in points that fits the thumbnail
_SHOT_STATUSES = (AppStatus.FAILED.value, AppStatus.OP_ERROR.value)
SHOT_MISSING = "(không tìm thấy ảnh)"
_PLAIN_HEADERS = ["TC_ID", "Lượt", "Vùng miền", "Câu gốc", "Kết quả mong đợi"]
_PLAIN_KEYS = ["tc_id", "turn", "region", "text_raw", "expected"]
_PLAIN_WIDTHS = (14, 8, 12, 45, 40)


def _pct(x: float | None) -> str:
    return f"{(x or 0) * 100:.0f}%"


def result_values(result: dict[str, Any]) -> tuple[str, str, str]:
    """(Text app nghe được, Kết quả, Ghi chú) for one result; all empty while it is untested."""
    status = result["status"]
    if status == AppStatus.OP_ERROR.value:
        return "", f"Lỗi thao tác: {result.get('error') or ''}", ""
    if status not in (AppStatus.PASSED.value, AppStatus.FAILED.value):
        return "", "", ""
    note = f"WER {_pct(result.get('wer'))} · CER {_pct(result.get('cer'))}"
    if any(o.get("op") != "equal" for o in result.get("ops") or []):
        note += f" · sai: {format_ops(result['ops'])}"
    if result.get("text_tts") and result["text_tts"] != result.get("text_raw"):
        note += f" · câu đã đọc: {result['text_tts']}"
    verdict = "Pass" if status == AppStatus.PASSED.value else "Fail"
    return result.get("app_text") or "(app không trả câu)", verdict, note


def _source(audio_set: dict[str, Any]) -> Path | None:
    p = audio_set.get("source_path")
    return Path(p) if p and Path(p).is_file() else None


def result_suffix(audio_set: dict[str, Any]) -> str:
    """File extension of the result workbook: a macro workbook stays .xlsm."""
    src = _source(audio_set)
    return ".xlsm" if src is not None and src.suffix.lower() == ".xlsm" else ".xlsx"


def _thumbnail(path: Path) -> XlImage | None:
    """A JPEG copy SHOT_HEIGHT_PX tall (full phone screenshots would bloat the workbook)."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((im.width * SHOT_HEIGHT_PX // max(im.height, 1) or 1, SHOT_HEIGHT_PX))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
    except (OSError, ValueError):  # missing or not an image
        return None
    buf.seek(0)
    return XlImage(buf)


def _write_screenshot(ws: Any, row: int, col: int, result: dict[str, Any]) -> None:
    if result["status"] not in _SHOT_STATUSES or not result.get("screenshot_path"):
        return
    img = _thumbnail(Path(result["screenshot_path"]))
    if img is None:
        ws.cell(row=row, column=col, value=SHOT_MISSING).alignment = Alignment(vertical="top", wrap_text=True)
        return
    ws.add_image(img, f"{get_column_letter(col)}{row}")
    dim = ws.row_dimensions[row]
    dim.height = max(dim.height or 0, _SHOT_ROW_PT)


def _write_results(ws: Any, row: int, first_col: int, result: dict[str, Any]) -> None:
    for i, value in enumerate(result_values(result)):
        c = ws.cell(row=row, column=first_col + i, value=value or None)
        c.alignment = Alignment(vertical="top", wrap_text=_RESULT_WRAP[i])
    _write_screenshot(ws, row, first_col + 3, result)


def _last_column(ws: Any, header_row: int, last_row: int) -> int:
    """Last column holding a header or any value (notes / formulas without a header too) in the table."""
    cols = [c.column for row in ws.iter_rows(min_row=header_row, max_row=max(header_row, last_row))
            for c in row if c.value is not None]
    cols += [r.max_col for r in ws.merged_cells.ranges if r.min_row <= header_row <= r.max_row]
    return max(cols) if cols else ws.max_column


def _fill_source_sheet(ws: Any, header_row: int, results: list[dict[str, Any]]) -> None:
    last_row = max([r.get("source_row") or 0 for r in results] + [ws.max_row])
    last = _last_column(ws, header_row, last_row)
    model = ws.cell(row=header_row, column=last)
    for i, name in enumerate(RESULT_HEADERS):
        col = last + 1 + i
        c = ws.cell(row=header_row, column=col, value=name)
        if model.has_style:
            c.font, c.fill, c.border = copy(model.font), copy(model.fill), copy(model.border)
            c.alignment = copy(model.alignment)
        else:
            c.font, c.fill = BOLD, HEADER_FILL
        ws.column_dimensions[get_column_letter(col)].width = _RESULT_WIDTHS[i]
    for r in results:
        if r.get("source_row"):
            _write_results(ws, r["source_row"], last + 1, r)
    if ws.auto_filter.ref:
        min_col, min_row, max_col, max_row = range_boundaries(ws.auto_filter.ref)
        end = max(max_col, last + len(RESULT_HEADERS))
        ws.auto_filter.ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(end)}{max_row}"


def _plain_sheet(wb: Any, name: str, results: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet(name[:31])
    for i, h in enumerate(_PLAIN_HEADERS + RESULT_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font, c.fill = BOLD, HEADER_FILL
        ws.column_dimensions[get_column_letter(i)].width = (_PLAIN_WIDTHS + _RESULT_WIDTHS)[i - 1]
    for n, r in enumerate(results, start=2):
        for i, key in enumerate(_PLAIN_KEYS, start=1):
            c = ws.cell(row=n, column=i, value=r.get(key) or None)
            c.alignment = Alignment(vertical="top", wrap_text=key == "text_raw")
        _write_results(ws, n, len(_PLAIN_KEYS) + 1, r)
    ws.freeze_panes = "A2"


def _formulas(ws: Any) -> list[str]:
    """Every formula text of a sheet: cells, dropdown lists, conditional formats, sheet-scoped names."""
    out = [getattr(c.value, "text", c.value) for row in ws.iter_rows() for c in row if c.data_type == "f"]
    for dv in ws.data_validations.dataValidation:
        out += [f for f in (dv.formula1, dv.formula2) if f]
    for cf in ws.conditional_formatting:
        for rule in cf.rules:
            out += list(rule.formula or [])
    out += [d.attr_text for d in ws.defined_names.values() if d.attr_text]
    return [str(f) for f in out if f]


def _refers_to(text: str, sheet: str) -> bool:
    quoted = "'" + sheet.replace("'", "''") + "'!"
    return quoted in text or re.search(r"(?<![\w.'])" + re.escape(sheet) + "!", text) is not None


def _referenced_sheets(wb: Any, kept: set[str]) -> set[str]:
    """Unselected sheets the kept ones reach through formulas or defined names (e.g. a dropdown's list)."""
    names = {n: d.attr_text for n, d in wb.defined_names.items() if d.attr_text}
    found: set[str] = set()
    todo = [ws for ws in wb.worksheets if ws.title in kept]
    while todo:
        text = "\n".join(f for ws in todo for f in _formulas(ws))
        text += "\n" + "\n".join(v for n, v in names.items()
                                 if re.search(r"(?<![\w.])" + re.escape(n) + r"(?![\w(])", text, re.I))
        todo = [ws for ws in wb.worksheets
                if ws.title not in kept | found and _refers_to(text, ws.title)]
        found |= {ws.title for ws in todo}
    return found


def _overview(wb: Any, store: Store, run_id: int, audio_set: dict[str, Any], results: list[dict]) -> None:
    name, n = OVERVIEW_SHEET, 1
    while name in wb.sheetnames:
        n += 1
        name = f"{OVERVIEW_SHEET} ({n})"
    ws = wb.create_sheet(name, 0)
    for label, value in (("Bộ audio", audio_set.get("name")), ("File nguồn", audio_set.get("source_file"))):
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = BOLD
    _app_overview(ws, store, run_id, results)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 28
    for other in wb.worksheets:  # a second selected tab would open the file with sheets grouped
        other.sheet_view.tabSelected = other is ws
    wb.active = 0


def build_result_report(store: Store, run_id: int, out_path: Path) -> Path:
    run = store.get_app_run(run_id) or {"id": run_id}
    audio_set = store.get_audio_set(run.get("audio_set_id")) or {}
    results = store.app_results(run_id)

    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(results, key=lambda r: (r.get("source_row") or 0, r["id"])):
        by_sheet.setdefault(r.get("sheet") or DEFAULT_SHEET, []).append(r)
    chosen = list(audio_set.get("sheets") or [])
    order = [s for s in chosen if s in by_sheet] + [s for s in by_sheet if s not in chosen]

    src = _source(audio_set)
    wb = None
    if src is not None:
        try:
            wb = openpyxl.load_workbook(src, keep_vba=src.suffix.lower() == ".xlsm")
        except Exception:  # unreadable copy: fall back to plain tables rather than fail the export
            wb = None
    if wb is not None:
        keep = set(chosen) | set(by_sheet)
        lookups = _referenced_sheets(wb, keep)  # removing them would turn dropdowns / formulas into #REF!
        for ws in list(wb.worksheets):
            if ws.title in lookups:
                ws.sheet_state = "hidden"
            elif ws.title not in keep:
                wb.remove(ws)
        header_row = int(audio_set.get("header_row") or 1)
        for sheet in order:
            if sheet in wb.sheetnames:
                _fill_source_sheet(wb[sheet], header_row, by_sheet[sheet])
            else:  # a selected sheet the file no longer has
                _plain_sheet(wb, sheet, by_sheet[sheet])
    else:
        wb = Workbook()
        wb.remove(wb.active)
        for sheet in order:
            _plain_sheet(wb, sheet, by_sheet[sheet])
    _overview(wb, store, run_id, audio_set, results)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
