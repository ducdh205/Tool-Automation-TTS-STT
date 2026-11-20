"""Block 2: speak each verified sentence to the real app and read what it heard."""

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
from tts_stt_tool.device.ui_tree import UiNode, bubble_labels, find, new_bubble_after, parse_dump
from tts_stt_tool.jobs.runner import Emit, ProgressEvent
from tts_stt_tool.store.db import AppStatus, Store

_LOG = logging.getLogger(__name__)
POLL_S = 0.4
Sleep = Callable[[float], Awaitable[None]]


class OperationError(Exception):
    """The tool could not drive the app (not an app recognition error)."""


class DeviceDriver(Protocol):
    screen_w: int

    async def nodes(self) -> list[UiNode]: ...

    async def tap(self, x: int, y: int) -> None: ...

    async def back(self) -> None: ...

    async def launch(self, package: str) -> None: ...


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


@dataclass
class AppCapture:
    text: str | None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    bubbles: list[str] = field(default_factory=list)  # user bubbles on screen at the end


async def _wait_for(dev: DeviceDriver, label: str, timeout_s: float, sleep: Sleep) -> list[UiNode] | None:
    async for nodes in _poll(dev, timeout_s, sleep):
        if find(nodes, label):
            return nodes
    return None


async def _tap(dev: DeviceDriver, node: UiNode, log: list[str]) -> None:
    x, y = node.center
    log.append(f"Bấm '{node.label}' ({x},{y})")
    await dev.tap(x, y)


async def ensure_home(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> list[UiNode]:
    for _ in range(3):
        nodes = await dev.nodes()
        if find(nodes, p.open_label):
            return nodes
        close = find(nodes, p.close_label)
        if close:
            await _tap(dev, close, log)
        else:
            log.append("Back")
            await dev.back()
        await sleep(0.6)
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


async def run_one(
    dev: DeviceDriver,
    p: AppProfile,
    wav: Path,
    player: AudioPlayer,
    sleep: Sleep = asyncio.sleep,
    prev_bubbles: list[str] | None = None,
) -> AppCapture:
    """``prev_bubbles``: user bubbles seen when the previous sentence finished (chat may persist)."""
    log: list[str] = []
    home = await ensure_home(dev, p, log, sleep)
    await _tap(dev, find(home, p.open_label), log)  # type: ignore[arg-type]

    # The app stops listening after ~3 s of silence and one dump costs ~2.5 s:
    # play right away and check the sheet afterwards.
    await sleep(p.pre_delay_s)
    log.append(f"Phát {Path(wav).name}")
    await asyncio.to_thread(player.play, wav)
    await sleep(p.post_delay_s)

    nodes = await dev.nodes()
    stop = find(nodes, p.stop_label)
    if stop:
        before = bubble_labels(nodes, dev.screen_w)  # still listening: nothing new yet
        await _tap(dev, stop, log)
    elif find(nodes, p.idle_label):
        log.append("App đã tự dừng nghe")  # never tap the idle mic: it would start a new listen
        before = list(prev_bubbles or [])
    else:
        raise OperationError(f"App không chuyển sang nghe (không thấy '{p.stop_label}')")

    text: str | None = None
    async for nodes in _poll(dev, p.result_timeout_s, sleep):
        bubble = new_bubble_after(before, nodes, dev.screen_w)
        if bubble:
            text = bubble.label
            log.append(f"App nhận: {text}")
            break
    else:
        log.append("App không trả câu nào")

    bubbles = bubble_labels(nodes, dev.screen_w)
    close = find(nodes, p.close_label)
    if close:
        await _tap(dev, close, log)
    return AppCapture(text=text, log=log, bubbles=bubbles)


MAX_CONSECUTIVE_OP_ERRORS = 5


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
) -> None:
    todo = store.pending_for_block2(app_run_id)
    total = len(todo)
    prev: list[str] | None = None
    op_errors = 0
    for done, row in enumerate(todo):
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        label = f"[{done + 1}/{total}] {row['tc_id']}"
        emit(ProgressEvent("", "log", done, total, message=f"{label}: {row['text_tts']}"))
        try:
            cap = await run_one(dev, profile, Path(row["audio_path"]), player, prev_bubbles=prev)
        except Exception as e:  # OperationError, adb failures: the tool, not the app, failed
            op_errors += 1
            msg = str(e) or type(e).__name__
            store.record_app_result(row["id"], AppStatus.OP_ERROR, None, None, msg, "")
            emit(ProgressEvent("", "log", done + 1, total, message=f"{label}: Lỗi thao tác — {msg}"))
            emit(ProgressEvent("", "item", done + 1, total, item=store.get_app_result(row["id"])))
            prev = None
            if op_errors >= MAX_CONSECUTIVE_OP_ERRORS:
                emit(ProgressEvent("", "error", done + 1, total,
                                   message=f"Dừng sau {MAX_CONSECUTIVE_OP_ERRORS} lỗi thao tác liên tiếp: {msg}"))
                return
            continue
        op_errors = 0
        prev = cap.bubbles
        heard = cap.text or ""
        result = compare(row["text_tts"], heard, settings.wer_threshold)
        status = AppStatus.PASSED if result.correct else AppStatus.FAILED
        store.record_app_result(row["id"], status, heard, result, None, "\n".join(cap.log))
        for line in cap.log:
            emit(ProgressEvent("", "log", done, total, message=line))
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_app_result(row["id"])))
    emit(ProgressEvent("", "done", total, total))
