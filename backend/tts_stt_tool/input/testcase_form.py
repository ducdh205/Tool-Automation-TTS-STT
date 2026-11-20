"""Read the 36-column voice-assistant testcase form (header on row 4)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import column_index_from_string
from openpyxl.utils.escape import unescape

from tts_stt_tool.models import InputItem, SheetInfo

HEADER_ROW = 4
FIRST_DATA_ROW = 5
ID_HEADER = "TC_ID"
TEXT_HEADER = "Câu nói (utterance)"

# Column letters of the form (spec §3).
COLUMNS = {
    "tc_id": "A",
    "feature": "B",
    "priority": "E",
    "region": "H",
    "turn": "I",
    "speaker": "L",
    "text_raw": "M",
    "expected": "N",
}
_IDX = {k: column_index_from_string(v) - 1 for k, v in COLUMNS.items()}
_MAX_COL = max(_IDX.values()) + 1
FORM_COLS = 36  # A..AJ


class InputError(Exception):
    """An input file cannot be read."""


def cell_text(value: Any) -> str:
    """Convert a cell value to text; whole floats become ints ("2.0" -> "2")."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # Excel stores CR inside a cell as "_x000D_"; openpyxl leaves it escaped.
    return unescape(str(value)).strip()


@contextmanager
def open_workbook(path: Path) -> Iterator[Any]:
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except PermissionError as e:
        raise InputError(f"File đang được mở bởi chương trình khác: {path.name}") from e
    except FileNotFoundError as e:
        raise InputError(f"Không tìm thấy file: {path}") from e
    except Exception as e:  # corrupted / not an xlsx
        raise InputError(f"Không đọc được file Excel {path.name}: {e}") from e
    try:
        yield wb
    finally:
        wb.close()


def _is_form(ws: Any) -> bool:
    for row in ws.iter_rows(min_row=HEADER_ROW, max_row=HEADER_ROW, max_col=_MAX_COL, values_only=True):
        cells = list(row) + [None] * _MAX_COL
        return cell_text(cells[_IDX["tc_id"]]) == ID_HEADER and cell_text(cells[_IDX["text_raw"]]) == TEXT_HEADER
    return False


def _iter_items(ws: Any, sheet: str) -> Iterator[InputItem]:
    for r, row in enumerate(
        ws.iter_rows(min_row=FIRST_DATA_ROW, max_col=FORM_COLS, values_only=True), start=FIRST_DATA_ROW
    ):
        cells = (list(row) + [None] * FORM_COLS)[:FORM_COLS]
        values = {k: cell_text(cells[i]) for k, i in _IDX.items()}
        if not values["tc_id"]:
            continue
        yield InputItem(sheet=sheet, source_row=r, form=[cell_text(c) for c in cells], **values)


def is_testcase_form(path: Path, sheet: str) -> bool:
    with open_workbook(path) as wb:
        return sheet in wb.sheetnames and _is_form(wb[sheet])


def list_sheets(path: Path) -> list[SheetInfo]:
    with open_workbook(path) as wb:
        infos = []
        for name in wb.sheetnames:
            ws = wb[name]
            form = _is_form(ws)
            count = sum(1 for _ in _iter_items(ws, name)) if form else 0
            infos.append(SheetInfo(name=name, item_count=count, is_testcase=form))
        return infos


def read_testcase_items(path: Path, sheets: list[str]) -> list[InputItem]:
    with open_workbook(path) as wb:
        items: list[InputItem] = []
        for name in sheets:
            if name not in wb.sheetnames:
                raise InputError(f"Không có sheet '{name}' trong {path.name}")
            ws = wb[name]
            if not _is_form(ws):
                raise InputError(f"Sheet '{name}' không đúng form testcase (header dòng {HEADER_ROW})")
            items.extend(_iter_items(ws, name))
        return items
