"""Block 2: speak each generated sentence (verified or not) to the real app and read what it heard."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.device.adb import Adb
from tts_stt_tool.device.player import AudioPlayer
from tts_stt_tool.device.profile import AppProfile
from tts_stt_tool.device.ui_tree import UiNode, bubble_labels, find, heard_text, new_bubble_after, parse_dump
from tts_stt_tool.jobs.runner import Emit, ProgressEvent
from tts_stt_tool.store.db import AppStatus, Store

_LOG = logging.getLogger(__name__)
POLL_S = 0.4
MIC_POLL_S = 0.15
Sleep = Callable[[float], Awaitable[None]]


class OperationError(Exception):
    """The tool could not drive the app (not an app recognition error)."""


class DeviceDriver(Protocol):
    screen_w: int

    async def nodes(self) -> list[UiNode]: ...

    async def tap(self, x: int, y: int) -> None: ...

    async def back(self) -> None: ...

    async def launch(self, package: str) -> None: ...

    async def mic_active(self) -> bool | None:
        """Whether the microphone is recording right now; None if the device cannot tell."""
        ...

    async def screencap(self) -> bytes:
        """PNG of the current screen."""
        ...


class AdbDriver:
    """DeviceDriver over the stock adb binary."""

    def __init__(self, adb: Adb, serial: str, screen_w: int) -> None:
        self.adb, self.serial, self.screen_w = adb, serial, screen_w

    @classmethod
    async def connect(cls, adb: Adb, serial: str) -> AdbDriver:
        w, _ = await adb.screen_size(serial)
        return cls(adb, serial, w)

    async def nodes(self) -> list[UiNode]:
        return parse_dump(await self.adb.dump_ui(self.serial))

    async def tap(self, x: int, y: int) -> None:
        await self.adb.tap(self.serial, x, y)

    async def back(self) -> None:
        await self.adb.key(self.serial, "KEYCODE_BACK")

    async def launch(self, package: str) -> None:
        await self.adb.launch(self.serial, package)

    async def mic_active(self) -> bool | None:
        try:
            return await self.adb.mic_active(self.serial)
        except Exception:  # dumpsys not permitted on some builds -> fall back to fixed delay
            return None

    async def screencap(self) -> bytes:
        return await self.adb.screencap(self.serial)


async def _try_screencap(dev: DeviceDriver, log: list[str]) -> bytes | None:
    """Evidence of a failure; a capture problem must never cost the sentence its result."""
    try:
        png = await dev.screencap()
    except Exception as e:  # noqa: BLE001 — locked phone, adb hiccup, a driver without screencap
        log.append(f"Không chụp được màn hình: {e or type(e).__name__}")
        return None
    log.append("Chụp màn hình")
    return png


@dataclass
class AppCapture:
    text: str | None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    bubbles: list[str] = field(default_factory=list)  # user bubbles on screen at the end
    screenshot: bytes | None = None  # PNG taken before closing the sheet when the text is wrong
    not_heard: bool = False  # the app said "Chưa nghe rõ" (nothing caught)


async def _wait_for(dev: DeviceDriver, label: str, timeout_s: float, sleep: Sleep) -> list[UiNode] | None:
    async for nodes in _poll(dev, timeout_s, sleep):
        if find(nodes, label):
            return nodes
    return None


async def _tap(dev: DeviceDriver, node: UiNode, log: list[str]) -> None:
    x, y = node.center
    log.append(f"Bấm '{node.label.split(chr(10), 1)[0]}' ({x},{y})")  # iOS repeats labels on a 2nd line
    await dev.tap(x, y)


async def ensure_home(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> list[UiNode]:
    """Get back to the screen with the mic button using Back (never stale coordinate taps).

    A task form (opened by speaking, or by a stray tap) asks "Bỏ thay đổi?" on Back -> take the
    discard button, never "Giữ nháp" (that would leave a junk draft behind).
    """
    for _ in range(4):
        nodes = await dev.nodes()
        if find(nodes, p.open_label):
            return nodes
        discard = find(nodes, p.discard_label) if p.discard_label else None
        if discard:
            await _tap(dev, discard, log)
        else:
            log.append("Back")
            await dev.back()
        await sleep(1.0)
    log.append(f"Mở lại app {p.package}")
    await dev.launch(p.package)
    await sleep(2.0)
    nodes = await _wait_for(dev, p.open_label, 4.0, sleep)
    if nodes is None:
        raise OperationError(f"Không thấy nút mic '{p.open_label}' trên màn hình chính")
    return nodes


async def _poll(dev: DeviceDriver, timeout_s: float, sleep: Sleep):
    """Yield fresh node lists until ``timeout_s`` of wall time (or the poll budget) is used up.

    Real dumps take ~2.5 s each, so the wall clock — not the poll count — bounds the wait.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    for _ in range(max(1, int(timeout_s / POLL_S))):
        yield await dev.nodes()
        if loop.time() >= deadline:
            return
        await sleep(POLL_S)


