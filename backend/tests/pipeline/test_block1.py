import asyncio
from pathlib import Path

import numpy as np
import pytest

from tts_stt_tool.config import Settings
from tts_stt_tool.models import InputItem
from tts_stt_tool.pipeline.block1 import run_generate, run_verify
from tts_stt_tool.store.db import ItemStatus, Store
from tts_stt_tool.stt.wyoming_client import SttError
from tts_stt_tool.tts.cache import AudioCache


class FakeTts:
    version = "fake-1"

    def __init__(self):
        self.calls: list[tuple[str, int]] = []
        self._texts: list[str] = []

    def voices(self):
        return []

    def synthesize(self, text, voice, attempt):
        self.calls.append((text, attempt))
        if text not in self._texts:
            self._texts.append(text)
        n = 1600 + self._texts.index(text)  # the length encodes the text, so a fake STT can "hear" it
        return (np.sin(np.linspace(0, 50, n)) * 0.2).astype("float32"), 16000

    def text_of(self, audio) -> str:
        i = len(audio) - 1600
        return self._texts[i] if 0 <= i < len(self._texts) else ""


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
    settings = Settings(data_dir=tmp_path)
    cache = AudioCache(tmp_path / "audio")
    return store, settings, cache


def make_set(store, texts):
    return store.create_audio_set("s", "f.xlsx", ["S"], "Ngọc Huyền",
                                  [_item(f"TC-{i}", t) for i, t in enumerate(texts)])


class ScriptedStt(FakeStt):
    """FakeStt that knows which item is being transcribed by decoding the fake audio."""

    def __init__(self, script, tts):
        super().__init__(script)
        self.tts = tts

    async def transcribe(self, audio, sr):
        self.current = self.tts.text_of(audio)
        return await super().transcribe(audio, sr)


async def generate(store, set_id, tts, cache, settings, cancel=None, events=None, **kw):
    events = events if events is not None else []
    await run_generate(store, set_id, tts, cache, settings, events.append, cancel or asyncio.Event(), **kw)
    return events


async def verify(store, set_id, stt, settings, cancel=None, events=None, **kw):
    events = events if events is not None else []
    await run_verify(store, set_id, stt, settings, events.append, cancel or asyncio.Event(), **kw)
    return events


def by_text(store, set_id):
    return {i["text_tts"]: i for i in store.get_items(set_id)}


def ids(store, set_id):
    return [i["id"] for i in store.get_items(set_id)]


