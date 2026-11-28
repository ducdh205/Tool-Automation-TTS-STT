"""Block 2 on two phones at once: one playback per sentence, retries only where needed."""

import asyncio

import pytest

from backend.tests.pipeline.fake_app import FakeApp
from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.device.profile import AppProfile
from tts_stt_tool.models import InputItem
from tts_stt_tool.pipeline.block2 import AppCapture, Lane, OperationError, run_block2_multi
from tts_stt_tool.store.db import AppStatus, ItemStatus, Store

FAST = AppProfile(pre_delay_s=0, post_delay_s=0, listen_timeout_s=0.1, result_timeout_s=0.1)


def _item(tc, text):
    return InputItem(sheet="S", tc_id=tc, turn="1", feature="", priority="", region="",
                     speaker="👤 Người dùng", text_raw=text, expected="", source_row=5)


def make_env(tmp_path, texts):
    store = Store(tmp_path / "t.db")
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "v", [_item(str(i), t) for i, t in enumerate(texts)])
    for r in store.get_items(set_id):
        wav = tmp_path / f"{r['id']}.wav"
        wav.write_bytes(b"RIFF")
        store.record_generated(r["id"], str(wav), 1)
        store.record_verify(r["id"], r["text_tts"], compare(r["text_tts"], r["text_tts"]), ItemStatus.PASSED)
    a = store.create_app_run(set_id, "SER", "m", "p", None)
    b = store.create_app_run(set_id, "SER2", "m2", "p", None)
    return store, a, b, Settings(data_dir=tmp_path)


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path, ["bật đèn", "tắt đèn", "mở cốp"])


def wavs(store, run_id):
    return [f"{r['item_id']}.wav" for r in store.app_results(run_id)]


def scripted_attempt(answers, default=None):
    """answers[(run_id, wav name)] = one answer per attempt: text | "NOT_HEARD" | Exception."""
    calls: list[tuple[str, tuple[int, ...]]] = []
    count: dict[tuple[int, str], int] = {}

    async def attempt(lanes, wav, player, checks):
        calls.append((wav.name, tuple(l.run_id for l in lanes)))
        out = []
        for lane in lanes:
            key = (lane.run_id, wav.name)
            n = count.get(key, 0)
            count[key] = n + 1
            seq = answers.get(key, [default])
            ans = seq[min(n, len(seq) - 1)]
            if isinstance(ans, Exception):
                ans.log = [f"try {n + 1}"]
                out.append(ans)
            elif ans == "NOT_HEARD":
                out.append(AppCapture(text=None, not_heard=True, log=[f"try {n + 1}"]))
            else:
                out.append(AppCapture(text=ans, log=[f"try {n + 1}"]))
        return out

    attempt.calls = calls
    return attempt


async def no_pause(_s, _c):
    return None


async def go(store, lanes, settings, attempt, cancel=None, emit=None, profile=None):
    events = []
    await run_block2_multi(store, lanes, profile or AppProfile(), object(), settings, emit or events.append,
                           cancel or asyncio.Event(), attempt=attempt, pause=no_pause)
    return events


def status(store, run_id):
    return [r["status"] for r in store.app_results(run_id)]


async def test_not_heard_retries_only_that_lane(env):
    store, a, b, settings = env
    w = wavs(store, a)
    att = scripted_attempt({(a, w[0]): ["NOT_HEARD", "bật đèn"]}, default="bật đèn")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    assert att.calls[:3] == [(w[0], (a, b)), (w[0], (a,)), (w[1], (a, b))]
    assert store.app_results(a)[0]["status"] == AppStatus.PASSED.value
    assert "Phát lại lần 2" in store.app_results(a)[0]["log"]


async def test_op_error_retries_once_alone(env):
    store, a, b, settings = env
    w = wavs(store, a)
    att = scripted_attempt({(b, w[0]): [OperationError("x"), "bật đèn"]}, default="bật đèn")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    assert att.calls[1] == (w[0], (b,))
    row = store.app_results(b)[0]
    assert row["status"] == AppStatus.PASSED.value
    assert "— Thử lại sau lỗi thao tác —" in row["log"] and "try 1" in row["log"]


