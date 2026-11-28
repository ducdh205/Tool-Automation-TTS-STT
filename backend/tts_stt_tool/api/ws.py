"""WebSockets: /ws pushes job ProgressEvents as JSON; /ws/device/{serial}/stream mirrors a phone."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tts_stt_tool.device.adb import AdbError
from tts_stt_tool.device.scrcpy import Packet, ScrcpyError, ScrcpyStream, Session

ws_router = APIRouter()
_LOG = logging.getLogger(__name__)


@ws_router.websocket("/ws")
async def events(ws: WebSocket) -> None:
    await ws.accept()
    runner = ws.app.state.ctx.runner
    q = runner.subscribe()
    try:
        while True:
            event = await q.get()
            await ws.send_json(event.to_json())
    except WebSocketDisconnect:
        pass
    finally:
        runner.unsubscribe(q)


def frame_message(p: Packet) -> bytes:
    """Binary frame for the browser: u8 flags (1 = key frame, 2 = carries SPS/PPS), u64 PTS, H.264."""
    return struct.pack(">BQ", (1 if p.key else 0) | (2 if p.config else 0), p.pts) + p.data


def oriented(size: tuple[int, int], s: Session) -> tuple[int, int]:
    """The phone's pixel size in the orientation of the stream (taps are sent in phone pixels)."""
    short, long = sorted(size)
    return (long, short) if s.width > s.height else (short, long)


@ws_router.websocket("/ws/device/{serial}/stream")
async def device_stream(ws: WebSocket, serial: str) -> None:
    """Android only, view only. Any failure ends with {"type": "error"}: the page falls back to
    screenshots. The stream never takes part in a test run; it can stop at any time."""
    await ws.accept()
    ctx = ws.app.state.ctx
    stream: ScrcpyStream | None = None
    try:
        if not ScrcpyStream.available() or not ctx.adb.available:
            raise ScrcpyError("scrcpy không có sẵn")
        if await ctx.ios.is_ios(serial):
            raise ScrcpyError("iPhone không hỗ trợ scrcpy")
        size = await ctx.adb.screen_size(serial)
        stream = ScrcpyStream(ctx.adb, serial)
        await stream.start()

        async def pump() -> None:
            async for item in stream.packets():
                if isinstance(item, Session):
                    w, h = oriented(size, item)
                    await ws.send_json({"type": "session", "width": item.width, "height": item.height,
                                        "device_width": w, "device_height": h})
                else:
                    await ws.send_bytes(frame_message(item))
            raise ScrcpyError("scrcpy-server đã dừng")

        async def watch_client() -> None:
            while True:  # the page never sends anything; this returns when it goes away
                if (await ws.receive())["type"] == "websocket.disconnect":
                    return

        tasks = [asyncio.create_task(pump()), asyncio.create_task(watch_client())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            t.result()
    except (ScrcpyError, AdbError, OSError, asyncio.IncompleteReadError) as e:
        _LOG.info("scrcpy %s: %s", serial, e)
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "message": str(e)})
            await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass  # page closed mid-send
    finally:
        if stream is not None:
            await stream.close()
