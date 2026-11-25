"""Read csv / xlsx testcase files through a user-chosen column mapping."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl.utils import get_column_letter

from tts_stt_tool.input.testcase_form import InputError, cell_text, open_workbook
from tts_stt_tool.models import InputItem

DEFAULT_SPEAKER = "👤 Người dùng"
PREVIEW_ROWS = 20

# Header keywords per mapping field, tried exact-match first, then "contains".
_KEYWORDS: dict[str, list[str]] = {
    "text_col": ["câu nói (utterance)", "câu nói", "utterance", "câu lệnh", "text"],
    "id_col": ["tc_id", "mã câu", "case id", "id"],
    "region_col": ["vùng miền", "region"],
    "expected_col": ["kết quả mong đợi", "expected"],
    "turn_col": ["bước / lượt", "bước", "lượt", "turn"],
}

# Short words that would match unrelated headers ("Các bước thực hiện", "Use case / Req ID") by substring.
_EXACT_ONLY = {"id", "bước", "lượt", "turn", "text"}


@dataclass
class ColumnMapping:
    text_col: str
    header_row: int = 1
    id_col: str | None = None
    region_col: str | None = None
    region_value: str | None = None
    expected_col: str | None = None
    turn_col: str | None = None


@dataclass
class SheetPreview:
    columns: list[str]
    rows: list[list[str]]
    row_count: int
    suggestions: dict[str, str] = field(default_factory=dict)


def sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return []
    with open_workbook(path) as wb:
        return list(wb.sheetnames)


def header_labels(cells: list[str]) -> list[str]:
    """Column names for a header row: trailing blanks dropped, blank -> "Cột F", duplicates -> "X (2)"."""
    cells = list(cells)
    while cells and not cells[-1]:
        cells.pop()
    labels: list[str] = []
    real = set(cells)
    for i, c in enumerate(cells, start=1):
        base = c or f"Cột {get_column_letter(i)}"
        label, n = base, 1
        # A label must be unique, and a generated one must not equal another real header.
        while label in labels or (label != c and label in real):
            n += 1
            label = f"{base} ({n})"
        labels.append(label)
    return labels


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    norm = [c.strip().lower() for c in columns]
    taken: set[int] = set()
    out: dict[str, str] = {}
    for key, words in _KEYWORDS.items():
        found = None
        for loose, match in ((False, lambda n, w: n == w), (True, lambda n, w: w in n)):
            for w in words:
                if loose and w in _EXACT_ONLY:
                    continue
                found = next((i for i, n in enumerate(norm) if i not in taken and match(n, w)), None)
                if found is not None:
                    break
            if found is not None:
                break
        if found is not None:
            taken.add(found)
            out[key] = columns[found]
    return out


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
        if sheet is not None and sheet not in wb.sheetnames:
            raise InputError(f"Không có sheet '{sheet}' trong {path.name}")
        ws = wb[sheet] if sheet else wb.worksheets[0]
        for n, row in enumerate(ws.iter_rows(min_row=header_row, values_only=True), start=header_row):
            yield n, [cell_text(c) for c in row]


def _sheet_rows(path: Path, sheet: str | None, header_row: int) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Header labels and the non-empty data rows below the header."""
    it = _rows(path, sheet, header_row)
    first = next(it, None)
    if first is None or first[0] != header_row:
        raise InputError(f"Sheet '{sheet or path.stem}' không có dòng {header_row}")
    labels = header_labels(first[1])
    data = [(n, cells) for n, cells in it if any(cells)]
    return labels, data


def preview_sheet(path: Path, sheet: str | None, header_row: int, limit: int = PREVIEW_ROWS) -> SheetPreview:
    labels, data = _sheet_rows(path, sheet, header_row)
    rows = [(cells + [""] * len(labels))[: len(labels)] for _, cells in data[:limit]]
    return SheetPreview(columns=labels, rows=rows, row_count=len(data), suggestions=suggest_mapping(labels))


def _col_index(labels: list[str], col: str | None, sheet: str) -> int | None:
    if not col:
        return None
    if col not in labels:
        raise InputError(f"Sheet '{sheet}' không có cột '{col}'")
    return labels.index(col)


def read_items(path: Path, sheets: list[str], mapping: ColumnMapping) -> list[InputItem]:
    targets: list[str | None] = list(sheets) if path.suffix.lower() != ".csv" and sheets else [None]
    items: list[InputItem] = []
    for sheet in targets:
        sheet_name = sheet or path.stem
        labels, data = _sheet_rows(path, sheet, mapping.header_row)
        t_idx = _col_index(labels, mapping.text_col, sheet_name)
        i_idx = _col_index(labels, mapping.id_col, sheet_name)
        r_idx = _col_index(labels, mapping.region_col, sheet_name)
        e_idx = _col_index(labels, mapping.expected_col, sheet_name)
        n_idx = _col_index(labels, mapping.turn_col, sheet_name)
        width = len(labels)
        for n, cells in data:
            cells = (cells + [""] * width)[:width]
            if i_idx is not None and not cells[i_idx]:
                continue
            items.append(
                InputItem(
                    sheet=sheet_name,
                    tc_id=cells[i_idx] if i_idx is not None else str(n),
                    turn=(cells[n_idx] if n_idx is not None else "") or "1",
                    feature="",
                    priority="",
                    region=cells[r_idx] if r_idx is not None else (mapping.region_value or ""),
                    speaker=DEFAULT_SPEAKER,
                    text_raw=cells[t_idx],
                    expected=cells[e_idx] if e_idx is not None else "",
                    source_row=n,
                )
            )
    return items
