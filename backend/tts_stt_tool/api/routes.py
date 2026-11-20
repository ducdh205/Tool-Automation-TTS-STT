"""REST API (prefix /api)."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from tts_stt_tool.api.app import AppContext
from tts_stt_tool.config import save_settings
from tts_stt_tool.device.adb import KEYS, AdbError
from tts_stt_tool.input.filters import clean_text, has_words
from tts_stt_tool.input.generic import ColumnMapping, preview_columns, read_generic
from tts_stt_tool.input.testcase_form import InputError, list_sheets, read_testcase_items
from tts_stt_tool.jobs.runner import JobBusyError
from tts_stt_tool.pipeline.block1 import run_block1
from tts_stt_tool.report.excel import build_block1_report, export_block1_csv
from tts_stt_tool.store.db import ItemStatus
from tts_stt_tool.stt.wyoming_client import WyomingStt

router = APIRouter()
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ctx_of(request: Request) -> AppContext:
    return request.app.state.ctx


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", name).strip() or "file"


def _require_set(ctx: AppContext, set_id: int) -> dict[str, Any]:
    s = ctx.store.get_audio_set(set_id)
    if s is None:
        raise HTTPException(404, "Không tìm thấy bộ audio")
    return s


def _upload_path(ctx: AppContext, file_id: str) -> Path:
    p = (ctx.uploads / file_id).resolve()
    if p.parent != ctx.uploads.resolve() or not p.is_file():
        raise HTTPException(404, "Không tìm thấy file đã tải lên")
    return p


# -- input ------------------------------------------------------------------
@router.post("/files/inspect")
async def inspect_file(request: Request, file: UploadFile) -> dict[str, Any]:
    ctx = ctx_of(request)
    name = _safe_name(Path(file.filename or "input").name)
    if Path(name).suffix.lower() not in (".xlsx", ".xlsm", ".csv"):
        raise HTTPException(422, "Chỉ hỗ trợ file .xlsx hoặc .csv")
    ctx.uploads.mkdir(parents=True, exist_ok=True)
    file_id = f"{uuid.uuid4().hex[:8]}_{name}"
    path = ctx.uploads / file_id
    path.write_bytes(await file.read())
    try:
        if path.suffix.lower() == ".csv":
            return {"file_id": file_id, "sheets": [], "is_form": False,
                    "columns": preview_columns(path, None, 1)}
        sheets = await asyncio.to_thread(list_sheets, path)
        is_form = any(s.is_testcase for s in sheets)
        columns = [] if is_form else preview_columns(path, sheets[0].name if sheets else None, 1)
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    return {"file_id": file_id, "is_form": is_form, "columns": columns,
            "sheets": [s.__dict__ for s in sheets]}


class MappingIn(BaseModel):
    text_col: str
    id_col: str | None = None
    header_row: int = 1


class AudioSetIn(BaseModel):
    file_id: str
    sheets: list[str]
    name: str
    mapping: MappingIn | None = None


@router.post("/audio-sets")
async def create_audio_set(request: Request, body: AudioSetIn) -> dict[str, int]:
    ctx = ctx_of(request)
    path = _upload_path(ctx, body.file_id)
    try:
        if body.mapping:
            sheet = body.sheets[0] if body.sheets else None
            items = await asyncio.to_thread(read_generic, path, sheet, ColumnMapping(**body.mapping.model_dump()))
        else:
            if not body.sheets:
                raise HTTPException(422, "Chọn ít nhất một sheet")
            items = await asyncio.to_thread(read_testcase_items, path, body.sheets)
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    source = body.file_id.split("_", 1)[-1]
    set_id = ctx.store.create_audio_set(body.name or source, source, body.sheets, ctx.settings.voice, items)
    return {"id": set_id}


@router.get("/audio-sets")
def list_audio_sets(request: Request) -> list[dict[str, Any]]:
    ctx = ctx_of(request)
    return [{**s, "summary": ctx.store.summary(s["id"])} for s in ctx.store.list_audio_sets()]


@router.get("/audio-sets/{set_id}/items")
def get_items(request: Request, set_id: int, status: str | None = None) -> list[dict[str, Any]]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    st = None
    if status:
        try:
            st = ItemStatus(status)
        except ValueError as e:
            raise HTTPException(422, f"Trạng thái không hợp lệ: {status}") from e
    return ctx.store.get_items(set_id, st)


@router.get("/audio-sets/{set_id}/summary")
def get_summary(request: Request, set_id: int) -> dict[str, int]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    return ctx.store.summary(set_id)


class ItemPatch(BaseModel):
    text_tts: str | None = None
    enabled: bool | None = None


@router.patch("/items/{item_id}")
def patch_item(request: Request, item_id: int, body: ItemPatch) -> dict[str, Any]:
    ctx = ctx_of(request)
    if ctx.store.get_item(item_id) is None:
        raise HTTPException(404, "Không tìm thấy câu")
    if body.text_tts is not None:
        text = clean_text(body.text_tts)
        if not has_words(text):
            raise HTTPException(422, "Câu đọc phải có chữ để đọc")
        ctx.store.set_item_text(item_id, text)
    if body.enabled is not None:
        ctx.store.set_enabled(item_id, body.enabled)
    return ctx.store.get_item(item_id)


@router.get("/items/{item_id}/audio")
def item_audio(request: Request, item_id: int) -> FileResponse:
    item = ctx_of(request).store.get_item(item_id)
    if not item or not item["audio_path"] or not Path(item["audio_path"]).is_file():
        raise HTTPException(404, "Chưa có audio")
    # no-store: after an edit the same item id serves a different file
    return FileResponse(item["audio_path"], media_type="audio/wav", headers={"Cache-Control": "no-store"})


# -- jobs ---------------------------------------------------------------------
@router.post("/audio-sets/{set_id}/block1")
async def start_block1(request: Request, set_id: int) -> dict[str, str]:
    # async: runner.start needs the running event loop
    ctx = ctx_of(request)
    _require_set(ctx, set_id)

    async def job(emit, cancel) -> None:
        if ctx.wyoming is not None:
            await ctx.wyoming.ensure_running()
        await run_block1(ctx.store, set_id, ctx.tts, ctx.cache, ctx.stt, ctx.settings, emit, cancel)

    try:
        return {"job_id": ctx.runner.start(f"Khối 1 – bộ {set_id}", job)}
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict[str, bool]:
    if not ctx_of(request).runner.cancel(job_id):
        raise HTTPException(404, "Không có job này")
    return {"ok": True}


@router.get("/jobs/current")
def current_job(request: Request) -> dict[str, Any] | None:
    return ctx_of(request).runner.current()


# -- reports ------------------------------------------------------------------
@router.post("/audio-sets/{set_id}/report")
async def report(request: Request, set_id: int, format: Literal["xlsx", "csv"] = "xlsx") -> FileResponse:
    ctx = ctx_of(request)
    s = _require_set(ctx, set_id)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = f"{_safe_name(s['name'])}_{stamp}"
    if format == "csv":
        out = await asyncio.to_thread(export_block1_csv, ctx.store, set_id, ctx.reports / f"{base}.csv")
        return FileResponse(out, media_type="text/csv; charset=utf-8", filename=out.name)
    out = await asyncio.to_thread(build_block1_report, ctx.store, set_id, ctx.settings, ctx.reports / f"{base}.xlsx")
    return FileResponse(out, media_type=XLSX_TYPE, filename=out.name)


# -- settings / health --------------------------------------------------------
@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return ctx_of(request).settings.to_json()


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str | None = None
    max_regen: int = Field(ge=0, le=10)
    wer_threshold: float = Field(ge=0, le=1)
    reject_warn_ratio: float = Field(ge=0, le=1)
    wyoming_host: str
    wyoming_port: int = Field(ge=1, le=65535)
    stt_timeout_s: float = Field(gt=0, le=600)
    wyoming_cmd: list[str] = []
    port: int = Field(ge=1, le=65535)


@router.put("/settings")
def put_settings(request: Request, body: SettingsIn) -> dict[str, Any]:
    ctx = ctx_of(request)
    for k, v in body.model_dump().items():
        setattr(ctx.settings, k, v)
    save_settings(ctx.settings)
    if isinstance(ctx.stt, WyomingStt):  # apply without restart
        ctx.stt.host = ctx.settings.wyoming_host
        ctx.stt.port = ctx.settings.wyoming_port
        ctx.stt.timeout_s = ctx.settings.stt_timeout_s
    return ctx.settings.to_json()


@router.get("/voices")
async def voices(request: Request) -> list[dict[str, str]]:
    ctx = ctx_of(request)
    if ctx.voices is None:
        ctx.voices = await asyncio.to_thread(ctx.tts.voices)
    return [v.__dict__ for v in ctx.voices]


def _gpu_available() -> bool:
    try:
        import torch  # optional

        return bool(torch.cuda.is_available())
    except Exception:
        return False


# -- device -------------------------------------------------------------------
@router.get("/device")
async def device_status(request: Request) -> dict[str, Any]:
    adb = ctx_of(request).adb
    if not adb.available:
        return {"adb": False, "error": "Không tìm thấy adb", "devices": []}
    try:
        devices = await adb.devices()
    except AdbError as e:
        return {"adb": True, "error": str(e), "devices": []}
    return {"adb": True, "error": None, "devices": [d.to_json() for d in devices]}


@router.get("/device/{serial}/screen")
async def device_screen(request: Request, serial: str) -> Response:
    try:
        png = await ctx_of(request).adb.screencap(serial)
    except AdbError as e:
        raise HTTPException(503, str(e)) from e
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


class DeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["tap", "swipe", "key", "text"]
    x: int | None = Field(None, ge=0)
    y: int | None = Field(None, ge=0)
    x2: int | None = Field(None, ge=0)
    y2: int | None = Field(None, ge=0)
    duration_ms: int = Field(300, ge=1, le=5000)
    key: str | None = None
    text: str | None = Field(None, max_length=500)


@router.post("/device/{serial}/input")
async def device_input(request: Request, serial: str, body: DeviceInput) -> dict[str, bool]:
    adb = ctx_of(request).adb
    try:
        if body.action == "tap":
            if body.x is None or body.y is None:
                raise HTTPException(422, "Thiếu toạ độ")
            await adb.tap(serial, body.x, body.y)
        elif body.action == "swipe":
            if None in (body.x, body.y, body.x2, body.y2):
                raise HTTPException(422, "Thiếu toạ độ")
            await adb.swipe(serial, body.x, body.y, body.x2, body.y2, body.duration_ms)
        elif body.action == "key":
            if body.key not in KEYS:
                raise HTTPException(422, "Phím không hỗ trợ")
            await adb.key(serial, KEYS[body.key])
        else:
            if not body.text:
                raise HTTPException(422, "Thiếu nội dung")
            await adb.text(serial, body.text)
    except AdbError as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    ctx = ctx_of(request)
    if ctx.wyoming is not None:
        up = await ctx.wyoming.is_up()
    else:
        from tts_stt_tool.stt.server_manager import port_open

        up = await port_open(ctx.settings.wyoming_host, ctx.settings.wyoming_port, 0.5)
    return {"wyoming": up, "wyoming_error": ctx.wyoming_error, "gpu": _gpu_available(),
            "job": ctx.runner.current()}
