import asyncio

import numpy as np
import pytest

from tts_stt_tool.config import Settings
from tts_stt_tool.models import InputItem
from tts_stt_tool.pipeline.block1 import run_block1
from tts_stt_tool.store.db import ItemStatus, Store
from tts_stt_tool.stt.wyoming_client import SttError
from tts_stt_tool.tts.cache import AudioCache


class FakeTts:
    version = "fake-1"

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def voices(self):
        return []

    def synthesize(self, text, voice, attempt):
        self.calls.append((text, attempt))
        return (np.sin(np.linspace(0, 50, 1600)) * 0.2).astype("float32"), 16000


class FakeStt:
    """Answers per text_tts from a script; the last answer repeats."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.audio_lengths: list[int] = []
        self.current = None

    async def transcribe(self, audio, sr):
        self.audio_lengths.append(len(audio))
        answers = self.script[self.current]
        ans = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(ans, Exception):
            raise ans
        return ans


def _item(tc, text):
    return InputItem(sheet="S", tc_id=tc, turn="1", feature="", priority="", region="",
                     speaker="👤 Người dùng", text_raw=text, expected="", source_row=5)


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    settings = Settings(data_dir=tmp_path, max_regen=3)
    cache = AudioCache(tmp_path / "audio")
    return store, settings, cache


def make_set(store, texts):
    return store.create_audio_set("s", "f.xlsx", ["S"], "Ngọc Huyền",
                                  [_item(f"TC-{i}", t) for i, t in enumerate(texts)])


class ScriptedStt(FakeStt):
    """FakeStt that knows which item is being transcribed via the text the TTS just spoke."""

    def __init__(self, script, tts):
        super().__init__(script)
        self.tts = tts

    async def transcribe(self, audio, sr):
        self.current = self.tts.calls[-1][0] if self.tts.calls else self.current
        return await super().transcribe(audio, sr)


async def run(store, set_id, tts, cache, stt, settings, cancel=None, events=None):
    events = events if events is not None else []
    await run_block1(store, set_id, tts, cache, stt, settings, events.append, cancel or asyncio.Event())
    return events


def by_text(store, set_id):
    return {i["text_tts"]: i for i in store.get_items(set_id)}


async def test_retry_policy(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu b", "câu c"])
    tts = FakeTts()
    stt = ScriptedStt({
        "câu a": ["câu a"],
        "câu b": ["sai", "sai", "câu b"],
        "câu c": ["sai"],
    }, tts)
    events = await run(store, set_id, tts, cache, stt, settings)
    items = by_text(store, set_id)
    assert items["câu a"]["status"] == ItemStatus.PASSED.value
    assert items["câu a"]["attempts"] == 1
    assert items["câu b"]["status"] == ItemStatus.PASSED.value
    assert items["câu b"]["attempts"] == 3
    assert items["câu c"]["status"] == ItemStatus.AUDIO_FAILED.value
    assert items["câu c"]["attempts"] == 4
    assert items["câu c"]["ref_text"] == "sai"
    assert [a for t, a in tts.calls if t == "câu c"] == [0, 1, 2, 3]
    assert events[-1].kind == "done"
    assert events[-1].done == events[-1].total == 3


async def test_stt_error_marks_item_and_continues(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu d", "câu e"])
    tts = FakeTts()
    stt = ScriptedStt({"câu d": [SttError("Hết thời gian chờ STT (30s)")], "câu e": ["câu e"]}, tts)
    await run(store, set_id, tts, cache, stt, settings)
    items = by_text(store, set_id)
    assert items["câu d"]["status"] == ItemStatus.ERROR.value
    assert "Hết thời gian" in items["câu d"]["error"]
    assert items["câu e"]["status"] == ItemStatus.PASSED.value


async def test_consecutive_errors_abort_job(env):
    store, settings, cache = env
    set_id = make_set(store, ["a1", "a2", "a3", "a4", "a5"])
    tts = FakeTts()
    err = SttError("Không kết nối được wyoming tại 127.0.0.1:10300")
    stt = ScriptedStt({t: [err] for t in ["a1", "a2", "a3", "a4", "a5"]}, tts)
    events = await run(store, set_id, tts, cache, stt, settings)
    assert events[-1].kind == "error"
    assert "Không kết nối được" in events[-1].message
    assert store.summary(set_id).get(ItemStatus.PENDING.value) == 2


async def test_resume_reuses_cache_and_skips_passed(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu f"])
    tts = FakeTts()
    stt = ScriptedStt({"câu a": ["câu a"], "câu f": [SttError("Hết thời gian")]}, tts)
    await run(store, set_id, tts, cache, stt, settings)
    assert len(tts.calls) == 2
    # second run: câu a already Đạt; câu f (Lỗi) retried, its attempt-0 audio is cached
    stt2 = ScriptedStt({"câu f": ["câu f"]}, tts)
    stt2.current = "câu f"
    calls_before = len(tts.calls)
    await run(store, set_id, tts, cache, stt2, settings)
    assert len(tts.calls) == calls_before  # no new synthesis
    assert by_text(store, set_id)["câu f"]["status"] == ItemStatus.PASSED.value


async def test_cancel_stops_after_current_item(env):
    store, settings, cache = env
    set_id = make_set(store, ["x1", "x2", "x3"])
    tts = FakeTts()
    stt = ScriptedStt({"x1": ["x1"], "x2": ["x2"], "x3": ["x3"]}, tts)
    cancel = asyncio.Event()
    events: list = []

    def emit(e):
        events.append(e)
        if e.kind == "item":
            cancel.set()

    await run_block1(store, set_id, tts, cache, stt, settings, emit, cancel)
    assert events[-1].kind == "cancelled"
    assert store.summary(set_id).get(ItemStatus.PASSED.value) == 1
    assert store.summary(set_id).get(ItemStatus.PENDING.value) == 2


async def test_item_event_carries_row(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a"])
    tts = FakeTts()
    events = await run(store, set_id, tts, cache, ScriptedStt({"câu a": ["câu a"]}, tts), settings)
    item_events = [e for e in events if e.kind == "item"]
    assert item_events[0].item["status"] == ItemStatus.PASSED.value
    assert item_events[0].item["audio_path"].endswith(".wav")
