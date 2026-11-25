"""Shared Excel helpers: cell text and workbook opening (the 36-column form is mapped like any other file)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils.escape import unescape

ID_HEADER = "TC_ID"
TEXT_HEADER = "Câu nói (utterance)"
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
