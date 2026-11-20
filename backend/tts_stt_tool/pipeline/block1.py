"""Block 1: synthesize -> reference STT -> compare -> regenerate on mismatch."""

from __future__ import annotations

import asyncio
import logging

import soundfile as sf

from tts_stt_tool.compare.score import CompareResult, compare
from tts_stt_tool.config import Settings
from tts_stt_tool.jobs.runner import Emit, ProgressEvent
from tts_stt_tool.store.db import ItemStatus, Store
from tts_stt_tool.stt.wyoming_client import SttEngine, SttError
from tts_stt_tool.tts.base import TtsEngine
from tts_stt_tool.tts.cache import AudioCache, cache_key

_LOG = logging.getLogger(__name__)
MAX_CONSECUTIVE_ERRORS = 3
_TODO = (ItemStatus.PENDING.value, ItemStatus.GENERATED.value, ItemStatus.ERROR.value)


async def _audio_for(tts: TtsEngine, cache: AudioCache, text: str, voice: str, attempt: int):
    key = cache_key(text, voice, attempt, tts.version)
    if cache.exists(key):
        audio, sr = await asyncio.to_thread(sf.read, cache.path_for(key), dtype="float32")
        return audio, sr, cache.path_for(key)
    audio, sr = await asyncio.to_thread(tts.synthesize, text, voice, attempt)
    path = await asyncio.to_thread(cache.write, key, audio, sr)
    return audio, sr, path


class _Superseded(Exception):
    """The row was edited while being processed; its new text will be handled later."""


async def _verify_item(store, item, tts, cache, stt, settings, voice) -> None:
    text = item["text_tts"]
    last: tuple[str, CompareResult] | None = None
    for attempt in range(settings.max_regen + 1):
        audio, sr, path = await _audio_for(tts, cache, text, voice, attempt)
        if not store.record_generated(item["id"], str(path), attempt + 1, text_tts=text):
            raise _Superseded
        hyp = await stt.transcribe(audio, sr)
        result = compare(text, hyp, settings.wer_threshold)
        last = (hyp, result)
        if result.correct:
            if not store.record_verify(item["id"], hyp, result, ItemStatus.PASSED, text_tts=text):
                raise _Superseded
            return
    assert last is not None
    if not store.record_verify(item["id"], last[0], last[1], ItemStatus.AUDIO_FAILED, text_tts=text):
        raise _Superseded


async def run_block1(
    store: Store,
    audio_set_id: int,
    tts: TtsEngine,
    cache: AudioCache,
    stt: SttEngine,
    settings: Settings,
    emit: Emit,
    cancel: asyncio.Event,
) -> None:
    audio_set = store.get_audio_set(audio_set_id) or {}
    voice = audio_set.get("voice") or settings.voice or ""
    todo = store.pending_for_block1(audio_set_id)
    total = len(todo)
    consecutive_stt_errors = 0
    for done, queued in enumerate(todo):
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        # Re-read: the user may have edited, disabled or re-run this row since the queue was built.
        item = store.get_item(queued["id"])
        if not item or not item["enabled"] or not item["text_tts"] or item["status"] not in _TODO:
            emit(ProgressEvent("", "progress", done + 1, total))
            continue
        try:
            await _verify_item(store, item, tts, cache, stt, settings, voice)
            consecutive_stt_errors = 0
        except _Superseded:
            _LOG.info("block1 item %s edited during processing; result dropped", item["id"])
        except SttError as e:  # infrastructure: wyoming down/hung -> stop after a few in a row
            _LOG.warning("block1 item %s STT failed: %s", item["id"], e)
            store.record_error(item["id"], str(e), text_tts=item["text_tts"])
            consecutive_stt_errors += 1
            if consecutive_stt_errors >= MAX_CONSECUTIVE_ERRORS:
                emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
                emit(ProgressEvent("", "error", done + 1, total,
                                   message=f"Dừng sau {MAX_CONSECUTIVE_ERRORS} lỗi STT liên tiếp: {e}"))
                return
        except Exception as e:  # per-item problem (TTS failure, bad text): mark and continue
            _LOG.warning("block1 item %s failed: %s", item["id"], e)
            store.record_error(item["id"], str(e) or type(e).__name__, text_tts=item["text_tts"])
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
    emit(ProgressEvent("", "done", total, total))
