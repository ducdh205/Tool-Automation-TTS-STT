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


class AppStatus(StrEnum):
    PENDING = "Chờ"
    PASSED = "Đúng"
    FAILED = "Sai"
    OP_ERROR = "Lỗi thao tác"


SCHEMA = """
CREATE TABLE IF NOT EXISTS audio_sets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    sheets_json TEXT NOT NULL,
    voice TEXT,
    voice_trung TEXT,
    voice_nam TEXT,
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
    updated_at TEXT,
    form_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_set ON items(audio_set_id, id);
CREATE TABLE IF NOT EXISTS app_runs (
    id INTEGER PRIMARY KEY,
    audio_set_id INTEGER NOT NULL REFERENCES audio_sets(id) ON DELETE CASCADE,
    serial TEXT, device_model TEXT, profile_name TEXT, app_version TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_results (
    id INTEGER PRIMARY KEY,
    app_run_id INTEGER NOT NULL REFERENCES app_runs(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    app_text TEXT, wer REAL, cer REAL, ops_json TEXT, error TEXT, log TEXT,
    updated_at TEXT,
    text_tts_snap TEXT, audio_snap TEXT, screenshot_path TEXT
);
CREATE INDEX IF NOT EXISTS ix_app_results_run ON app_results(app_run_id, id);
"""

_RESULT_SELECT = (
    # text/audio as they were when the run was created: later edits must not change what was tested
    "SELECT r.*, i.sheet, i.tc_id, i.turn, i.feature, i.priority, i.text_raw, i.source_row, i.speaker,"
    " i.region, i.expected,"
    " COALESCE(r.text_tts_snap, i.text_tts) AS text_tts, COALESCE(r.audio_snap, i.audio_path) AS audio_path"
    " FROM app_results r JOIN items i ON i.id = r.item_id"
)

