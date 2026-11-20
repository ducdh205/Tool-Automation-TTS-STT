"""Block 1: synthesize audio, then verify it with the reference STT (two separate jobs).

A failed verification does not regenerate on its own: the user decides with "Sinh lại"
(``run_generate(..., regenerate=True)``), which speaks the row again with the next attempt's seed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import soundfile as sf

from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.jobs.runner import Emit, ProgressEvent
from tts_stt_tool.store.db import ItemStatus, Store
from tts_stt_tool.stt.wyoming_client import SttEngine, SttError
from tts_stt_tool.tts.base import TtsEngine
from tts_stt_tool.tts.cache import AudioCache

_LOG = logging.getLogger(__name__)
MAX_CONSECUTIVE_ERRORS = 3
MISSING_AUDIO = "Không tìm thấy file audio — bấm Sinh lại"


def _still_queued(queue_query: Callable[[list[int]], list[dict[str, Any]]], item_id: int) -> dict[str, Any] | None:
    """Re-read a queued row: it may have been edited, disabled or processed since the queue was built."""
    rows = queue_query([item_id])
    return rows[0] if rows else None


async def run_generate(
    store: Store,
    audio_set_id: int,
    tts: TtsEngine,
    cache: AudioCache,
    settings: Settings,
    emit: Emit,
    cancel: asyncio.Event,
    *,
    item_ids: list[int] | None = None,
    regenerate: bool = False,
) -> None:
    audio_set = store.get_audio_set(audio_set_id) or {}
    voice = audio_set.get("voice") or settings.voice or ""
    query = store.items_for_regenerate if regenerate else store.items_for_generate
    todo = query(audio_set_id, item_ids)
    total = len(todo)
    for done, queued in enumerate(todo):
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        item = _still_queued(lambda ids: query(audio_set_id, ids), queued["id"])
        if item is None:
            emit(ProgressEvent("", "progress", done + 1, total))
            continue
        text = item["text_tts"]
        attempt = item["attempts"] if regenerate else 0
        try:
            path = await cache.get_or_synthesize(tts, text, voice, attempt)
            if not store.record_generated(item["id"], str(path), attempt + 1, text_tts=text):
                _LOG.info("block1 item %s edited while synthesizing; audio dropped", item["id"])
        except Exception as e:  # per-item problem (TTS failure, bad text): mark and continue
            _LOG.warning("block1 item %s synthesis failed: %s", item["id"], e)
            store.record_error(item["id"], str(e) or type(e).__name__, text_tts=text)
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
    emit(ProgressEvent("", "done", total, total))


async def run_verify(
    store: Store,
    audio_set_id: int,
    stt: SttEngine,
    settings: Settings,
    emit: Emit,
    cancel: asyncio.Event,
    *,
    item_ids: list[int] | None = None,
) -> None:
    todo = store.items_for_verify(audio_set_id, item_ids)
    total = len(todo)
    consecutive_stt_errors = 0
    for done, queued in enumerate(todo):
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        item = _still_queued(lambda ids: store.items_for_verify(audio_set_id, ids), queued["id"])
        if item is None:
            emit(ProgressEvent("", "progress", done + 1, total))
            continue
        text = item["text_tts"]
        try:
            if not Path(item["audio_path"]).is_file():
                store.record_error(item["id"], MISSING_AUDIO, text_tts=text)
            else:
                audio, sr = await asyncio.to_thread(sf.read, item["audio_path"], dtype="float32")
                hyp = await stt.transcribe(audio, sr)
                result = compare(text, hyp, settings.wer_threshold)
                status = ItemStatus.PASSED if result.correct else ItemStatus.AUDIO_FAILED
                if not store.record_verify(item["id"], hyp, result, status, text_tts=text):
                    _LOG.info("block1 item %s edited during verify; result dropped", item["id"])
            consecutive_stt_errors = 0
        except SttError as e:  # infrastructure: wyoming down/hung -> stop after a few in a row
            _LOG.warning("block1 item %s STT failed: %s", item["id"], e)
            store.record_error(item["id"], str(e), text_tts=text)
            consecutive_stt_errors += 1
            if consecutive_stt_errors >= MAX_CONSECUTIVE_ERRORS:
                emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
                emit(ProgressEvent("", "error", done + 1, total,
                                   message=f"Dừng sau {MAX_CONSECUTIVE_ERRORS} lỗi STT liên tiếp: {e}"))
                return
        except Exception as e:  # unreadable audio file etc.: mark and continue
            _LOG.warning("block1 item %s verify failed: %s", item["id"], e)
            store.record_error(item["id"], str(e) or type(e).__name__, text_tts=text)
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
    emit(ProgressEvent("", "done", total, total))
