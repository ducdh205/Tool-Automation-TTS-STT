"""Block 1: synthesize -> reference STT -> compare -> regenerate on mismatch."""

from __future__ import annotations

import asyncio
import logging

import soundfile as sf

from tts_stt_tool.compare.score import CompareResult, compare
from tts_stt_tool.config import Settings
from tts_stt_tool.jobs.runner import Emit, ProgressEvent
from tts_stt_tool.store.db import ItemStatus, Store
from tts_stt_tool.stt.wyoming_client import SttEngine
from tts_stt_tool.tts.base import TtsEngine
from tts_stt_tool.tts.cache import AudioCache, cache_key

_LOG = logging.getLogger(__name__)
MAX_CONSECUTIVE_ERRORS = 3


async def _audio_for(tts: TtsEngine, cache: AudioCache, text: str, voice: str, attempt: int):
    key = cache_key(text, voice, attempt, tts.version)
    if cache.exists(key):
        audio, sr = await asyncio.to_thread(sf.read, cache.path_for(key), dtype="float32")
        return audio, sr, cache.path_for(key)
    audio, sr = await asyncio.to_thread(tts.synthesize, text, voice, attempt)
    path = await asyncio.to_thread(cache.write, key, audio, sr)
    return audio, sr, path


async def _verify_item(store, item, tts, cache, stt, settings, voice) -> None:
    text = item["text_tts"]
    last: tuple[str, CompareResult] | None = None
    for attempt in range(settings.max_regen + 1):
        audio, sr, path = await _audio_for(tts, cache, text, voice, attempt)
        store.record_generated(item["id"], str(path), attempt + 1)
        hyp = await stt.transcribe(audio, sr)
        result = compare(text, hyp, settings.wer_threshold)
        last = (hyp, result)
        if result.correct:
            store.record_verify(item["id"], hyp, result, ItemStatus.PASSED)
            return
    assert last is not None
    store.record_verify(item["id"], last[0], last[1], ItemStatus.AUDIO_FAILED)


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
    consecutive_errors = 0
    for done, item in enumerate(todo):
        if cancel.is_set():
            emit(ProgressEvent("", "cancelled", done, total))
            return
        try:
            await _verify_item(store, item, tts, cache, stt, settings, voice)
            consecutive_errors = 0
        except Exception as e:  # one bad item (SttError, TTS failure) must not stop the run
            _LOG.warning("block1 item %s failed: %s", item["id"], e)
            store.record_error(item["id"], str(e) or type(e).__name__)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
                emit(ProgressEvent("", "error", done + 1, total,
                                   message=f"Dừng sau {MAX_CONSECUTIVE_ERRORS} lỗi liên tiếp: {e}"))
                return
        emit(ProgressEvent("", "item", done + 1, total, item=store.get_item(item["id"])))
    emit(ProgressEvent("", "done", total, total))
