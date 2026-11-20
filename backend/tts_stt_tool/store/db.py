"""SQLite persistence for audio sets (Block 1) and their items."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from tts_stt_tool.compare.score import CompareResult
from tts_stt_tool.input.filters import classify
from tts_stt_tool.models import InputItem


class ItemStatus(StrEnum):
    PENDING = "Chờ"
    SKIPPED = "Không áp dụng"
    GENERATED = "Đã sinh audio"
    PASSED = "Đạt"
    AUDIO_FAILED = "Audio không đạt"
    ERROR = "Lỗi"


SCHEMA = """
CREATE TABLE IF NOT EXISTS audio_sets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    sheets_json TEXT NOT NULL,
    voice TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    audio_set_id INTEGER NOT NULL REFERENCES audio_sets(id) ON DELETE CASCADE,
    sheet TEXT, tc_id TEXT, turn TEXT, feature TEXT, priority TEXT, region TEXT,
    speaker TEXT, expected TEXT, source_row INTEGER,
    text_raw TEXT, text_tts TEXT, skip_reason TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    audio_path TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    ref_text TEXT, wer REAL, cer REAL, ops_json TEXT, error TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_set ON items(audio_set_id, id);
"""

_BLOCK1_TODO = (ItemStatus.PENDING, ItemStatus.GENERATED, ItemStatus.ERROR)
_RESET_SQL = (
    "audio_path=NULL, attempts=0, ref_text=NULL, wer=NULL, cer=NULL, ops_json=NULL, error=NULL"
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _item_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["ops"] = json.loads(d.pop("ops_json")) if d.get("ops_json") else []
    return d


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                with conn:  # one transaction
                    yield conn
            finally:
                conn.close()

    # -- audio sets -------------------------------------------------------
    def create_audio_set(
        self, name: str, source_file: str, sheets: list[str], voice: str | None, items: list[InputItem]
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO audio_sets(name, source_file, sheets_json, voice, created_at) VALUES (?,?,?,?,?)",
                (name, source_file, json.dumps(sheets, ensure_ascii=False), voice, _now()),
            )
            set_id = int(cur.lastrowid)
            rows = []
            for it in items:
                text_tts, reason = classify(it)
                status = ItemStatus.SKIPPED if reason else ItemStatus.PENDING
                rows.append((
                    set_id, it.sheet, it.tc_id, it.turn, it.feature, it.priority, it.region,
                    it.speaker, it.expected, it.source_row, it.text_raw, text_tts, reason,
                    0 if reason else 1, status.value, _now(),
                ))
            c.executemany(
                "INSERT INTO items(audio_set_id, sheet, tc_id, turn, feature, priority, region, speaker,"
                " expected, source_row, text_raw, text_tts, skip_reason, enabled, status, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            return set_id

    def list_audio_sets(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM audio_sets ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sheets"] = json.loads(d.pop("sheets_json"))
            out.append(d)
        return out

    def get_audio_set(self, audio_set_id: int) -> dict[str, Any] | None:
        return next((s for s in self.list_audio_sets() if s["id"] == audio_set_id), None)

    def summary(self, audio_set_id: int) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) n FROM items WHERE audio_set_id=? GROUP BY status", (audio_set_id,)
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    # -- items ------------------------------------------------------------
    def get_items(self, audio_set_id: int, status: ItemStatus | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM items WHERE audio_set_id=?"
        args: list[Any] = [audio_set_id]
        if status is not None:
            sql += " AND status=?"
            args.append(status.value)
        with self._conn() as c:
            return [_item_row(r) for r in c.execute(sql + " ORDER BY id", args).fetchall()]

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return _item_row(r) if r else None

    def pending_for_block1(self, audio_set_id: int) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(_BLOCK1_TODO))
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM items WHERE audio_set_id=? AND enabled=1 AND text_tts IS NOT NULL"
                f" AND status IN ({marks}) ORDER BY id",
                [audio_set_id, *[s.value for s in _BLOCK1_TODO]],
            ).fetchall()
        return [_item_row(r) for r in rows]

    def set_item_text(self, item_id: int, text_tts: str) -> None:
        with self._conn() as c:
            c.execute(
                f"UPDATE items SET text_tts=?, status=?, enabled=1, skip_reason=NULL, {_RESET_SQL},"
                " updated_at=? WHERE id=?",
                (text_tts, ItemStatus.PENDING.value, _now(), item_id),
            )

    def set_enabled(self, item_id: int, enabled: bool) -> None:
        with self._conn() as c:
            c.execute("UPDATE items SET enabled=?, updated_at=? WHERE id=?", (int(enabled), _now(), item_id))

    def record_generated(self, item_id: int, audio_path: str, attempts: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE items SET audio_path=?, attempts=?, status=?, error=NULL, updated_at=? WHERE id=?",
                (audio_path, attempts, ItemStatus.GENERATED.value, _now(), item_id),
            )

    def record_verify(self, item_id: int, ref_text: str, result: CompareResult, status: ItemStatus) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE items SET ref_text=?, wer=?, cer=?, ops_json=?, status=?, error=NULL, updated_at=?"
                " WHERE id=?",
                (ref_text, result.wer, result.cer, json.dumps(result.ops_as_dicts(), ensure_ascii=False),
                 status.value, _now(), item_id),
            )

    def record_error(self, item_id: int, msg: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE items SET status=?, error=?, updated_at=? WHERE id=?",
                (ItemStatus.ERROR.value, msg, _now(), item_id),
            )