async def test_both_fail_retry_together(env):
    store, a, b, settings = env
    w = wavs(store, a)
    att = scripted_attempt({(a, w[0]): ["NOT_HEARD", "bật đèn"], (b, w[0]): [OperationError("x"), "bật đèn"]},
                           default="bật đèn")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    assert att.calls[:2] == [(w[0], (a, b)), (w[0], (a, b))]


async def test_op_error_twice_records_op_error(env):
    store, a, b, settings = env
    w = wavs(store, a)
    att = scripted_attempt({(b, w[0]): [OperationError("x"), OperationError("y")]}, default="bật đèn")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    row = store.app_results(b)[0]
    assert row["status"] == AppStatus.OP_ERROR.value and row["error"] == "y"
    assert store.app_results(a)[0]["status"] == AppStatus.PASSED.value


async def test_one_lane_five_op_errors_stops_both(tmp_path):
    store, a, b, settings = make_env(tmp_path, ["bật đèn", "tắt đèn", "mở cốp", "đóng cốp", "bật quạt",
                                                "tắt quạt", "mở kính"])
    att = scripted_attempt({(b, w): [OperationError("rút cáp")] for w in wavs(store, b)}, default="ok")
    events = await go(store, [Lane(a, object(), name="SER"), Lane(b, object(), name="SER2")], settings, att)
    assert events[-1].kind == "error" and "5 lỗi thao tác" in events[-1].message and "SER2" in events[-1].message
    assert store.app_summary(b) == {AppStatus.OP_ERROR.value: 5, AppStatus.PENDING.value: 2}
    assert store.app_summary(a)[AppStatus.PENDING.value] == 2


async def test_cancel_stops_both(env):
    store, a, b, settings = env
    cancel = asyncio.Event()
    events = []

    def emit(e):
        events.append(e)
        if e.kind == "item":
            cancel.set()

    await go(store, [Lane(a, object()), Lane(b, object())], settings, scripted_attempt({}, "x"),
             cancel=cancel, emit=emit)
    assert events[-1].kind == "cancelled"
    assert status(store, a)[1:] == [AppStatus.PENDING.value] * 2
    assert status(store, b)[1:] == [AppStatus.PENDING.value] * 2


async def test_cancel_during_last_sentence_ends_cancelled(tmp_path):
    store, a, b, settings = make_env(tmp_path, ["bật đèn"])
    cancel = asyncio.Event()
    inner = scripted_attempt({}, "bật đèn")

    async def attempt(lanes, wav, player, checks):
        cancel.set()  # Dừng pressed while the only (= last) sentence plays
        return await inner(lanes, wav, player, checks)

    events = await go(store, [Lane(a, object())], settings, attempt, cancel=cancel)
    assert events[-1].kind == "cancelled"
    assert status(store, a) == [AppStatus.PASSED.value]  # its answer is still kept


