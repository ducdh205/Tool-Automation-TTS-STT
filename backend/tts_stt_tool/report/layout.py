"""Where each testcase lives inside a session export (shared by the form Excel and the zip)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from tts_stt_tool.store.db import AppStatus

DEFAULT_SHEET = "Dữ liệu"  # audio sets read from csv have no sheet name

# Worst status of a testcase's turns decides the folder prefix (failures sort first by name).
_PREFIX_ORDER = [
    (AppStatus.FAILED.value, "FAIL_"),
    (AppStatus.OP_ERROR.value, "LOI_"),
    (AppStatus.PENDING.value, "CHUA_"),
    (AppStatus.PASSED.value, "PASS_"),
]
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_component(name: str) -> str:
    """One path component Windows accepts (real sheet names can end with a space)."""
    out = _INVALID.sub("_", name or "").rstrip(" .")
    if out.split(".")[0].upper() in _RESERVED:
        out = "_" + out
    return out or "_"


def turn_prefix(turn: str | None) -> str:
    m = re.search(r"\d+", turn or "")
    return f"luot{int(m.group()) if m else 1}_"


def _prefix(statuses: list[str]) -> str:
    for status, prefix in _PREFIX_ORDER:
        if status in statuses:
            return prefix
    return "PASS_"


def case_folders(results: list[dict[str, Any]]) -> dict[int, str]:
    """Result id -> ``"<sheet>/<PREFIX><TC_ID>[_n]"``.

    Turns of one TC_ID share a folder; a second row with the same TC_ID *and* turn is a
    different testcase that happens to reuse the ID, so it goes to ``<TC_ID>_2``.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in sorted(results, key=lambda r: (r.get("source_row") or 0, r["id"])):
        tc = r.get("tc_id") or f"dong{r.get('source_row') or r['id']}"
        groups[(r.get("sheet") or "", tc)].append(r)

    out: dict[int, str] = {}
    for (sheet, tc), rows in groups.items():
        copies: list[list[dict[str, Any]]] = []
        for row in rows:
            turn = turn_prefix(row.get("turn"))
            copy = next((c for c in copies if all(turn_prefix(x.get("turn")) != turn for x in c)), None)
            if copy is None:
                copy = []
                copies.append(copy)
            copy.append(row)
        for n, copy in enumerate(copies, start=1):
            name = safe_component(tc) + ("" if n == 1 else f"_{n}")
            folder = f"{safe_component(sheet or DEFAULT_SHEET)}/{_prefix([x['status'] for x in copy])}{name}"
            for row in copy:
                out[row["id"]] = folder
    return out
