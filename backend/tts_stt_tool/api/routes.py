"""REST API (prefix /api)."""

from __future__ import annotations

import asyncio
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from tts_stt_tool.api.app import AppContext
from tts_stt_tool.config import save_settings
from tts_stt_tool.device.adb import KEYS, AdbError
from tts_stt_tool.device.goios import GoIosError
from tts_stt_tool.device.wda import WdaError
from tts_stt_tool.device.profile import AppProfile, get_profile, list_profiles, save_profile
from tts_stt_tool.device.ui_tree import UiNode, node_at, parse_dump
from tts_stt_tool.input.filters import clean_text, has_words
from tts_stt_tool.input.generic import ColumnMapping, preview_sheet, read_items, sheet_names
from tts_stt_tool.input.testcase_form import InputError
from tts_stt_tool.jobs.runner import JobBusyError
from tts_stt_tool.jobs.runner import Lane as JobLane
from tts_stt_tool.pipeline.block1 import run_generate, run_verify
from tts_stt_tool.pipeline.block2 import Lane, run_block2_multi
from tts_stt_tool.report.audio_set_zip import PackError, build_audio_set_zip, import_audio_set_zip, pack_name
from tts_stt_tool.report.device_label import device_tag
from tts_stt_tool.report.excel import build_block1_report, export_block1_csv
from tts_stt_tool.report.result_export import build_result_report, result_suffix
from tts_stt_tool.report.session_zip import build_session_zip, session_root_name
from tts_stt_tool.store.db import ItemStatus
from tts_stt_tool.stt.wyoming_client import WyomingStt
from tts_stt_tool.tts.base import VoiceInfo
from tts_stt_tool.tts.speed import MAX_SPEED, MIN_SPEED

router = APIRouter()
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"
VOICE_PREVIEW_TEXT = "Xin chào, bạn muốn bật quạt hay điều chỉnh nhiệt độ?"


def ctx_of(request: Request) -> AppContext:
    return request.app.state.ctx


def _require_free(ctx: AppContext, serial: str) -> None:
    """Manual taps / pin dumps would break the sentence a block 2 job is running on this phone."""
    if serial in ctx.busy_serials:
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
        sheets = await asyncio.to_thread(sheet_names, path)
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    return {"file_id": file_id, "sheets": sheets}


class PreviewIn(BaseModel):
    file_id: str
    sheet: str | None = None
    header_row: int = Field(1, ge=1)


@router.post("/files/preview")
async def preview_file(request: Request, body: PreviewIn) -> dict[str, Any]:
    path = _upload_path(ctx_of(request), body.file_id)
    try:
        pv = await asyncio.to_thread(preview_sheet, path, body.sheet, body.header_row)
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    return {"columns": pv.columns, "rows": pv.rows, "row_count": pv.row_count, "suggestions": pv.suggestions}


class MappingIn(BaseModel):
    text_col: str
    header_row: int = Field(1, ge=1)
    id_col: str | None = None
    region_col: str | None = None
    region_value: str | None = None
    expected_col: str | None = None
    turn_col: str | None = None


class AudioSetIn(BaseModel):
    file_id: str
    sheets: list[str]
    name: str
    mapping: MappingIn


@router.post("/audio-sets")
async def create_audio_set(request: Request, body: AudioSetIn) -> dict[str, int]:
    ctx = ctx_of(request)
    path = _upload_path(ctx, body.file_id)
    m = body.mapping
    if m.region_col and m.region_value:
        raise HTTPException(422, "Chọn cột vùng miền hoặc giá trị cố định, không chọn cả hai")
    if path.suffix.lower() != ".csv" and not body.sheets:
        raise HTTPException(422, "Chọn ít nhất một sheet")
    try:
        items = await asyncio.to_thread(read_items, path, body.sheets, ColumnMapping(**m.model_dump()))
    except InputError as e:
        raise HTTPException(422, str(e)) from e
    if not items:
        raise HTTPException(422, "Không có dòng dữ liệu nào")
    source = body.file_id.split("_", 1)[-1]
    set_id = ctx.store.create_audio_set(
        body.name or source, source, body.sheets, ctx.settings.voice, items,
        voice_trung=ctx.settings.voice_trung, voice_nam=ctx.settings.voice_nam,
    )
    kept: str | None = None
    if path.suffix.lower() != ".csv":
        dest = ctx.sources / str(set_id) / _safe_name(source)

        def keep() -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)

        await asyncio.to_thread(keep)
        kept = str(dest)
    ctx.store.set_source(set_id, kept, m.header_row)
    return {"id": set_id}


