import asyncio

import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.config import Settings
from tts_stt_tool.device.profile import AppProfile
from tts_stt_tool.models import InputItem
from tts_stt_tool.pipeline.block2 import AppCapture, OperationError, run_block2
from tts_stt_tool.store.db import AppStatus, ItemStatus, Store


def _item(tc, text):
    return InputItem(sheet="S", tc_id=tc, turn="1", feature="", priority="", region="",
                     speaker="👤 Người dùng", text_raw=text, expected="", source_row=5)


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "t.db")
    texts = ["bật đèn", "tắt đèn", "mở cốp", "đóng cốp", "bật quạt", "tắt quạt", "mở kính"]
    set_id = store.create_audio_set("s", "f.xlsx", ["S"], "v", [_item(str(i), t) for i, t in enumerate(texts)])
    for r in store.get_items(set_id):
        store.record_generated(r["id"], f"{r['id']}.wav", 1)
        store.record_verify(r["id"], r["text_tts"], compare(r["text_tts"], r["text_tts"]), ItemStatus.PASSED)
    run_id = store.create_app_run(set_id, "SER", "m", "p", None)
    return store, run_id, Settings(data_dir=tmp_path)


def scripted(answers):
    """run_one replacement: answers keyed by audio file name -> text | None | Exception."""
    seen_prev = []

    async def fake(dev, profile, wav, player, prev_bubbles=None):
        seen_prev.append(prev_bubbles)
        ans = answers.get(wav.name, "")
        if isinstance(ans, Exception):
            raise ans
        return AppCapture(text=ans, log=[f"play {wav.name}"], bubbles=[ans] if ans else [])

    fake.seen_prev = seen_prev
    return fake


async def go(store, run_id, settings, fake, cancel=None, emit=None):
    events = []
    await run_block2(store, run_id, object(), AppProfile(), object(), settings,
                     emit or events.append, cancel or asyncio.Event(), run_one=fake)
    return events


def by_text(store, run_id):
    return {r["text_tts"]: r for r in store.app_results(run_id)}


async def test_statuses(env):
    store, run_id, settings = env
    ids = {r["text_tts"]: r["item_id"] for r in store.app_results(run_id)}
    fake = scripted({f"{ids['bật đèn']}.wav": "bật đèn", f"{ids['tắt đèn']}.wav": "tắt đen",
                     f"{ids['mở cốp']}.wav": None, f"{ids['đóng cốp']}.wav": OperationError("Không thấy nút mic")})
    events = await go(store, run_id, settings, fake)
    r = by_text(store, run_id)
    assert r["bật đèn"]["status"] == AppStatus.PASSED.value
    assert r["tắt đèn"]["status"] == AppStatus.FAILED.value and r["tắt đèn"]["wer"] == 0.5
    assert r["mở cốp"]["status"] == AppStatus.FAILED.value and r["mở cốp"]["app_text"] == ""
    assert r["đóng cốp"]["status"] == AppStatus.OP_ERROR.value and "nút mic" in r["đóng cốp"]["error"]
    assert "play" in r["bật đèn"]["log"]
    kinds = [e.kind for e in events]
    assert "log" in kinds and kinds[-1] == "done"
    assert fake.seen_prev[1] == ["bật đèn"]  # chat state carried to the next sentence


async def test_five_op_errors_abort(env):
    """Review #5: phone unplugged."""
    store, run_id, settings = env
    fake = scripted({f"{r['item_id']}.wav": OperationError("adb: device not found") for r in store.app_results(run_id)})
    events = await go(store, run_id, settings, fake)
    assert events[-1].kind == "error" and "5 lỗi thao tác" in events[-1].message
    assert store.app_summary(run_id) == {AppStatus.OP_ERROR.value: 5, AppStatus.PENDING.value: 2}


async def test_resume_only_pending_and_op_errors(env):
    store, run_id, settings = env
    first = store.app_results(run_id)[0]
    store.record_app_result(first["id"], AppStatus.PASSED, "bật đèn", compare("bật đèn", "bật đèn"), None, "")
    fake = scripted({})
    await go(store, run_id, settings, fake)
    assert len(fake.seen_prev) == 6


async def test_cancel_after_first(env):
    store, run_id, settings = env
    cancel = asyncio.Event()
    events = []

    def emit(e):
        events.append(e)
        if e.kind == "item":
            cancel.set()

    await go(store, run_id, settings, scripted({}), cancel=cancel, emit=emit)
    assert events[-1].kind == "cancelled"
    assert store.app_summary(run_id)[AppStatus.PENDING.value] == 6
