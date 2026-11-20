"""REST API (prefix /api)."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from tts_stt_tool.api.app import AppContext
from tts_stt_tool.config import save_settings
from tts_stt_tool.device.adb import KEYS, AdbError
from tts_stt_tool.device.profile import AppProfile, get_profile, list_profiles, save_profile
from tts_stt_tool.device.ui_tree import node_at, parse_dump
from tts_stt_tool.input.filters import clean_text, has_words
from tts_stt_tool.input.generic import ColumnMapping, preview_columns, read_generic
from tts_stt_tool.input.testcase_form import InputError, list_sheets, read_testcase_items
from tts_stt_tool.jobs.runner import JobBusyError
from tts_stt_tool.pipeline.block1 import run_generate, run_verify
from tts_stt_tool.pipeline.block2 import run_block2
from tts_stt_tool.report.excel import build_block1_report, export_block1_csv
from tts_stt_tool.report.form_export import build_form_report
from tts_stt_tool.report.session_zip import build_session_zip, session_root_name
from tts_stt_tool.store.db import ItemStatus
from tts_stt_tool.stt.wyoming_client import WyomingStt
from tts_stt_tool.tts.base import VoiceInfo

router = APIRouter()
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VOICE_PREVIEW_TEXT = "Xin chào, bạn muốn bật quạt hay điều chỉnh nhiệt độ?"


def ctx_of(request: Request) -> AppContext:
    return request.app.state.ctx


def _require_free(ctx: AppContext, serial: str) -> None:
    """Manual taps / pin dumps would break the sentence a block 2 job is running on this phone."""
    if ctx.busy_serial == serial:
        raise HTTPException(409, "Điện thoại đang chạy test app — tạm khóa thao tác tay")


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
class ItemIdsIn(BaseModel):
    item_ids: list[int] | None = None  # None = every eligible row


def _start(ctx: AppContext, name: str, job) -> dict[str, str]:
    try:
        return {"job_id": ctx.runner.start(name, job)}
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


# async handlers: runner.start needs the running event loop
@router.post("/audio-sets/{set_id}/generate")
async def start_generate(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    ids = body.item_ids if body else None
    if not ctx.store.items_for_generate(set_id, ids):
        raise HTTPException(422, "Không có câu nào cần sinh audio")

    async def job(emit, cancel) -> None:
        await run_generate(ctx.store, set_id, ctx.tts, ctx.cache, ctx.settings, emit, cancel, item_ids=ids)

    return _start(ctx, f"Sinh audio – bộ {set_id}", job)


@router.post("/audio-sets/{set_id}/regenerate")
async def start_regenerate(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    ids = body.item_ids if body else None
    if not ctx.store.items_for_regenerate(set_id, ids):
        raise HTTPException(422, "Không có câu nào để sinh lại")

    async def job(emit, cancel) -> None:
        await run_generate(ctx.store, set_id, ctx.tts, ctx.cache, ctx.settings, emit, cancel,
                           item_ids=ids, regenerate=True)

    return _start(ctx, f"Sinh lại – bộ {set_id}", job)


@router.post("/audio-sets/{set_id}/verify")
async def start_verify(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    ids = body.item_ids if body else None
    if not ctx.store.items_for_verify(set_id, ids):
        raise HTTPException(422, "Không có câu nào có audio để verify")

    async def job(emit, cancel) -> None:
        if ctx.wyoming is not None:
            await ctx.wyoming.ensure_running()
        await run_verify(ctx.store, set_id, ctx.stt, ctx.settings, emit, cancel, item_ids=ids)

    return _start(ctx, f"Verify – bộ {set_id}", job)


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
async def report(
    request: Request, set_id: int, format: Literal["xlsx", "csv"] = "xlsx", app_run_id: int | None = None
) -> FileResponse:
    ctx = ctx_of(request)
    s = _require_set(ctx, set_id)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = f"{_safe_name(s['name'])}_{stamp}"
    if format == "csv":
        out = await asyncio.to_thread(export_block1_csv, ctx.store, set_id, ctx.reports / f"{base}.csv")
        return FileResponse(out, media_type="text/csv; charset=utf-8", filename=out.name)
    if app_run_id is not None:
        run = ctx.store.get_app_run(app_run_id)
        if run is None or run["audio_set_id"] != set_id:
            raise HTTPException(404, "Lần test app không thuộc bộ audio này")
    out = await asyncio.to_thread(build_block1_report, ctx.store, set_id, ctx.settings, ctx.reports / f"{base}.xlsx",
                                  app_run_id)
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


async def _available_voices(ctx: AppContext) -> list[VoiceInfo]:
    if ctx.voices is None:
        async with ctx.voice_lock:
            if ctx.voices is None:
                ctx.voices = await asyncio.to_thread(ctx.tts.voices)
    return ctx.voices


@router.get("/voices")
async def voices(request: Request) -> list[dict[str, str]]:
    return [v.__dict__ for v in await _available_voices(ctx_of(request))]


@router.get("/voices/preview")
async def voice_preview(request: Request, voice_id: str) -> FileResponse:
    ctx = ctx_of(request)
    if not any(voice.id == voice_id for voice in await _available_voices(ctx)):
        raise HTTPException(404, "Giọng VieNeu này không có sẵn")
    async with ctx.voice_lock:
        path = await ctx.voice_preview_cache.get_or_synthesize(ctx.tts, VOICE_PREVIEW_TEXT, voice_id, attempt=0)
    return FileResponse(path, media_type="audio/wav")


def _gpu_available() -> bool:
    try:
        import torch  # optional

        return bool(torch.cuda.is_available())
    except Exception:
        return False


# -- device -------------------------------------------------------------------
@router.get("/device")
async def device_status(request: Request) -> dict[str, Any]:
    ctx = ctx_of(request)
    adb = ctx.adb
    if not adb.available:
        return {"adb": False, "error": "Không tìm thấy adb", "devices": [], "busy": ctx.busy_serial}
    try:
        devices = await adb.devices()
    except AdbError as e:
        return {"adb": True, "error": str(e), "devices": [], "busy": ctx.busy_serial}
    return {"adb": True, "error": None, "devices": [d.to_json() for d in devices], "busy": ctx.busy_serial}


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
    _require_free(ctx_of(request), serial)
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


@router.get("/device/{serial}/node-at")
async def device_node_at(request: Request, serial: str, x: int, y: int) -> dict[str, Any]:
    _require_free(ctx_of(request), serial)
    try:
        nodes = parse_dump(await ctx_of(request).adb.dump_ui(serial))
    except AdbError as e:
        raise HTTPException(503, str(e)) from e
    node = node_at(nodes, x, y)
    if node is None:
        raise HTTPException(404, "Không có phần tử nào tại điểm này")
    return node.to_json()


# -- block 2 ------------------------------------------------------------------
class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    package: str = Field(min_length=1)
    open_label: str = Field(min_length=1)
    stop_label: str = Field(min_length=1)
    idle_label: str = Field(min_length=1)
    close_label: str = Field(min_length=1)
    sheet_label: str = ""
    discard_label: str = ""
    pre_delay_s: float = Field(ge=0, le=10)
    post_delay_s: float = Field(ge=0, le=10)
    listen_timeout_s: float = Field(gt=0, le=60)
    result_timeout_s: float = Field(gt=0, le=120)


@router.get("/profiles")
def get_profiles(request: Request) -> list[dict[str, Any]]:
    return [p.to_json() for p in list_profiles(ctx_of(request).profiles_dir)]


@router.put("/profiles/{name}")
def put_profile(request: Request, name: str, body: ProfileIn) -> dict[str, Any]:
    p = AppProfile(**{**body.model_dump(), "name": name})
    save_profile(ctx_of(request).profiles_dir, p)
    return p.to_json()


class AppRunIn(BaseModel):
    serial: str = Field(min_length=1)
    profile: str
    item_ids: list[int] | None = None  # None = every row that passed Block 1


def _start_block2(ctx: AppContext, run_id: int, serial: str, profile: AppProfile) -> str:
    async def job(emit, cancel) -> None:
        ctx.busy_serial = serial
        try:
            dev = await ctx.device(serial)
            await run_block2(ctx.store, run_id, dev, profile, ctx.player, ctx.settings, emit, cancel,
                             shots_dir=ctx.run_dir(run_id))
        finally:
            ctx.busy_serial = None

    try:
        return ctx.runner.start(f"Khối 2 – lần test {run_id}", job)
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


def _profile(ctx: AppContext, name: str) -> AppProfile:
    try:
        return get_profile(ctx.profiles_dir, name)
    except KeyError as e:
        raise HTTPException(404, f"Không có hồ sơ app '{name}'") from e


@router.post("/audio-sets/{set_id}/app-runs")
async def create_app_run(request: Request, set_id: int, body: AppRunIn) -> dict[str, Any]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    profile = _profile(ctx, body.profile)
    if ctx.runner.current() is not None:
        raise HTTPException(409, f"Đang chạy: {ctx.runner.current()['name']}")
    if not ctx.store.summary(set_id).get(ItemStatus.PASSED.value):
        raise HTTPException(422, "Bộ audio chưa có câu Đạt — chạy Khối 1 trước")
    model = version = None
    if ctx.device_factory is None and ctx.adb.available:
        try:
            model = next((d.model for d in await ctx.adb.devices() if d.serial == body.serial), None)
            version = await ctx.adb.app_version(body.serial, profile.package)
        except AdbError:
            pass
    run_id = ctx.store.create_app_run(set_id, body.serial, model, profile.name, version, item_ids=body.item_ids)
    if not ctx.store.app_results(run_id):
        ctx.store.delete_app_run(run_id)
        raise HTTPException(422, "Không có câu Đạt nào trong các case đã chọn")
    return {"id": run_id, "job_id": _start_block2(ctx, run_id, body.serial, profile)}


def _require_run(ctx: AppContext, run_id: int) -> dict[str, Any]:
    run = ctx.store.get_app_run(run_id)
    if run is None:
        raise HTTPException(404, "Không tìm thấy lần test app")
    return run


@router.post("/app-runs/{run_id}/resume")
async def resume_app_run(request: Request, run_id: int) -> dict[str, str]:
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    return {"job_id": _start_block2(ctx, run_id, run["serial"], _profile(ctx, run["profile_name"]))}


def _run_file_base(ctx: AppContext, run: dict[str, Any]) -> str:
    s = ctx.store.get_audio_set(run["audio_set_id"]) or {}
    return f"{_safe_name(s.get('name') or 'bo-audio')}_Phien{run['id']}"


@router.post("/app-runs/{run_id}/form-report")
async def form_report(request: Request, run_id: int) -> FileResponse:
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    out = ctx.reports / f"KetQua_{_run_file_base(ctx, run)}.xlsx"
    await asyncio.to_thread(build_form_report, ctx.store, run_id, out)
    return FileResponse(out, media_type=XLSX_TYPE, filename=out.name)


class ExportZipIn(BaseModel):
    audio: Literal["failed", "all", "selected"] = "failed"
    item_ids: list[int] | None = None  # for audio="selected"


EXPORT_TTL_S = 6 * 3600  # an export nobody downloaded is swept at the next export


def _sweep_exports(ctx: AppContext) -> None:
    now = time.time()
    for token, (path, _) in list(ctx.exports.items()):
        if not path.is_file():
            ctx.exports.pop(token, None)
    for path in ctx.exports_dir.glob("*.zip") if ctx.exports_dir.is_dir() else ():
        if now - path.stat().st_mtime > EXPORT_TTL_S:
            path.unlink(missing_ok=True)


@router.post("/app-runs/{run_id}/export-zip")
async def export_zip(request: Request, run_id: int, body: ExportZipIn) -> dict[str, str]:
    """Build the session zip, then hand out a one-time GET link.

    A plain link lets the browser stream the (up to ~1 GB) file to disk with its own progress bar,
    instead of holding it in a page blob.
    """
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    if body.audio == "selected" and not body.item_ids:
        raise HTTPException(422, "Chưa chọn case nào")
    try:
        profile = get_profile(ctx.profiles_dir, run["profile_name"]).to_json()
    except KeyError:
        profile = None
    _sweep_exports(ctx)
    token = uuid.uuid4().hex
    out = ctx.exports_dir / f"{token}.zip"
    try:
        await asyncio.to_thread(build_session_zip, ctx.store, run_id, ctx.settings, out, body.audio,
                                set(body.item_ids or ()), profile)
    except BaseException:
        out.unlink(missing_ok=True)  # never leave a half-written zip behind
        raise
    ctx.exports[token] = (out, f"{session_root_name(run)}.zip")
    return {"download_url": f"/api/exports/{token}"}


@router.get("/exports/{token}")
def download_export(request: Request, token: str) -> FileResponse:
    ctx = ctx_of(request)
    entry = ctx.exports.pop(token, None) if re.fullmatch(r"[0-9a-f]{32}", token) else None
    if entry is None or not entry[0].is_file():
        raise HTTPException(404, "File xuất không còn — bấm Xuất zip lại")
    path, name = entry
    return FileResponse(path, media_type="application/zip", filename=name,
                        background=BackgroundTask(path.unlink, missing_ok=True))


@router.get("/audio-sets/{set_id}/app-runs")
def list_app_runs(request: Request, set_id: int) -> list[dict[str, Any]]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    return ctx.store.list_app_runs(set_id)


@router.get("/app-runs/{run_id}/results")
def app_run_results(request: Request, run_id: int) -> list[dict[str, Any]]:
    ctx = ctx_of(request)
    _require_run(ctx, run_id)
    return ctx.store.app_results(run_id)


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
