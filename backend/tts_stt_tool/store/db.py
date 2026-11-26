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

from tts_stt_tool.compare.normalize import normalize
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


class VerifyStatus(StrEnum):
    """Block 1 STT check of a row's audio, shown next to it in Block 2 (which tests every row with audio)."""

    PASSED = "Đạt"
    FAILED = "Không đạt"
    NOT_YET = "Chưa"


def verify_status(item_status: str | None) -> str:
    if item_status == ItemStatus.PASSED.value:
        return VerifyStatus.PASSED.value
    if item_status == ItemStatus.AUDIO_FAILED.value:
        return VerifyStatus.FAILED.value
    return VerifyStatus.NOT_YET.value


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
    created_at TEXT NOT NULL,
    source_path TEXT,
    header_row INTEGER
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
    created_at TEXT NOT NULL,
    wer_threshold REAL NOT NULL DEFAULT 0  -- a result is "Đúng" when its WER is at most this
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
CREATE TABLE IF NOT EXISTS app_attempts (
    id INTEGER PRIMARY KEY,
    app_result_id INTEGER NOT NULL REFERENCES app_results(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    app_text TEXT, wer REAL, cer REAL, ops_json TEXT, error TEXT, log TEXT, screenshot_path TEXT,
    text_tts_snap TEXT, audio_snap TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_app_attempts_result ON app_attempts(app_result_id, id);
"""

# what a finished result keeps when it is run again (``rerun_app_results``)
_ATTEMPT_COLS = "status, app_text, wer, cer, ops_json, error, log, screenshot_path, text_tts_snap, audio_snap, updated_at"

_RESULT_SELECT = (
    # text/audio as they were when the run was created: later edits must not change what was tested
    "SELECT r.*, i.sheet, i.tc_id, i.turn, i.feature, i.priority, i.text_raw, i.source_row, i.speaker,"
    " i.region, i.expected, i.status AS item_status,"
    " COALESCE(r.text_tts_snap, i.text_tts) AS text_tts, COALESCE(r.audio_snap, i.audio_path) AS audio_path"
    " FROM app_results r JOIN items i ON i.id = r.item_id"
)

_ITEM_COLUMNS = (
    "id", "audio_set_id", "sheet", "tc_id", "turn", "feature", "priority", "region", "speaker", "expected",
    "source_row", "text_raw", "text_tts", "skip_reason", "enabled", "status", "audio_path", "attempts",
    "ref_text", "wer", "cer", "ops_json", "error", "updated_at", "form_json",
)

_RESET_SQL = (
    "audio_path=NULL, attempts=0, ref_text=NULL, wer=NULL, cer=NULL, ops_json=NULL, error=NULL"
)


# a row Block 2 can play: generated (verified or not), still enabled
_HAS_AUDIO = "enabled=1 AND audio_path IS NOT NULL AND status<>?"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _item_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["ops"] = json.loads(d.pop("ops_json")) if d.get("ops_json") else []
    d.pop("form_json", None)  # legacy column of the old 36-column form export, no longer read
    # an app result carries its item's Block 1 status as item_status; an item row has it as status
    d["verify"] = verify_status(d.pop("item_status") if "item_status" in d else d.get("status"))
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
            cols = {r["name"] for r in c.execute("PRAGMA table_info(audio_sets)")}
            for col, kind in (("source_path", "TEXT"), ("header_row", "INTEGER")):
                if col not in cols:
                    c.execute(f"ALTER TABLE audio_sets ADD COLUMN {col} {kind}")
            if "wer_threshold" not in {r["name"] for r in c.execute("PRAGMA table_info(app_runs)")}:
                c.execute("ALTER TABLE app_runs ADD COLUMN wer_threshold REAL NOT NULL DEFAULT 0")

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
                ))
            c.executemany(
                "INSERT INTO items(audio_set_id, sheet, tc_id, turn, feature, priority, region, speaker,"
                " expected, source_row, text_raw, text_tts, skip_reason, enabled, status, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            return set_id

    def set_source(self, audio_set_id: int, source_path: str | None, header_row: int) -> None:
        """The kept copy of the input file (None for csv) and its header row, used by the result export."""
        with self._conn() as c:
            c.execute("UPDATE audio_sets SET source_path=?, header_row=? WHERE id=?",
                      (source_path, header_row, audio_set_id))

    def set_voices(self, audio_set_id: int, voice: str | None, voice_trung: str | None, voice_nam: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE audio_sets SET voice=?, voice_trung=?, voice_nam=? WHERE id=?",
                      (voice, voice_trung, voice_nam, audio_set_id))

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
                " JOIN app_runs a ON a.id = r.app_run_id WHERE r.audio_snap IS NOT NULL"
                " UNION ALL SELECT t.audio_snap, a.audio_set_id FROM app_attempts t"
                " JOIN app_results r ON r.id = t.app_result_id JOIN app_runs a ON a.id = r.app_run_id"
                " WHERE t.audio_snap IS NOT NULL")
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

    def export_audio_set(self, audio_set_id: int) -> dict[str, Any] | None:
        """A set's own data for a zip: set fields + raw item rows (no ids, no app runs); None if unknown."""
        meta = self.get_audio_set(audio_set_id)
        if meta is None:
            return None
        with self._conn() as c:
            rows = c.execute("SELECT * FROM items WHERE audio_set_id=? ORDER BY id", (audio_set_id,)).fetchall()
        items = [{k: v for k, v in dict(r).items() if k not in ("id", "audio_set_id")} for r in rows]
        keys = ("name", "source_file", "sheets", "voice", "voice_trung", "voice_nam", "created_at")
        return {"audio_set": {k: meta[k] for k in keys}, "items": items}

    def import_audio_set(self, audio_set: dict[str, Any], items: list[dict[str, Any]]) -> int:
        """Insert a new set from ``export_audio_set`` data; a taken name gets " (2)", " (3)"…

        Rows are stored as given (no ``classify``): only known item columns are read.
        """
        cols = [c for c in _ITEM_COLUMNS if c not in ("id", "audio_set_id")]
        with self._conn() as c:
            taken = {r["name"] for r in c.execute("SELECT name FROM audio_sets")}
            base = audio_set.get("name") or "bo-audio"
            name, n = base, 1
            while name in taken:
                n += 1
                name = f"{base} ({n})"
            cur = c.execute(
                "INSERT INTO audio_sets(name, source_file, sheets_json, voice, voice_trung, voice_nam, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (name, audio_set.get("source_file") or "", json.dumps(audio_set.get("sheets") or [], ensure_ascii=False),
                 audio_set.get("voice"), audio_set.get("voice_trung"), audio_set.get("voice_nam"), _now()),
            )
            set_id = int(cur.lastrowid)
            now = _now()
            rows = []
            for it in items:
                row = {k: it.get(k) for k in cols}
                row["status"] = row["status"] or ItemStatus.PENDING.value
                row["enabled"] = 1 if row["enabled"] is None else row["enabled"]
                row["attempts"] = row["attempts"] or 0
                row["updated_at"] = row["updated_at"] or now
                rows.append((set_id, *(row[k] for k in cols)))
            c.executemany(
                f"INSERT INTO items(audio_set_id, {', '.join(cols)}) VALUES (?{',?' * len(cols)})", rows)
            return set_id

    def reset_progress(self) -> int:
        """Put every row of every set back to "Chờ" and drop all app runs; imported rows stay.

        Rows marked "Không áp dụng" keep that status. Returns how many rows were reset.
        """
        with self._conn() as c:
            c.execute("DELETE FROM app_runs")
            c.execute(f"UPDATE items SET {_RESET_SQL}, updated_at=? WHERE status=?",
                      (_now(), ItemStatus.SKIPPED.value))
            return c.execute(f"UPDATE items SET status=?, {_RESET_SQL}, updated_at=? WHERE status<>?",
                             (ItemStatus.PENDING.value, _now(), ItemStatus.SKIPPED.value)).rowcount

    def summary(self, audio_set_id: int) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) n FROM items WHERE audio_set_id=? GROUP BY status", (audio_set_id,)
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def count_with_audio(self, audio_set_id: int) -> int:
        """Rows ready for Block 2 (see ``create_app_run``)."""
        with self._conn() as c:
            return c.execute(f"SELECT COUNT(*) FROM items WHERE audio_set_id=? AND {_HAS_AUDIO}",
                             (audio_set_id, ItemStatus.SKIPPED.value)).fetchone()[0]

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
        item_ids: list[int] | None = None, wer_threshold: float = 0.0,
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO app_runs(audio_set_id, serial, device_model, profile_name, app_version, created_at,"
                " wer_threshold) VALUES (?,?,?,?,?,?,?)",
                (audio_set_id, serial, device_model, profile_name, app_version, _now(), wer_threshold),
            )
            run_id = int(cur.lastrowid)
            # every row with audio goes to the app, whatever its verify result (shown beside it)
            sql = ("INSERT INTO app_results(app_run_id, item_id, status, updated_at, text_tts_snap, audio_snap)"
                   " SELECT ?, id, ?, ?, text_tts, audio_path FROM items"
                   f" WHERE audio_set_id=? AND {_HAS_AUDIO}")
            params: list[Any] = [run_id, AppStatus.PENDING.value, _now(), audio_set_id, ItemStatus.SKIPPED.value]
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

    def set_app_threshold(self, run_id: int, wer_threshold: float) -> bool:
        """Change what counts as "Đúng" in this run and grade its finished results again.

        Only "Đúng"/"Sai" rows change (an operation error or a waiting row has no WER); an empty
        answer stays "Sai" whatever the threshold. Earlier attempts in the history keep their grade.
        """
        with self._conn() as c:
            if not c.execute("UPDATE app_runs SET wer_threshold=? WHERE id=?", (wer_threshold, run_id)).rowcount:
                return False
            rows = c.execute(
                "SELECT id, app_text, wer FROM app_results WHERE app_run_id=? AND status IN (?,?) AND wer IS NOT NULL",
                (run_id, AppStatus.PASSED.value, AppStatus.FAILED.value),
            ).fetchall()
            for r in rows:
                ok = bool(normalize(r["app_text"] or "")) and r["wer"] <= wer_threshold
                c.execute("UPDATE app_results SET status=? WHERE id=?",
                          ((AppStatus.PASSED if ok else AppStatus.FAILED).value, r["id"]))
            return True

    def rerun_app_results(self, run_id: int, item_ids: list[int]) -> int:
        """Queue ``item_ids`` again in this run; every other result of the run stays as it is.

        A finished result moves to ``app_attempts`` (shown as its ``history``) and its row goes back
        to "Chờ" with the item's current text and audio. Picked rows with audio that the run did
        not test yet are added. Rows without audio, or of another set, are ignored. Returns how
        many rows are now waiting.
        """
        if not item_ids:
            return 0
        marks = ",".join("?" * len(item_ids))
        with self._conn() as c:
            run = c.execute("SELECT audio_set_id FROM app_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                return 0
            playable = (f"SELECT id FROM items WHERE audio_set_id=? AND {_HAS_AUDIO} AND id IN ({marks})")
            p_args = [run["audio_set_id"], ItemStatus.SKIPPED.value, *item_ids]
            c.execute(
                f"INSERT INTO app_attempts(app_result_id, {_ATTEMPT_COLS})"
                f" SELECT id, {_ATTEMPT_COLS} FROM app_results"
                f" WHERE app_run_id=? AND status<>? AND item_id IN ({playable}) ORDER BY id",
                (run_id, AppStatus.PENDING.value, *p_args),
            )
            reset = c.execute(
                "UPDATE app_results SET status=?, app_text=NULL, wer=NULL, cer=NULL, ops_json=NULL, error=NULL,"
                " log=NULL, screenshot_path=NULL, updated_at=?,"
                " text_tts_snap=(SELECT text_tts FROM items WHERE items.id=app_results.item_id),"
                " audio_snap=(SELECT audio_path FROM items WHERE items.id=app_results.item_id)"
                f" WHERE app_run_id=? AND item_id IN ({playable})",
                (AppStatus.PENDING.value, _now(), run_id, *p_args),
            ).rowcount
            added = c.execute(
                "INSERT INTO app_results(app_run_id, item_id, status, updated_at, text_tts_snap, audio_snap)"
                f" SELECT ?, id, ?, ?, text_tts, audio_path FROM items WHERE id IN ({playable})"
                " AND id NOT IN (SELECT item_id FROM app_results WHERE app_run_id=?) ORDER BY id",
                (run_id, AppStatus.PENDING.value, _now(), *p_args, run_id),
            ).rowcount
            return reset + added

    def _with_history(self, c: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        out = [_item_row(r) for r in rows]
        if not out:
            return out
        by_id = {d["id"]: d for d in out}
        for d in out:
            d["history"] = []
        marks = ",".join("?" * len(by_id))
        for t in c.execute(
            f"SELECT * FROM app_attempts WHERE app_result_id IN ({marks}) ORDER BY id DESC", list(by_id)
        ):
            h = dict(t)
            h["ops"] = json.loads(h.pop("ops_json")) if h.get("ops_json") else []
            h["text_tts"], h["audio_path"] = h.pop("text_tts_snap"), h.pop("audio_snap")
            by_id[h.pop("app_result_id")]["history"].append(h)
        return out

    def app_results(self, run_id: int) -> list[dict[str, Any]]:
        """Results of a run; each carries ``history``: its earlier attempts, newest first."""
        with self._conn() as c:
            rows = c.execute(_RESULT_SELECT + " WHERE r.app_run_id=? ORDER BY r.id", (run_id,)).fetchall()
            return self._with_history(c, rows)

    def get_app_result(self, result_id: int) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute(_RESULT_SELECT + " WHERE r.id=?", (result_id,)).fetchone()
            return self._with_history(c, [r])[0] if r else None

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