@router.get("/audio-sets")
def list_audio_sets(request: Request) -> list[dict[str, Any]]:
    ctx = ctx_of(request)
    return [{**s, "summary": ctx.store.summary(s["id"])} for s in ctx.store.list_audio_sets()]


def _require_no_job(ctx: AppContext, what: str, set_id: int | None = None) -> None:
    """409 while a job runs — any job, or with ``set_id`` only one on that set."""
    if set_id is None:
        job = ctx.runner.busy()
    else:
        job = next((j for j in ctx.runner.jobs() if j["set_id"] == set_id), None)
    if job is not None:  # a running job may be writing rows or WAVs
        raise HTTPException(409, f"Đang chạy: {job['name']} — dừng job trước khi {what}")


@router.post("/audio-sets/import")
async def import_audio_set(request: Request, file: UploadFile) -> dict[str, int]:
    """Load a zip made by "Xuất" as a NEW audio set (never overwrites one)."""
    ctx = ctx_of(request)
    _require_no_job(ctx, "nạp bộ audio")
    ctx.uploads.mkdir(parents=True, exist_ok=True)
    tmp = ctx.uploads / f"{uuid.uuid4().hex[:8]}_import.zip"
    try:
        tmp.write_bytes(await file.read())
        try:
            return await asyncio.to_thread(import_audio_set_zip, ctx.store, tmp, ctx.cache.root)
        except PackError as e:
            raise HTTPException(422, str(e)) from e
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/audio-sets/{set_id}/export")
async def export_audio_set(request: Request, set_id: int) -> dict[str, str]:
    """Build the set's zip (manifest + WAVs), then hand out a one-time GET link like the session zip."""
    ctx = ctx_of(request)
    audio_set = _require_set(ctx, set_id)
    _require_no_job(ctx, "xuất bộ audio", set_id)
    _sweep_exports(ctx)
    ctx.exports_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out = ctx.exports_dir / f"{token}.zip"
    try:
        await asyncio.to_thread(build_audio_set_zip, ctx.store, set_id, out)
    except BaseException:
        out.unlink(missing_ok=True)  # never leave a half-written zip behind
        raise
    ctx.exports[token] = (out, pack_name(audio_set))
    return {"download_url": f"/api/exports/{token}"}


@router.delete("/audio-sets/{set_id}")
async def delete_audio_set(request: Request, set_id: int) -> dict[str, bool]:
    """Delete a set, its app runs and results, their screenshots, and WAVs no other set uses."""
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    # Every job, not only this set's: sets share cached WAVs, and a job elsewhere may be about to reuse one.
    _require_no_job(ctx, "xóa")
    gone = ctx.store.delete_audio_set(set_id)
    if gone is None:
        raise HTTPException(404, "Không tìm thấy bộ audio")

    def cleanup() -> None:
        shutil.rmtree(ctx.sources / str(set_id), ignore_errors=True)
        for run_id in gone["run_ids"]:
            shutil.rmtree(ctx.run_dir(run_id), ignore_errors=True)
        cache_root = ctx.cache.root.resolve()
        for p in map(Path, gone["audio_paths"]):
            if p.resolve().parent == cache_root:  # never touch files outside the audio cache
                p.unlink(missing_ok=True)

    await asyncio.to_thread(cleanup)
    return {"ok": True}


def _empty_dir(path: Path) -> None:
    """Remove what is inside ``path`` but keep the folder (the audio cache writes into it directly)."""
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


@router.delete("/data")
async def clear_all_data(request: Request) -> dict[str, Any]:
    """Delete every audio set and the files they produced: WAVs, reports, uploads, screenshots.

    Settings, app profiles, wyoming models and voice previews are kept.
    """
    ctx = ctx_of(request)
    _require_no_job(ctx, "xóa")  # a running job may be writing rows or files
    count = ctx.store.delete_all_audio_sets()
    ctx.exports.clear()

    def cleanup() -> None:
        for d in (ctx.cache.root, ctx.reports, ctx.uploads, ctx.sources, ctx.settings.data_dir / "app_runs"):
            _empty_dir(d)

    await asyncio.to_thread(cleanup)
    return {"ok": True, "sets": count}


