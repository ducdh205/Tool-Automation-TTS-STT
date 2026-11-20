"""Shared data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InputItem:
    """One utterance row read from an input file."""

    sheet: str
    tc_id: str
    turn: str
    feature: str
    priority: str
    region: str
    speaker: str
    text_raw: str
    expected: str
    source_row: int


@dataclass
class SheetInfo:
    """A sheet of an input workbook."""

    name: str
    item_count: int
    is_testcase: bool
