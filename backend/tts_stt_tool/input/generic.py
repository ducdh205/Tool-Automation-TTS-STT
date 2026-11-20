"""Read csv / xlsx files that are not the testcase form, via a column mapping."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tts_stt_tool.input.testcase_form import InputError, cell_text, open_workbook
from tts_stt_tool.models import InputItem

DEFAULT_SPEAKER = "👤 Người dùng"


@dataclass
class ColumnMapping:
    text_col: str
    id_col: str | None = None
    header_row: int = 1


def _rows(path: Path, sheet: str | None, header_row: int) -> Iterator[tuple[int, list[str]]]:
    """Yield ``(row_number, cells)`` starting at the header row (1-based)."""
    if path.suffix.lower() == ".csv":
        try:
            with path.open(encoding="utf-8-sig", newline="") as f:
                for n, row in enumerate(csv.reader(f), start=1):
                    if n >= header_row:
                        yield n, [c.strip() for c in row]
        except FileNotFoundError as e:
            raise InputError(f"Không tìm thấy file: {path}") from e
        except PermissionError as e:
            raise InputError(f"File đang được mở bởi chương trình khác: {path.name}") from e
        except UnicodeDecodeError as e:
            raise InputError(f"File CSV phải mã hóa UTF-8: {path.name}") from e
        return
    with open_workbook(path) as wb:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        for n, row in enumerate(ws.iter_rows(min_row=header_row, values_only=True), start=header_row):
            yield n, [cell_text(c) for c in row]


def preview_columns(path: Path, sheet: str | None, header_row: int) -> list[str]:
    for _, cells in _rows(path, sheet, header_row):
        return cells
    return []


def read_generic(path: Path, sheet: str | None, mapping: ColumnMapping) -> list[InputItem]:
    rows = _rows(path, sheet, mapping.header_row)
    try:
        _, header = next(rows)
    except StopIteration:
        return []
    if mapping.text_col not in header:
        raise InputError(f"Không có cột '{mapping.text_col}'")
    t_idx = header.index(mapping.text_col)
    i_idx = header.index(mapping.id_col) if mapping.id_col and mapping.id_col in header else None
    sheet_name = sheet or path.stem
    items = []
    for n, cells in rows:
        cells = cells + [""] * len(header)
        if not any(cells):
            continue
        items.append(
            InputItem(
                sheet=sheet_name,
                tc_id=cells[i_idx] if i_idx is not None and cells[i_idx] else str(n),
                turn="1",
                feature="",
                priority="",
                region="",
                speaker=DEFAULT_SPEAKER,
                text_raw=cells[t_idx],
                expected="",
                source_row=n,
            )
        )
    return items