async def _wait_mic(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + p.listen_timeout_s
    for n in range(max(1, int(p.listen_timeout_s / MIC_POLL_S))):
        state = await dev.mic_active()
        if state is None and getattr(dev, "fast_ui", False):
            # iPhone: no system mic state, but a UI dump is cheap -> wait for the stop button.
            if await _wait_for(dev, p.stop_label, p.listen_timeout_s, sleep) is None:
                raise OperationError(f"Mic không bật sau {p.listen_timeout_s:g}s (không thấy nút '{p.stop_label}')")
            log.append(f"Mic đã bật (thấy nút '{p.stop_label}')")
            return
        if state is None:
            log.append("Không đọc được trạng thái mic, chờ cố định")
            await sleep(1.0)
            return
        if state:
            log.append(f"Mic đã bật (lần kiểm tra {n + 1})")
            return
        if loop.time() >= deadline:
            break
        await sleep(MIC_POLL_S)
    raise OperationError(f"Mic không bật sau {p.listen_timeout_s:g}s (không thấy app thu âm)")


def _shows_not_heard(nodes: list[UiNode], p: AppProfile) -> bool:
    """The "Chưa nghe rõ. Thử lại hoặc gõ." notice (matched as a substring: the tail varies)."""
    label = p.not_heard_label.strip()
    return bool(label) and any(label in n.label for n in nodes)


def _sheet_open(nodes: list[UiNode], p: AppProfile) -> bool:
    return any(find(nodes, label) for label in (p.close_label, p.stop_label, p.idle_label))


DISCARD_WAIT_S = 3.0
FORM_WAIT_S = 2.5  # iOS: how long a chat bubble may wait for the task form that follows it


async def _discard_form(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> None:
    """After Back on the task form: confirm "Bỏ thay đổi" so the next sentence starts clean.

    Best effort — if the dialog does not show, ``ensure_home`` deals with it next time.
    """
    if not p.discard_label:
        return
    nodes = await _wait_for(dev, p.discard_label, DISCARD_WAIT_S, sleep)
    if nodes is None:
        log.append(f"Không thấy nút '{p.discard_label}' sau Back")
        return
    await _tap(dev, find(nodes, p.discard_label), log)  # type: ignore[arg-type]


async def run_one(
    dev: DeviceDriver,
    p: AppProfile,
    wav: Path,
    player: AudioPlayer,
    sleep: Sleep = asyncio.sleep,
    prev_bubbles: list[str] | None = None,  # kept for callers; the baseline is now measured
    is_correct: Callable[[str], bool] | None = None,
) -> AppCapture:
    """Speak one sentence to the app and read what it heard.

    With ``is_correct``, a wrong (or empty) result is photographed while the sheet still shows it.
    """
    log: list[str] = []
    try:
        return await _run_one(dev, p, wav, player, sleep, log, is_correct)
    except OperationError as e:
        e.log = log  # type: ignore[attr-defined]
        raise


async def prepare(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> None:
    """Phase 1: from wherever the app is to a live mic, ready for the audio."""
    home = await ensure_home(dev, p, log, sleep)
    await _tap(dev, find(home, p.open_label), log)  # type: ignore[arg-type]

    # The mic goes live 0.6-1+ s after the tap (audio before that is lost) and the app gives up
    # after ~3 s of silence; a UI dump costs ~2.5 s, so watch the mic via dumpsys (~0.1 s).
    await _wait_mic(dev, p, log, sleep)
    await sleep(p.pre_delay_s)


async def speak(devs: list[DeviceDriver], wav: Path, player: AudioPlayer,
                logs: list[list[str]]) -> list[list[UiNode] | BaseException]:
    """Phase 2: play ``wav`` once for every listening phone; returns each phone's baseline dump.

    Baseline dumps run while the audio plays: the app is listening, so no new bubble exists yet.
    (The chat may still hold earlier bubbles: the sheet does not always clear on reopen.)
    """
    tasks = [asyncio.create_task(dev.nodes()) for dev in devs]
    await asyncio.sleep(0)
    for log in logs:
        log.append(f"Phát {Path(wav).name}")
    try:
        await asyncio.to_thread(player.play, wav)
    finally:
        bases = await asyncio.gather(*tasks, return_exceptions=True)
    return list(bases)


async def _run_one(dev: DeviceDriver, p: AppProfile, wav: Path, player: AudioPlayer, sleep: Sleep,
                   log: list[str], is_correct: Callable[[str], bool] | None = None) -> AppCapture:
    await prepare(dev, p, log, sleep)
    [base] = await speak([dev], wav, player, [log])
    if isinstance(base, BaseException):
        raise base
    return await read_result(dev, p, base, log, sleep, is_correct)


async def read_result(dev: DeviceDriver, p: AppProfile, base: list[UiNode], log: list[str], sleep: Sleep,
                      is_correct: Callable[[str], bool] | None = None) -> AppCapture:
    """Phase 3: stop listening, read what the app heard, photograph a wrong answer, close the sheet."""
    if not _sheet_open(base, p):
        raise OperationError(f"Bảng '{p.sheet_label or p.close_label}' không mở")
    before = bubble_labels(base, dev.screen_w)
    before_heard = heard_text(base, p.heard_prefix)  # a form left open must not count as new
    await sleep(p.post_delay_s)

    # Decide on the stop tap with the cheap mic check right before tapping: a fresh UI dump
    # takes ~2.5 s, during which the app may stop by itself — and tapping the idle mic would
    # start a new listen.
    live = await dev.mic_active()
    stop = find(base, p.stop_label)
    if live is None:
        stop = find(await dev.nodes(), p.stop_label)
    if live is False or stop is None:
        log.append("App đã tự dừng nghe")
    else:
        await _tap(dev, stop, log)

    text: str | None = None
    on_form = False
    not_heard = False
    nodes = base
    async for nodes in _poll(dev, p.result_timeout_s, sleep):
        if not _sheet_open(nodes, p):
            raise OperationError(f"Bảng '{p.sheet_label or p.close_label}' không còn trên màn hình khi đọc kết quả")
        heard = heard_text(nodes, p.heard_prefix)
        if heard is not None and heard != before_heard:
            text, on_form = heard, True
            log.append(f"App nhận: {text}")
            break
        bubble = new_bubble_after(before, nodes, dev.screen_w)
        if bubble:
            text = bubble.label
            log.append(f"App nhận: {text}")
            break
        if _shows_not_heard(nodes, p):
            not_heard = True
            log.append(f"App báo '{p.not_heard_label}'")
            break
    else:
        log.append("App không trả câu nào")

    if text is not None and not on_form and p.heard_prefix and getattr(dev, "fast_ui", False):
        # iOS (Vita UAT): the bubble shows first and the task form replaces it ~1 s later.
        # Closing the chat before that leaves the form open on the home screen, so wait for it.
        async for later in _poll(dev, FORM_WAIT_S, sleep):
            heard = heard_text(later, p.heard_prefix)
            if heard is not None and heard != before_heard:
                text, on_form, nodes = heard, True, later
                log.append(f"Mở form tạo việc: {text}")
                break
            if not _sheet_open(later, p):
                break

    bubbles = bubble_labels(nodes, dev.screen_w)
    shot = None
    if is_correct is not None and not is_correct(text or ""):
        shot = await _try_screencap(dev, log)  # before Back: afterwards the evidence is gone
    # Close with Back: the sheet grows when the assistant answers, so a tap at coordinates from a
    # ~2.5 s old dump can land on the "Thử nói" suggestion and open a task form.
    log.append("Back (đóng bảng)")
    await dev.back()
    if on_form:
        await _discard_form(dev, p, log, sleep)
    return AppCapture(text=text, log=log, bubbles=bubbles, screenshot=shot, not_heard=not_heard)


MAX_CONSECUTIVE_OP_ERRORS = 5
NOT_HEARD_RETRIES = 1  # app says "Chưa nghe rõ": speak the sentence again this many times
RETRY_PAUSE_S = 1.0


async def pause_unless_cancelled(seconds: float, cancel: asyncio.Event) -> None:
    """Wait ``seconds``, returning early as soon as the run is cancelled."""
    if seconds <= 0:
        return
    try:
        await asyncio.wait_for(cancel.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def run_block2(
    store: Store,
    app_run_id: int,
    dev: DeviceDriver,
    profile: AppProfile,
    player: AudioPlayer,
    settings: Settings,
    emit: Emit,
    cancel: asyncio.Event,
    run_one: Callable[..., Awaitable[AppCapture]] = run_one,
    shots_dir: Path | None = None,
    pause: Callable[[float, asyncio.Event], Awaitable[None]] = pause_unless_cancelled,
) -> None:
    """Run every pending sentence; with ``shots_dir``, failures leave a ``<result id>.png`` there.

    ``profile.between_delay_s`` separates two sentences (not before the first, not after the last).
    """

    def save_shot(result_id: int, png: bytes | None, log: list[str]) -> str | None:
        if png is None or shots_dir is None:
            return None
        try:
            shots_dir.mkdir(parents=True, exist_ok=True)
            # a re-run keeps the earlier attempt's photo (its history points at it)
            path = shots_dir / f"{result_id}.png"
            n = 2
            while path.exists():
                path = shots_dir / f"{result_id}_{n}.png"
                n += 1
            path.write_bytes(png)
        except OSError as e:  # disk full, antivirus lock: the result matters more than its photo
            log.append(f"Không lưu được ảnh: {e}")
            return None
        return str(path.resolve())

    todo = store.pending_for_block2(app_run_id)
    total = len(todo)
    op_errors = 0
    for done, row in enumerate(todo):
        if done and profile.between_delay_s > 0 and not cancel.is_set():
            await pause(profile.between_delay_s, cancel)
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        label = f"[{done + 1}/{total}] {row['tc_id']}"
        # read per sentence: the user may change the run's threshold while it goes
        threshold = (store.get_app_run(app_run_id) or {}).get("wer_threshold", 0.0)
        emit(ProgressEvent("", "log", done, total, message=f"{label}: {row['text_tts']}"))
        try:
            if not row["audio_path"] or not Path(row["audio_path"]).is_file():
                raise OperationError("Không có file audio của câu này (chạy lại Khối 1)")
            kw = {}
            if shots_dir is not None:
                text_tts = row["text_tts"]
                kw["is_correct"] = lambda heard, t=text_tts: compare(t, heard, threshold).correct
            cap = await run_one(dev, profile, Path(row["audio_path"]), player, **kw)
            for attempt in range(NOT_HEARD_RETRIES):
                if not cap.not_heard or cap.text or cancel.is_set():
                    break
                note = f"{label}: app báo '{profile.not_heard_label}' → phát lại lần {attempt + 2}"
                emit(ProgressEvent("", "log", done, total, message=note))
                await pause(RETRY_PAUSE_S, cancel)
                first_log = cap.log
                cap = await run_one(dev, profile, Path(row["audio_path"]), player, **kw)
                cap.log = [*first_log, f"— Phát lại lần {attempt + 2} —", *cap.log]
        except Exception as e:  # OperationError, adb failures: the tool, not the app, failed
            op_errors += 1
            msg = str(e) or type(e).__name__
            log = list(getattr(e, "log", []) or [])
            # Photograph the screen as the failure left it, before the next sentence recovers it.
            png = await _try_screencap(dev, log) if shots_dir is not None else None
            shot_path = save_shot(row["id"], png, log)
            store.record_app_result(row["id"], AppStatus.OP_ERROR, None, None, msg, "\n".join(log),
                                    screenshot_path=shot_path)
            emit(ProgressEvent("", "log", done + 1, total, message=f"{label}: Lỗi thao tác — {msg}"))
            emit(ProgressEvent("", "item", done + 1, total, item=store.get_app_result(row["id"])))
            if op_errors >= MAX_CONSECUTIVE_OP_ERRORS:
                emit(ProgressEvent("", "error", done + 1, total,
                                   message=f"Dừng sau {MAX_CONSECUTIVE_OP_ERRORS} lỗi thao tác liên tiếp: {msg}"))
                return
            continue
        op_errors = 0
        heard = cap.text or ""
        result = compare(row["text_tts"], heard, threshold)
        status = AppStatus.PASSED if result.correct else AppStatus.FAILED
        shot_path = save_shot(row["id"], cap.screenshot, cap.log)
        store.record_app_result(row["id"], status, heard, result, None, "\n".join(cap.log),
                                screenshot_path=shot_path)
        for line in cap.log:
            emit(ProgressEvent("", "log", done, total, message=line))
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_app_result(row["id"])))
    emit(ProgressEvent("", "done", total, total))
