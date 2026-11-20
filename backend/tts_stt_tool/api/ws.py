"""WebSocket /ws: pushes job ProgressEvents as JSON."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


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
