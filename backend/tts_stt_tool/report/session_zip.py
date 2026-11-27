"""One app run as a zip: one folder per testcase with everything about it (spec §5.6)."""

from __future__ import annotations

import json
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Literal

from tts_stt_tool.tts.regions import voices_label
from tts_stt_tool.config import Settings
from tts_stt_tool.report.excel import build_block1_report, format_ops
from tts_stt_tool.report.result_export import build_result_report, result_suffix
from tts_stt_tool.report.layout import case_folders, safe_component, turn_prefix
from tts_stt_tool.store.db import AppStatus, Store

AudioChoice = Literal["failed", "all", "selected"]
_FAILED = (AppStatus.FAILED.value, AppStatus.OP_ERROR.value)
_STORED = (".wav", ".png")  # already compressed / not worth deflating


def session_root_name(run: dict[str, Any]) -> str:
    stamp = (run.get("created_at") or "")[:16]  # 2026-11-20T15:30
    day, _, clock = stamp.partition("T")
    return f"Phien{run['id']}_{day}_{clock.replace(':', '')}_{safe_component(run.get('device_model') or run.get('serial') or '')}"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _result_text(r: dict[str, Any], audio_missing: bool) -> str:
    tested = r["status"] in (AppStatus.PASSED.value, AppStatus.FAILED.value)
    lines = [
        ("TC_ID", r.get("tc_id")), ("Sheet", r.get("sheet")), ("Lượt", r.get("turn")),
        ("Câu gốc", r.get("text_raw")), ("Câu đã đọc", r.get("text_tts")), ("Verify audio", r.get("verify")),
        ("Câu app nghe", (r.get("app_text") or "(app không trả câu)") if tested else ""),
        ("Kết quả", r["status"]), ("MER", _pct(r.get("wer"))), ("CER", _pct(r.get("cer"))),
        ("Từ sai", format_ops(r.get("ops") or [])),
    ]
    if r.get("error"):
        lines.append(("Lỗi", r["error"]))
    lines.append(("Thời gian", r.get("updated_at")))
    if audio_missing:
        lines.append(("Ghi chú", "Không tìm thấy file audio"))
    return "\n".join(f"{k}: {v if v is not None else ''}" for k, v in lines) + "\n"


def _session_info(store: Store, run: dict[str, Any], settings: Settings, results: list[dict[str, Any]],
                  audio: AudioChoice, selected: set[int], profile: dict | None) -> str:
    s = store.get_audio_set(run["audio_set_id"]) or {}
    summary = store.app_summary(run["id"])
    choice = {"failed": "Chỉ case Sai / Lỗi thao tác", "all": "Tất cả",
              "selected": f"Các case đang chọn ({len(selected)})"}[audio]
    ends = [r["updated_at"] for r in results if r.get("updated_at") and r["status"] != AppStatus.PENDING.value]
    lines = [
        f"Phiên test: #{run['id']}",
        f"Bộ audio: {s.get('name', '')}",
        f"File nguồn: {s.get('source_file', '')}",
        f"Giọng: {voices_label(s if s.get('voice') else settings)}",
        f"Thiết bị: {run.get('device_model') or 'Android'} ({run.get('serial')})",
        f"Hồ sơ app: {run.get('profile_name')}",
        f"Phiên bản app: {run.get('app_version') or '—'}",
        f"Bắt đầu: {run.get('created_at')}",
        f"Kết thúc: {max(ends) if ends else '—'}",
        f"Ngưỡng MER: {settings.wer_threshold:g}",
        f"Số câu: {len(results)}",
        *(f"{st.value}: {summary.get(st.value, 0)}" for st in AppStatus),
        f"Audio kèm theo: {choice}",
    ]
    if profile is not None:
        lines += ["", "Hồ sơ app (JSON):", json.dumps(profile, ensure_ascii=False, indent=2)]
    return "\n".join(lines) + "\n"


def _wants_audio(r: dict[str, Any], audio: AudioChoice, selected: set[int]) -> bool:
    if audio == "all":
        return True
    if audio == "selected":
        return r["item_id"] in selected
    return r["status"] in _FAILED


def build_session_zip(
    store: Store,
    run_id: int,
    settings: Settings,
    out_path: Path,
    audio: AudioChoice = "failed",
    selected_item_ids: set[int] | None = None,
    profile: dict | None = None,
) -> Path:
    run = store.get_app_run(run_id)
    if run is None:
        raise KeyError(run_id)
    selected = set(selected_item_ids or ())
    s = store.get_audio_set(run["audio_set_id"]) or {}
    results = store.app_results(run_id)
    folders = case_folders(results)
    root = session_root_name(run)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def text(z: zipfile.ZipFile, name: str, body: str) -> None:
        z.writestr(zipfile.ZipInfo(name, date_time=time.localtime()[:6]), body.encode("utf-8-sig"),
                   compress_type=zipfile.ZIP_DEFLATED)

    def file(z: zipfile.ZipFile, name: str, src: Path) -> None:
        mode = zipfile.ZIP_STORED if src.suffix.lower() in _STORED else zipfile.ZIP_DEFLATED
        z.write(src, name, compress_type=mode)

    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out_path, "w") as z:
        suffix = result_suffix(s)
        form = build_result_report(store, run_id, Path(tmp) / f"form{suffix}")
        file(z, f"{root}/KetQua_{safe_component(s.get('name') or 'bo-audio')}_Phien{run_id}{suffix}", form)
        overview = build_block1_report(store, run["audio_set_id"], settings, Path(tmp) / "overview.xlsx", run_id)
        file(z, f"{root}/TongQuan.xlsx", overview)
        text(z, f"{root}/thong_tin_phien.txt", _session_info(store, run, settings, results, audio, selected, profile))
        for r in results:
            base = f"{root}/{folders[r['id']]}/{turn_prefix(r.get('turn'))}"
            wav = Path(r["audio_path"]) if r.get("audio_path") else None
            missing = False
            if _wants_audio(r, audio, selected):
                if wav is not None and wav.is_file():
                    file(z, base + "audio.wav", wav)
                else:
                    missing = True
            text(z, base + "ketqua.txt", _result_text(r, missing))
            if r.get("log"):
                text(z, base + "log.txt", r["log"] + "\n")
            shot = Path(r["screenshot_path"]) if r.get("screenshot_path") else None
            if shot is not None and shot.is_file():
                file(z, base + "manhinh.png", shot)
    return out_path


