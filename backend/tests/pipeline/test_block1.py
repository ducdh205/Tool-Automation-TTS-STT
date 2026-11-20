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


# --- final review fixes -------------------------------------------------------
async def test_edit_during_run_does_not_record_old_audio(env):
    """Review #1: user edits a row while the job is transcribing it."""
    store, settings, cache = env
    set_id = make_set(store, ["câu cũ"])
    item_id = store.get_items(set_id)[0]["id"]
    tts = FakeTts()

    class EditingStt:
        async def transcribe(self, audio, sr):
            store.set_item_text(item_id, "câu mới")
            return "câu cũ"

    await run(store, set_id, tts, cache, EditingStt(), settings)
    row = store.get_item(item_id)
    assert row["text_tts"] == "câu mới"
    assert row["status"] == ItemStatus.PENDING.value
    assert row["ref_text"] is None
    assert row["audio_path"] is None


async def test_item_edited_before_its_turn_uses_new_text(env):
    store, settings, cache = env
    set_id = make_set(store, ["một", "hai cũ"])
    second = store.get_items(set_id)[1]["id"]
    tts = FakeTts()

    class EditFirst:
        async def transcribe(self, audio, sr):
            if tts.calls[-1][0] == "một":
                store.set_item_text(second, "hai mới")
            return tts.calls[-1][0]

    await run(store, set_id, tts, cache, EditFirst(), settings)
    row = store.get_item(second)
    assert row["text_tts"] == "hai mới"
    assert row["status"] == ItemStatus.PASSED.value
    assert ("hai cũ", 0) not in tts.calls


async def test_per_item_failures_do_not_abort(env):
    """Review #2: only infrastructure (STT) errors count toward the abort."""
    store, settings, cache = env
    set_id = make_set(store, ["b1", "b2", "b3", "b4"])

    class BrokenTts(FakeTts):
        def synthesize(self, text, voice, attempt):
            if text != "b4":
                raise RuntimeError("TTS hỏng câu này")
            return super().synthesize(text, voice, attempt)

    tts = BrokenTts()
    events = await run(store, set_id, tts, cache, ScriptedStt({"b4": ["b4"]}, tts), settings)
    assert events[-1].kind == "done"
    assert store.summary(set_id) == {ItemStatus.ERROR.value: 3, ItemStatus.PASSED.value: 1}