@router.delete("/progress")
async def reset_progress(request: Request) -> dict[str, Any]:
    """Clear generated audio, STT/MER results and app runs of every set; imported rows are kept as "Chờ"."""
    ctx = ctx_of(request)
    _require_no_job(ctx, "xóa")  # a running job may be writing rows or files
    count = ctx.store.reset_progress()
    ctx.exports.clear()

    def cleanup() -> None:
        # No row points at a WAV any more, so the whole audio cache is stale.
        for d in (ctx.cache.root, ctx.reports, ctx.settings.data_dir / "app_runs"):
            _empty_dir(d)

    await asyncio.to_thread(cleanup)
    return {"ok": True, "items": count}


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


def _require_lane_free(ctx: AppContext, lane: JobLane, set_id: int, exclusive: bool = False) -> None:
    """409 before any other check: the lane is taken, or a clashing job of the other lane is on this set."""
    try:
        ctx.runner.check(lane, set_id, exclusive)
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


def _start(ctx: AppContext, name: str, job, set_id: int, exclusive: bool = False) -> dict[str, str]:
    """Start a Block 1 job beside a Block 2 job; ``exclusive`` (Sinh lại) waits for Block 2 on this set."""
    try:
        return {"job_id": ctx.runner.start(name, job, lane="block1", set_id=set_id, exclusive=exclusive)}
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