async def test_resume_lanes_with_different_pending(env):
    store, a, b, settings = env
    first = store.app_results(a)[0]
    store.record_app_result(first["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "")
    w = wavs(store, a)
    att = scripted_attempt({}, "x")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    assert att.calls == [(w[0], (b,)), (w[1], (a, b)), (w[2], (a, b))]


async def test_events_carry_run_id(env):
    store, a, b, settings = env
    events = await go(store, [Lane(a, object()), Lane(b, object())], settings, scripted_attempt({}, "x"))
    items = [e for e in events if e.kind == "item"]
    assert len(items) == 6
    assert all(e.run_id == e.item["app_run_id"] for e in items)


# -- the real default attempt, with fake phones and one fake speaker ---------------------------


class Speaker:
    def __init__(self, *apps):
        self.apps, self.calls, self.times = apps, 0, []

    def play(self, path):
        self.calls += 1
        self.times.append(_now())
        for app in self.apps:
            app.play(path)


def _now():
    import time

    return time.monotonic()


class SlowApp(FakeApp):
    """A phone whose screen dumps take ``delay`` seconds; remembers when its mic went live."""

    def __init__(self, delay, **kw):
        super().__init__(**kw)
        self.delay = delay
        self.mic_on: list[float] = []

    async def nodes(self):
        await asyncio.sleep(self.delay)
        return await super().nodes()

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.taps[-1] == "Nói để tạo việc":
            self.mic_on.append(_now())


@pytest.fixture
def fast_poll(monkeypatch):
    import tts_stt_tool.pipeline.block2 as b2

    monkeypatch.setattr(b2, "POLL_S", 0.001)


async def run_real(store, lanes, settings, spk, profile=FAST):
    events = []
    await run_block2_multi(store, lanes, profile, spk, settings, events.append, asyncio.Event(), pause=no_pause)
    return events


async def test_each_sentence_plays_once_for_both(env, fast_poll):
    store, a, b, settings = env
    pa, pb = FakeApp(transcript="bật đèn"), FakeApp(transcript="tắt đèn")
    spk = Speaker(pa, pb)
    await run_real(store, [Lane(a, pa), Lane(b, pb)], settings, spk)
    assert spk.calls == 3
    assert [r["app_text"] for r in store.app_results(a)] == ["bật đèn"] * 3
    assert [r["app_text"] for r in store.app_results(b)] == ["tắt đèn"] * 3


async def test_mic_off_before_play_is_op_error(env, fast_poll):
    store, a, b, settings = env
    pa, pb = FakeApp(transcript="bật đèn"), FakeApp(transcript="bật đèn")
    real_mic = pa.mic_active
    state = {"n": 0}

    async def mic_dies_once():
        live = await real_mic()
        if live and pa.state == "listening" and state["n"] == 0 and pa.mic_checks > 1:
            state["n"] += 1
            pa.state = "idle"  # the app gave up listening while the other phone was still preparing
            return False
        return live

    pa.mic_active = mic_dies_once
    spk = Speaker(pa, pb)
    await run_real(store, [Lane(a, pa), Lane(b, pb)], settings, spk)
    row = store.app_results(a)[0]
    assert "Mic đã tắt trước khi phát" in row["log"]
    assert row["status"] == AppStatus.PASSED.value  # the retry, alone, heard it
    assert spk.calls == 4  # 3 sentences + one retry for phone A


async def test_fast_lane_starts_later(env, fast_poll):
    store, a, b, settings = env
    fast, slow = SlowApp(0.05, transcript="bật đèn"), SlowApp(0.25, transcript="bật đèn")
    spk = Speaker(fast, slow)
    await run_real(store, [Lane(a, fast), Lane(b, slow)], settings, spk)
    assert spk.calls == 3
    for i in (1, 2):  # from the 2nd sentence the fast phone waits for the slow one before its mic tap
        assert spk.times[i] - fast.mic_on[i] < 0.1


async def test_lanes_with_different_audio_do_not_share_a_playback(env, tmp_path):
    """After "Sinh lại", one run may hold another WAV for the same sentence: play each its own."""
    import sqlite3

    store, a, b, settings = env
    w = wavs(store, a)
    other = tmp_path / "other.wav"
    other.write_bytes(b"RIFF")
    row_b = store.app_results(b)[0]
    with sqlite3.connect(tmp_path / "t.db") as c:
        c.execute("UPDATE app_results SET audio_snap=? WHERE id=?", (str(other), row_b["id"]))
    att = scripted_attempt({}, "x")
    await go(store, [Lane(a, object()), Lane(b, object())], settings, att)
    assert att.calls[:2] == [(w[0], (a,)), ("other.wav", (b,))]
    assert att.calls[2:] == [(w[1], (a, b)), (w[2], (a, b))]