_RESET_SQL = (
    "audio_path=NULL, attempts=0, ref_text=NULL, wer=NULL, cer=NULL, ops_json=NULL, error=NULL"
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _item_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["ops"] = json.loads(d.pop("ops_json")) if d.get("ops_json") else []
    d.pop("form_json", None)  # up to 36 cells per row: only the form export reads it (Store.form_cells)
    return d


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            # databases created before these columns
            for table, added in (("app_results", ("text_tts_snap", "audio_snap", "screenshot_path")),
                                 ("items", ("form_json",)),
                                 ("audio_sets", ("voice_trung", "voice_nam"))):
                cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
                for col in added:
                    if col not in cols:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")

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
        self, name: str, source_file: str, sheets: list[str], voice: str | None, items: list[InputItem],
        *, voice_trung: str | None = None, voice_nam: str | None = None,
    ) -> int:
        """``voice`` is the Miền Bắc voice and the fallback; Trung/Nam rows use their own voice when set."""
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO audio_sets(name, source_file, sheets_json, voice, voice_trung, voice_nam, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (name, source_file, json.dumps(sheets, ensure_ascii=False), voice, voice_trung, voice_nam, _now()),
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
                    json.dumps(it.form, ensure_ascii=False) if it.form else None,
                ))
            c.executemany(
                "INSERT INTO items(audio_set_id, sheet, tc_id, turn, feature, priority, region, speaker,"
                " expected, source_row, text_raw, text_tts, skip_reason, enabled, status, updated_at, form_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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

    def delete_audio_set(self, audio_set_id: int) -> dict[str, list] | None:
        """Delete a set with its items, app runs and results (cascade).

        Returns the deleted run ids and the WAV paths no other set still uses (the audio cache is
        content-addressed, so one file can back rows of several sets), or None if the set is unknown.
        """
        used = ("SELECT audio_path p, audio_set_id s FROM items WHERE audio_path IS NOT NULL"
                " UNION ALL SELECT r.audio_snap, a.audio_set_id FROM app_results r"
                " JOIN app_runs a ON a.id = r.app_run_id WHERE r.audio_snap IS NOT NULL")
        with self._conn() as c:
            if c.execute("SELECT 1 FROM audio_sets WHERE id=?", (audio_set_id,)).fetchone() is None:
                return None
            run_ids = [r["id"] for r in c.execute(
                "SELECT id FROM app_runs WHERE audio_set_id=? ORDER BY id", (audio_set_id,))]
            paths = [r["p"] for r in c.execute(
                f"SELECT DISTINCT p FROM ({used}) WHERE s=?"
                f" AND p NOT IN (SELECT p FROM ({used}) WHERE s<>?) ORDER BY p",
                (audio_set_id, audio_set_id))]
            c.execute("DELETE FROM audio_sets WHERE id=?", (audio_set_id,))
        return {"run_ids": run_ids, "audio_paths": paths}

    def delete_all_audio_sets(self) -> int:
        """Delete every set with its items, app runs and results (cascade); returns how many sets."""
        with self._conn() as c:
            return c.execute("DELETE FROM audio_sets").rowcount

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

    def form_cells(self, audio_set_id: int) -> dict[int, list[str]]:
        """Item id -> the 36 cells of its testcase-form row (items read from other inputs are absent)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, form_json FROM items WHERE audio_set_id=? AND form_json IS NOT NULL", (audio_set_id,)
            ).fetchall()
        return {r["id"]: json.loads(r["form_json"]) for r in rows}

    def _select_items(self, audio_set_id: int, item_ids: list[int] | None, where: str,
                      args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        sql = "SELECT * FROM items WHERE audio_set_id=? AND enabled=1 AND text_tts IS NOT NULL AND " + where
        params: list[Any] = [audio_set_id, *args]
        if item_ids is not None:
            if not item_ids:
                return []
            sql += f" AND id IN ({','.join('?' * len(item_ids))})"
            params += list(item_ids)
        with self._conn() as c:
            return [_item_row(r) for r in c.execute(sql + " ORDER BY id", params).fetchall()]

    def items_for_generate(self, audio_set_id: int, item_ids: list[int] | None) -> list[dict[str, Any]]:
        """Rows without audio yet (new, edited, or failed while synthesizing)."""
        return self._select_items(audio_set_id, item_ids, "audio_path IS NULL AND status IN (?,?)",
                                  (ItemStatus.PENDING.value, ItemStatus.ERROR.value))

    def items_for_regenerate(self, audio_set_id: int, item_ids: list[int] | None) -> list[dict[str, Any]]:
        """Rows with audio; without a selection only the ones whose audio failed verification."""
        if item_ids is not None:
            return self._select_items(audio_set_id, item_ids, "audio_path IS NOT NULL")
        return self._select_items(audio_set_id, None, "audio_path IS NOT NULL AND status=?",
                                  (ItemStatus.AUDIO_FAILED.value,))

    def items_for_verify(self, audio_set_id: int, item_ids: list[int] | None) -> list[dict[str, Any]]:
        """Rows with audio; without a selection only the ones not verified yet (or whose STT failed)."""
        if item_ids is not None:
            return self._select_items(audio_set_id, item_ids, "audio_path IS NOT NULL")
        return self._select_items(audio_set_id, None, "audio_path IS NOT NULL AND status IN (?,?)",
                                  (ItemStatus.GENERATED.value, ItemStatus.ERROR.value))

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

    @staticmethod
    def _guard(text_tts: str | None) -> tuple[str, tuple[Any, ...]]:
        """Extra WHERE so a result computed for an old text never lands on an edited row."""
        return (" AND text_tts=?", (text_tts,)) if text_tts is not None else ("", ())

    def record_generated(self, item_id: int, audio_path: str, attempts: int, text_tts: str | None = None) -> bool:
        where, args = self._guard(text_tts)
        with self._conn() as c:
            cur = c.execute(
                "UPDATE items SET audio_path=?, attempts=?, status=?, error=NULL, ref_text=NULL, wer=NULL, cer=NULL,"
                " ops_json=NULL, updated_at=? WHERE id=?" + where,
                (audio_path, attempts, ItemStatus.GENERATED.value, _now(), item_id, *args),
            )
            return cur.rowcount > 0

    def record_verify(
        self, item_id: int, ref_text: str, result: CompareResult, status: ItemStatus, text_tts: str | None = None
    ) -> bool:
        where, args = self._guard(text_tts)
        with self._conn() as c:
            cur = c.execute(
                "UPDATE items SET ref_text=?, wer=?, cer=?, ops_json=?, status=?, error=NULL, updated_at=?"
                " WHERE id=?" + where,
                (ref_text, result.wer, result.cer, json.dumps(result.ops_as_dicts(), ensure_ascii=False),
                 status.value, _now(), item_id, *args),
            )
            return cur.rowcount > 0

    def record_error(self, item_id: int, msg: str, text_tts: str | None = None) -> bool:
        where, args = self._guard(text_tts)
        with self._conn() as c:
            cur = c.execute(
                "UPDATE items SET status=?, error=?, updated_at=? WHERE id=?" + where,
                (ItemStatus.ERROR.value, msg, _now(), item_id, *args),
            )
            return cur.rowcount > 0

    # -- block 2 (app runs) ------------------------------------------------
    def create_app_run(
        self, audio_set_id: int, serial: str, device_model: str | None, profile_name: str, app_version: str | None,
        item_ids: list[int] | None = None,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO app_runs(audio_set_id, serial, device_model, profile_name, app_version, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (audio_set_id, serial, device_model, profile_name, app_version, _now()),
            )
            run_id = int(cur.lastrowid)
            sql = ("INSERT INTO app_results(app_run_id, item_id, status, updated_at, text_tts_snap, audio_snap)"
                   " SELECT ?, id, ?, ?, text_tts, audio_path FROM items"
                   " WHERE audio_set_id=? AND status=? AND enabled=1 AND audio_path IS NOT NULL")
            params: list[Any] = [run_id, AppStatus.PENDING.value, _now(), audio_set_id, ItemStatus.PASSED.value]
            if item_ids is not None:
                sql += f" AND id IN ({','.join('?' * len(item_ids)) or 'NULL'})"
                params += list(item_ids)
            c.execute(sql + " ORDER BY id", params)
            return run_id

    def delete_app_run(self, run_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM app_runs WHERE id=?", (run_id,))  # results cascade

    def get_app_run(self, run_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM app_runs WHERE id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def list_app_runs(self, audio_set_id: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM app_runs WHERE audio_set_id=? ORDER BY id DESC", (audio_set_id,)).fetchall()
        return [{**dict(r), "summary": self.app_summary(r["id"])} for r in rows]

    def app_results(self, run_id: int) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(_RESULT_SELECT + " WHERE r.app_run_id=? ORDER BY r.id", (run_id,)).fetchall()
        return [_item_row(r) for r in rows]

    def get_app_result(self, result_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute(_RESULT_SELECT + " WHERE r.id=?", (result_id,)).fetchone()
        return _item_row(r) if r else None

    def pending_for_block2(self, run_id: int) -> list[dict[str, Any]]:
        return [r for r in self.app_results(run_id) if r["status"] in (AppStatus.PENDING.value, AppStatus.OP_ERROR.value)]

    def record_app_result(
        self, result_id: int, status: AppStatus, app_text: str | None, result: CompareResult | None,
        error: str | None, log: str, screenshot_path: str | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE app_results SET status=?, app_text=?, wer=?, cer=?, ops_json=?, error=?, log=?,"
                " screenshot_path=?, updated_at=? WHERE id=?",
                (status.value, app_text, result.wer if result else None, result.cer if result else None,
                 json.dumps(result.ops_as_dicts(), ensure_ascii=False) if result else None,
                 error, log, screenshot_path, _now(), result_id),
            )

    def app_summary(self, run_id: int) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) n FROM app_results WHERE app_run_id=? GROUP BY status", (run_id,)
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}