async def test_generate_only_items_without_audio(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu b"])
    tts = FakeTts()
    events = await generate(store, set_id, tts, cache, settings)
    await generate(store, set_id, tts, cache, settings)
    assert [a for _, a in tts.calls] == [0, 0]  # the second run synthesizes nothing
    assert all(i["status"] == ItemStatus.GENERATED.value and i["attempts"] == 1 for i in store.get_items(set_id))
    assert events[-1].kind == "done" and events[-1].done == events[-1].total == 2


async def test_generate_selected_only(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu b"])
    await generate(store, set_id, FakeTts(), cache, settings, item_ids=[ids(store, set_id)[1]])
    assert [i["status"] for i in store.get_items(set_id)] == [ItemStatus.PENDING.value, ItemStatus.GENERATED.value]


async def test_verify_pass_and_fail_does_not_regenerate(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu c"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    calls_before = len(tts.calls)
    events = await verify(store, set_id, ScriptedStt({"câu a": ["câu a"], "câu c": ["sai"]}, tts), settings)
    assert len(tts.calls) == calls_before
    items = by_text(store, set_id)
    assert items["câu a"]["status"] == ItemStatus.PASSED.value
    assert items["câu c"]["status"] == ItemStatus.AUDIO_FAILED.value
    assert items["câu c"]["attempts"] == 1 and items["câu c"]["wer"] > 0 and items["câu c"]["ref_text"] == "sai"
    assert events[-1].kind == "done"


async def test_verify_all_only_generated_selected_reverifies(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a", "câu b"])
    tts = FakeTts()
    first, second = ids(store, set_id)
    await generate(store, set_id, tts, cache, settings, item_ids=[first])
    stt = ScriptedStt({"câu a": ["câu a"], "câu b": ["câu b"]}, tts)
    await verify(store, set_id, stt, settings)
    await generate(store, set_id, tts, cache, settings, item_ids=[second])
    stt.audio_lengths.clear()
    await verify(store, set_id, stt, settings)
    assert len(stt.audio_lengths) == 1  # only "câu b", which was still "Đã sinh audio"
    await verify(store, set_id, stt, settings, item_ids=[first])
    assert len(stt.audio_lengths) == 2  # a passed row is re-verified when picked by hand
    assert store.get_item(first)["status"] == ItemStatus.PASSED.value


async def test_regenerate_uses_next_attempt_and_clears_verify(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu c"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    await verify(store, set_id, ScriptedStt({"câu c": ["sai"]}, tts), settings)
    await generate(store, set_id, tts, cache, settings, regenerate=True)
    assert tts.calls[-1] == ("câu c", 1)
    it = store.get_items(set_id)[0]
    assert it["status"] == ItemStatus.GENERATED.value and it["attempts"] == 2
    assert it["ref_text"] is None and it["wer"] is None
    await generate(store, set_id, tts, cache, settings, regenerate=True)  # nothing failed now
    assert tts.calls[-1] == ("câu c", 1)


async def test_verify_selected_without_audio_is_untouched(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    item_id = ids(store, set_id)[0]
    store.set_item_text(item_id, "câu sửa")  # back to Chờ, audio dropped
    stt = ScriptedStt({"câu a": ["câu a"]}, tts)
    await verify(store, set_id, stt, settings, item_ids=[item_id])
    row = store.get_item(item_id)
    assert row["status"] == ItemStatus.PENDING.value and row["error"] is None
    assert stt.audio_lengths == []


async def test_verify_missing_audio_file_is_error(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    Path(store.get_items(set_id)[0]["audio_path"]).unlink()
    await verify(store, set_id, ScriptedStt({"câu a": ["câu a"]}, tts), settings)
    row = store.get_items(set_id)[0]
    assert row["status"] == ItemStatus.ERROR.value and "Sinh lại" in row["error"]


async def test_stt_error_marks_item_and_continues(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu d", "câu e"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    stt = ScriptedStt({"câu d": [SttError("Hết thời gian chờ STT (30s)")], "câu e": ["câu e"]}, tts)
    await verify(store, set_id, stt, settings)
    items = by_text(store, set_id)
    assert items["câu d"]["status"] == ItemStatus.ERROR.value
    assert "Hết thời gian" in items["câu d"]["error"]
    assert items["câu e"]["status"] == ItemStatus.PASSED.value
    # the errored row keeps its audio: the next Verify picks it up, Generate does not
    assert [i["text_tts"] for i in store.items_for_verify(set_id, None)] == ["câu d"]


async def test_verify_stops_after_three_stt_errors(env):
    store, settings, cache = env
    texts = ["a1", "a2", "a3", "a4", "a5"]
    set_id = make_set(store, texts)
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    err = SttError("Không kết nối được wyoming tại 127.0.0.1:10300")
    events = await verify(store, set_id, ScriptedStt({t: [err] for t in texts}, tts), settings)
    assert events[-1].kind == "error"
    assert "Không kết nối được" in events[-1].message
    assert store.summary(set_id) == {ItemStatus.ERROR.value: 3, ItemStatus.GENERATED.value: 2}


async def test_generate_reuses_cache(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a"])
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)
    store.set_item_text(ids(store, set_id)[0], "câu a")  # same text again: attempt-0 audio is cached
    await generate(store, set_id, tts, cache, settings)
    assert len(tts.calls) == 1
    assert store.get_items(set_id)[0]["status"] == ItemStatus.GENERATED.value


async def test_cancel_generate_after_first_item(env):
    store, settings, cache = env
    set_id = make_set(store, ["x1", "x2", "x3"])
    cancel = asyncio.Event()
    events: list = []

    def emit(e):
        events.append(e)
        if e.kind == "item":
            cancel.set()

    await run_generate(store, set_id, FakeTts(), cache, settings, emit, cancel)
    assert events[-1].kind == "cancelled"
    assert store.summary(set_id) == {ItemStatus.GENERATED.value: 1, ItemStatus.PENDING.value: 2}


async def test_item_events_carry_row(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu a"])
    tts = FakeTts()
    gen = await generate(store, set_id, tts, cache, settings)
    ver = await verify(store, set_id, ScriptedStt({"câu a": ["câu a"]}, tts), settings)
    assert [e for e in gen if e.kind == "item"][0].item["audio_path"].endswith(".wav")
    assert [e for e in ver if e.kind == "item"][0].item["status"] == ItemStatus.PASSED.value


async def test_edit_during_verify_does_not_record_old_result(env):
    store, settings, cache = env
    set_id = make_set(store, ["câu cũ"])
    item_id = ids(store, set_id)[0]
    tts = FakeTts()
    await generate(store, set_id, tts, cache, settings)

    class EditingStt:
        async def transcribe(self, audio, sr):
            store.set_item_text(item_id, "câu mới")
            return "câu cũ"

    await verify(store, set_id, EditingStt(), settings)
    row = store.get_item(item_id)
    assert row["text_tts"] == "câu mới"
    assert row["status"] == ItemStatus.PENDING.value
    assert row["ref_text"] is None and row["audio_path"] is None


async def test_item_edited_before_its_turn_uses_new_text(env):
    store, settings, cache = env
    set_id = make_set(store, ["một", "hai cũ"])
    second = ids(store, set_id)[1]

    class EditFirst(FakeTts):
        def synthesize(self, text, voice, attempt):
            if text == "một":
                store.set_item_text(second, "hai mới")
            return super().synthesize(text, voice, attempt)

    tts = EditFirst()
    await generate(store, set_id, tts, cache, settings)
    assert ("hai cũ", 0) not in tts.calls
    assert ("hai mới", 0) in tts.calls  # the queue re-reads the row and speaks the new text
    assert store.get_item(second)["status"] == ItemStatus.GENERATED.value


async def test_per_item_tts_failures_do_not_abort(env):
    store, settings, cache = env
    set_id = make_set(store, ["b1", "b2", "b3", "b4"])

    class BrokenTts(FakeTts):
        def synthesize(self, text, voice, attempt):
            if text != "b4":
                raise RuntimeError("TTS hỏng câu này")
            return super().synthesize(text, voice, attempt)

    events = await generate(store, set_id, BrokenTts(), cache, settings)
    assert events[-1].kind == "done"
    assert store.summary(set_id) == {ItemStatus.ERROR.value: 3, ItemStatus.GENERATED.value: 1}


def test_generate_uses_the_voice_of_each_rows_region(env):
    store, settings, cache = env
    rows = [("Bắc", "một"), ("BAC-HN", "hai"), ("Miền Trung", "ba"), ("Nam", "bốn"), ("", "năm"), ("??", "sáu")]
    items = [InputItem(sheet="S", tc_id=f"TC-{i}", turn="1", feature="", priority="", region=r, speaker="",
                       text_raw=t, expected="", source_row=i) for i, (r, t) in enumerate(rows)]
    # the set was imported with other voices; generating must use the voices saved in Settings now
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "Cũ", items, voice_trung="Cũ", voice_nam="Cũ")
    settings.voice, settings.voice_trung, settings.voice_nam = "Bắc-voice", "Trung-voice", "Nam-voice"
    used: dict[str, str] = {}

    class VoiceTts(FakeTts):
        def synthesize(self, text, voice, attempt):
            used[text] = voice
            return super().synthesize(text, voice, attempt)

    asyncio.run(run_generate(store, set_id, VoiceTts(), cache, settings, lambda e: None, asyncio.Event()))
    assert used == {"một": "Bắc-voice", "hai": "Bắc-voice", "ba": "Trung-voice", "bốn": "Nam-voice",
                    "năm": "Bắc-voice", "sáu": "Bắc-voice"}