# async handlers: runner.start needs the running event loop
@router.post("/audio-sets/{set_id}/generate")
async def start_generate(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    _require_lane_free(ctx, "block1", set_id)
    ids = body.item_ids if body else None
    if not ctx.store.items_for_generate(set_id, ids):
        raise HTTPException(422, "Không có câu nào cần sinh audio")

    async def job(emit, cancel) -> None:
        await run_generate(ctx.store, set_id, ctx.tts, ctx.cache, ctx.settings, emit, cancel, item_ids=ids)

    return _start(ctx, f"Sinh audio – bộ {set_id}", job, set_id)


@router.post("/audio-sets/{set_id}/regenerate")
async def start_regenerate(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    _require_lane_free(ctx, "block1", set_id, exclusive=True)  # swaps WAVs a Block 2 run may be playing
    ids = body.item_ids if body else None
    if not ctx.store.items_for_regenerate(set_id, ids):
        raise HTTPException(422, "Không có câu nào để sinh lại")

    async def job(emit, cancel) -> None:
        await run_generate(ctx.store, set_id, ctx.tts, ctx.cache, ctx.settings, emit, cancel,
                           item_ids=ids, regenerate=True)

    return _start(ctx, f"Sinh lại – bộ {set_id}", job, set_id, exclusive=True)


@router.post("/audio-sets/{set_id}/verify")
async def start_verify(request: Request, set_id: int, body: ItemIdsIn | None = None) -> dict[str, str]:
    ctx = ctx_of(request)
    _require_set(ctx, set_id)
    _require_lane_free(ctx, "block1", set_id)
    ids = body.item_ids if body else None
    if not ctx.store.items_for_verify(set_id, ids):
        raise HTTPException(422, "Không có câu nào có audio để verify")

    async def job(emit, cancel) -> None:
        if ctx.wyoming is not None:
            await ctx.wyoming.ensure_running()
        await run_verify(ctx.store, set_id, ctx.stt, ctx.settings, emit, cancel, item_ids=ids)

    return _start(ctx, f"Verify – bộ {set_id}", job, set_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict[str, bool]:
    if not ctx_of(request).runner.cancel(job_id):
        raise HTTPException(404, "Không có job này")
    return {"ok": True}


@router.get("/jobs/current")
def current_job(request: Request) -> dict[str, Any] | None:
    """The oldest running job (kept for old clients; /jobs lists them all)."""
    return ctx_of(request).runner.busy()


@router.get("/jobs")
def list_jobs(request: Request) -> list[dict[str, Any]]:
    return ctx_of(request).runner.jobs()


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
        base += f"_Phien{app_run_id}_{_safe_name(device_tag(run))}"  # two phones of one job: tell them apart
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
    voice_trung: str | None = None
    voice_nam: str | None = None
    voice_speed: float = Field(default=1.0, ge=MIN_SPEED, le=MAX_SPEED)
    max_regen: int = Field(ge=0, le=10)
    wer_threshold: float = Field(ge=0, le=1)
    # Block 2 default; changed from the app run toolbar, so the Block 1 form may leave it out
    app_wer_threshold: float | None = Field(default=None, ge=0, le=1)
    reject_warn_ratio: float = Field(ge=0, le=1)
    wyoming_host: str
    wyoming_port: int = Field(ge=1, le=65535)
    stt_timeout_s: float = Field(gt=0, le=600)
    wyoming_cmd: list[str] = []
    port: int = Field(ge=1, le=65535)
    wda_url: str = Field(default="http://127.0.0.1:8100", pattern=r"^https?://")  # read at startup
    # Echoed back by the settings form; ignored here — CPU/GPU changes go through PUT /api/tts/device,
    # which checks CUDA first.
    tts_device: str | None = None


@router.put("/settings")
def put_settings(request: Request, body: SettingsIn) -> dict[str, Any]:
    ctx = ctx_of(request)
    skip = {"tts_device"} | ({"app_wer_threshold"} if body.app_wer_threshold is None else set())
    for k, v in body.model_dump(exclude=skip).items():
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
async def voice_preview(request: Request, voice_id: str,
                        speed: float = Query(default=1.0, ge=MIN_SPEED, le=MAX_SPEED)) -> FileResponse:
    ctx = ctx_of(request)
    if not any(voice.id == voice_id for voice in await _available_voices(ctx)):
        raise HTTPException(404, "Giọng VieNeu này không có sẵn")
    async with ctx.voice_lock:
        path = await ctx.voice_preview_cache.get_or_synthesize(ctx.tts, VOICE_PREVIEW_TEXT, voice_id, attempt=0,
                                                               speed=speed)
    return FileResponse(path, media_type="audio/wav")


# -- TTS device (CPU / GPU) ----------------------------------------------------
async def _tts_device_json(ctx: AppContext, refresh: bool = False) -> dict[str, Any]:
    probe = await ctx.gpu.probe(refresh=refresh)
    return {
        "device": ctx.settings.tts_device,
        "active": getattr(ctx.tts, "active_device", None),
        "load_error": getattr(ctx.tts, "load_error", None),
        "nvidia": probe.nvidia,
        "gpu_name": probe.gpu_name,
        "torch_cuda": probe.torch_cuda,
        "uv": ctx.gpu.can_install,
        "install": ctx.gpu.install_state(),
    }


def _apply_tts_device(ctx: AppContext, device: str) -> None:
    ctx.settings.tts_device = device
    save_settings(ctx.settings)
    set_device = getattr(ctx.tts, "set_device", None)
    if set_device is not None:
        set_device(device)


@router.get("/tts/device")
async def get_tts_device(request: Request) -> dict[str, Any]:
    return await _tts_device_json(ctx_of(request))


class TtsDeviceIn(BaseModel):
    device: Literal["cpu", "cuda"]


@router.put("/tts/device")
async def put_tts_device(request: Request, body: TtsDeviceIn) -> dict[str, Any]:
    ctx = ctx_of(request)
    if ctx.runner.busy() is not None:  # the model is reloaded on switch; never under a running job
        raise HTTPException(409, "Đang có tác vụ chạy, đợi xong rồi đổi")
    if body.device == "cuda":
        probe = await ctx.gpu.probe(refresh=True)  # CUDA may have been installed by hand meanwhile
        if not probe.nvidia:
            raise HTTPException(409, "Máy không có GPU NVIDIA")
        if not probe.torch_cuda:
            raise HTTPException(409, "Chưa có PyTorch CUDA")
    if body.device != ctx.settings.tts_device:
        _apply_tts_device(ctx, body.device)
    return await _tts_device_json(ctx)


@router.post("/tts/install-cuda")
async def install_cuda(request: Request) -> dict[str, Any]:
    ctx = ctx_of(request)
    if not (await ctx.gpu.probe()).nvidia:
        raise HTTPException(400, "Máy không có GPU NVIDIA")

    def on_done() -> None:
        if ctx.runner.busy() is None:  # else the user switches once the job ends
            _apply_tts_device(ctx, "cuda")

    ctx.gpu.start_install(on_done)
    return await _tts_device_json(ctx)


# -- device -------------------------------------------------------------------
DEVICE_ERRORS = (AdbError, WdaError, GoIosError)


async def _is_ios(ctx: AppContext, serial: str) -> bool:
    return ctx.device_factory is None and await ctx.ios.is_ios(serial)


@router.get("/device")
async def device_status(request: Request) -> dict[str, Any]:
    """Android phones (adb) and iPhones (go-ios + WebDriverAgent), each with its ``platform``."""
    ctx = ctx_of(request)
    adb, errors, devices = ctx.adb, [], []
    if adb.available:
        try:
            devices += [d.to_json() | {"platform": "android"} for d in await adb.devices()]
        except AdbError as e:
            errors.append(str(e))
    if ctx.ios.available:
        try:
            devices += await ctx.ios.devices()
        except DEVICE_ERRORS as e:
            errors.append(f"iPhone: {e}")
    if not adb.available and not ctx.ios.available:
        errors.append("Không tìm thấy adb")
    return {"adb": adb.available, "ios": ctx.ios.available, "error": "; ".join(errors) or None,
            "devices": devices, "busy": sorted(ctx.busy_serials)}


def _launcher(ctx: AppContext):
    if ctx.wda_launcher is None:
        raise HTTPException(503, "Không tìm thấy go-ios (vendor/go-ios/ios.exe)")
    return ctx.wda_launcher


@router.get("/ios/connect")
async def ios_connect_status(request: Request) -> dict[str, Any]:
    """State of the "Kết nối iPhone" button: idle | starting | running | error (+ step, error, detail)."""
    return _launcher(ctx_of(request)).snapshot()


@router.post("/ios/connect")
async def ios_connect(request: Request) -> dict[str, Any]:
    """Start WebDriverAgent on the USB iPhone and forward its port, in the background."""
    return _launcher(ctx_of(request)).start()


@router.post("/ios/disconnect")
async def ios_disconnect(request: Request) -> dict[str, Any]:
    ctx = ctx_of(request)
    if any([await ctx.ios.is_ios(s) for s in ctx.busy_serials]):
        raise HTTPException(409, "Đang chạy test app trên iPhone — dừng job trước")
    return _launcher(ctx).stop()


@router.get("/device/{serial}/screen")
async def device_screen(request: Request, serial: str) -> Response:
    ctx = ctx_of(request)
    try:
        png = await (ctx.ios.screencap(serial) if await _is_ios(ctx, serial) else ctx.adb.screencap(serial))
    except DEVICE_ERRORS as e:
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
    """Coordinates are screenshot pixels (an iPhone converts them to points)."""
    ctx = ctx_of(request)
    _require_free(ctx, serial)
    if body.action in ("tap", "swipe") and None in (body.x, body.y):
        raise HTTPException(422, "Thiếu toạ độ")
    if body.action == "swipe" and None in (body.x2, body.y2):
        raise HTTPException(422, "Thiếu toạ độ")
    if body.action == "key" and body.key not in KEYS:
        raise HTTPException(422, "Phím không hỗ trợ")
    if body.action == "text" and not body.text:
        raise HTTPException(422, "Thiếu nội dung")
    try:
        if await _is_ios(ctx, serial):
            ios = ctx.ios
            if body.action == "tap":
                await ios.tap_px(serial, body.x, body.y)  # type: ignore[arg-type]
            elif body.action == "swipe":
                await ios.swipe_px(serial, body.x, body.y, body.x2, body.y2, body.duration_ms)  # type: ignore[arg-type]
            elif body.action == "key":
                await (await ios.driver(serial)).key(body.key)  # type: ignore[arg-type]
            else:
                await (await ios.driver(serial)).text(body.text)  # type: ignore[arg-type]
            return {"ok": True}
        adb = ctx.adb
        if body.action == "tap":
            await adb.tap(serial, body.x, body.y)  # type: ignore[arg-type]
        elif body.action == "swipe":
            await adb.swipe(serial, body.x, body.y, body.x2, body.y2, body.duration_ms)  # type: ignore[arg-type]
        elif body.action == "key":
            await adb.key(serial, KEYS[body.key])  # type: ignore[index]
        else:
            await adb.text(serial, body.text)  # type: ignore[arg-type]
    except DEVICE_ERRORS as e:
        raise HTTPException(503, str(e)) from e
    return {"ok": True}


@router.get("/device/{serial}/node-at")
async def device_node_at(request: Request, serial: str, x: int, y: int) -> dict[str, Any]:
    ctx = ctx_of(request)
    _require_free(ctx, serial)
    try:
        if await _is_ios(ctx, serial):
            nodes, scale = await ctx.ios.nodes_px(serial)
            nodes = [UiNode(n.text, n.desc, n.cls, tuple(round(v * scale) for v in n.bounds), n.clickable)  # type: ignore[misc]
                     for n in nodes]
        else:
            nodes = parse_dump(await ctx.adb.dump_ui(serial))
    except DEVICE_ERRORS as e:
        raise HTTPException(503, str(e)) from e
    node = node_at(nodes, x, y)
    if node is None:
        raise HTTPException(404, "Không có phần tử nào tại điểm này")
    return node.to_json()


async def _device_model_version(ctx: AppContext, serial: str, package: str) -> tuple[str | None, str | None]:
    """Phone name and app version for the run record (best effort)."""
    if ctx.device_factory is not None:
        return None, None
    try:
        if await ctx.ios.is_ios(serial):
            return await ctx.ios.model(serial), await ctx.ios.app_version(serial, package)
        if ctx.adb.available:
            model = next((d.model for d in await ctx.adb.devices() if d.serial == serial), None)
            return model, await ctx.adb.app_version(serial, package)
    except DEVICE_ERRORS:
        pass
    return None, None


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
    heard_prefix: str = ""
    not_heard_label: str = "Chưa nghe rõ"
    pre_delay_s: float = Field(ge=0, le=10)
    post_delay_s: float = Field(ge=0, le=10)
    listen_timeout_s: float = Field(gt=0, le=60)
    result_timeout_s: float = Field(gt=0, le=120)
    between_delay_s: float = Field(default=0.0, ge=0, le=60)


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
    serial2: str | None = None  # a second phone: both hear each sentence from one playback


def _start_block2(ctx: AppContext, set_id: int, runs: list[tuple[int, str]], profile: AppProfile) -> str:
    """Start a Block 2 job on one or two phones (``runs`` = [(run id, serial)]).

    It runs beside a Block 1 job (not beside "Sinh lại" on this set).
    """
    serials = [s for _, s in runs]

    async def job(emit, cancel) -> None:
        ctx.busy_serials.update(serials)
        try:
            lanes = []
            for run_id, serial in runs:
                run = ctx.store.get_app_run(run_id) or {}
                lanes.append(Lane(run_id, await ctx.device(serial), ctx.run_dir(run_id),
                                  name=run.get("device_model") or serial))
            await run_block2_multi(ctx.store, lanes, profile, ctx.player, ctx.settings, emit, cancel)
        finally:
            ctx.busy_serials.difference_update(serials)

    name = "Khối 2 – lần test " + " + ".join(str(r) for r, _ in runs)
    try:
        return ctx.runner.start(name, job, lane="block2", set_id=set_id)
    except JobBusyError as e:
        raise HTTPException(409, str(e)) from e


async def _connected(ctx: AppContext, serial: str) -> bool:
    """Whether ``serial`` is plugged in and ready to drive (tests inject devices: always)."""
    if ctx.device_factory is not None:
        return True
    try:
        if ctx.adb.available and any(d.serial == serial and d.state == "device" for d in await ctx.adb.devices()):
            return True
        return ctx.ios.available and any(d["serial"] == serial and d["state"] == "device"
                                         for d in await ctx.ios.devices())
    except DEVICE_ERRORS:
        return False


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
    _require_lane_free(ctx, "block2", set_id)
    if body.serial2 is not None and body.serial2 == body.serial:
        raise HTTPException(422, "Hai máy phải khác nhau")
    if not ctx.store.count_with_audio(set_id):
        raise HTTPException(422, "Bộ audio chưa có câu nào có audio — sinh audio ở Khối 1 trước")
    serials = [body.serial] + ([body.serial2] if body.serial2 else [])
    runs: list[tuple[int, str]] = []
    for serial in serials:
        model, version = await _device_model_version(ctx, serial, profile.package)
        platform = "ios" if await _is_ios(ctx, serial) else "android"
        runs.append((ctx.store.create_app_run(set_id, serial, model, profile.name, version, item_ids=body.item_ids,
                                              wer_threshold=ctx.settings.app_wer_threshold, platform=platform),
                     serial))
    if not ctx.store.app_results(runs[0][0]):
        for run_id, _ in runs:
            ctx.store.delete_app_run(run_id)
        raise HTTPException(422, "Không có câu nào có audio trong các case đã chọn")
    if len(runs) == 2:
        ctx.store.link_pair(runs[0][0], runs[1][0])
    return {"id": runs[0][0], "pair_id": runs[1][0] if len(runs) == 2 else None,
            "job_id": _start_block2(ctx, set_id, runs, profile)}


def _require_run(ctx: AppContext, run_id: int) -> dict[str, Any]:
    run = ctx.store.get_app_run(run_id)
    if run is None:
        raise HTTPException(404, "Không tìm thấy lần test app")
    return run


class ThresholdIn(BaseModel):
    wer_threshold: float = Field(ge=0, le=1)


@router.put("/app-runs/{run_id}/threshold")
def set_run_threshold(request: Request, run_id: int, body: ThresholdIn) -> dict[str, Any]:
    """Grade this run again with another MER threshold; the next new run starts with it too."""
    ctx = ctx_of(request)
    _require_run(ctx, run_id)
    ctx.store.set_app_threshold(run_id, body.wer_threshold)
    if ctx.settings.app_wer_threshold != body.wer_threshold:
        ctx.settings.app_wer_threshold = body.wer_threshold
        save_settings(ctx.settings)
    return {**(ctx.store.get_app_run(run_id) or {}), "summary": ctx.store.app_summary(run_id)}


@router.post("/app-runs/{run_id}/resume")
async def resume_app_run(request: Request, run_id: int) -> dict[str, str]:
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    runs = [(run_id, run["serial"])]
    pair = ctx.store.get_app_run(run["pair_run_id"]) if run.get("pair_run_id") else None
    if pair is not None and await _connected(ctx, pair["serial"]):
        runs.append((pair["id"], pair["serial"]))  # the other phone of this job is here too: go on together
    return {"job_id": _start_block2(ctx, run["audio_set_id"], runs, _profile(ctx, run["profile_name"]))}


class RerunIn(BaseModel):
    serial: str = Field(min_length=1)
    item_ids: list[int] = Field(min_length=1)


@router.post("/app-runs/{run_id}/rerun")
async def rerun_app_run(request: Request, run_id: int, body: RerunIn) -> dict[str, str]:
    """Run some cases again inside this run: the other results stay, the old ones go to history."""
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    profile = _profile(ctx, run["profile_name"])
    _require_lane_free(ctx, "block2", run["audio_set_id"])
    if body.serial != run["serial"]:
        raise HTTPException(409, f"Lần test #{run_id} chạy trên máy {run['device_model'] or run['serial']}"
                                 " — chọn máy đó, hoặc tạo lần test mới")
    if run["app_version"]:
        _, version = await _device_model_version(ctx, body.serial, profile.package)
        if version and version != run["app_version"]:
            raise HTTPException(409, f"App đã đổi phiên bản ({run['app_version']} → {version})"
                                     f" so với lần test #{run_id} — tạo lần test mới")
    if not ctx.store.rerun_app_results(run_id, body.item_ids):
        raise HTTPException(422, "Không có câu nào có audio trong các case đã chọn")
    return {"job_id": _start_block2(ctx, run["audio_set_id"], [(run_id, run["serial"])], profile)}


def _run_file_base(ctx: AppContext, run: dict[str, Any]) -> str:
    s = ctx.store.get_audio_set(run["audio_set_id"]) or {}
    return f"{_safe_name(s.get('name') or 'bo-audio')}_Phien{run['id']}_{_safe_name(device_tag(run))}"


@router.post("/app-runs/{run_id}/form-report")
async def form_report(request: Request, run_id: int) -> FileResponse:
    ctx = ctx_of(request)
    run = _require_run(ctx, run_id)
    suffix = result_suffix(ctx.store.get_audio_set(run["audio_set_id"]) or {})
    out = ctx.reports / f"KetQua_{_run_file_base(ctx, run)}{suffix}"
    await asyncio.to_thread(build_result_report, ctx.store, run_id, out)
    return FileResponse(out, media_type=XLSM_TYPE if suffix == ".xlsm" else XLSX_TYPE, filename=out.name)


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
    return {"wyoming": up, "wyoming_error": ctx.wyoming_error, "gpu": (await ctx.gpu.probe()).torch_cuda,
            "job": ctx.runner.busy(), "jobs": ctx.runner.jobs()}
