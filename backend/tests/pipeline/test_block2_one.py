from pathlib import Path

import pytest

from backend.tests.pipeline.fake_app import FakeApp, no_sleep
from tts_stt_tool.device.profile import AppProfile
from tts_stt_tool.pipeline.block2 import OperationError, run_one

WAV = Path("x.wav")


async def one(app: FakeApp):
    return await run_one(app, AppProfile(), WAV, app, sleep=no_sleep)


async def test_happy_path():
    app = FakeApp()
    cap = await one(app)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert cap.error is None
    assert app.taps == ["Nói để tạo việc", "Dừng nghe", "Đóng"]
    assert app.played == [WAV]
    assert app.state == "home"
    assert cap.log


async def test_app_stopped_by_itself_is_not_tapped_again():
    """Review #1: tapping the idle mic would start a new listen."""
    app = FakeApp(auto_stop=True)
    cap = await one(app)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert "Bấm để nói" not in app.taps
    assert "Dừng nghe" not in app.taps


async def test_nothing_heard_returns_none_not_error():
    app = FakeApp(transcript=None)
    cap = await one(app)
    assert cap.text is None
    assert cap.error is None
    assert app.state == "home"


async def test_starts_from_open_sheet():
    """Review #4."""
    app = FakeApp(state="idle")
    cap = await one(app)
    assert cap.text is not None
    assert app.taps[0] == "Đóng"


async def test_starts_from_background_relaunches_app():
    app = FakeApp(state="background")
    cap = await one(app)
    assert app.launched == 1
    assert cap.text is not None


async def test_mic_never_found():
    app = FakeApp(mic_visible=False, launch_fixes=False)
    with pytest.raises(OperationError, match="Nói để tạo việc"):
        await one(app)


async def test_sheet_never_opens():
    app = FakeApp(sheet_opens=False)
    with pytest.raises(OperationError, match="Dừng nghe"):
        await one(app)


async def test_plays_before_app_gives_up_listening():
    """Real phone: one dump ~2.5 s and the app stops after ~3 s of silence.
    Playback must start without waiting for a confirming dump."""
    app = FakeApp(silence_dumps=0)
    cap = await one(app)
    assert app.played == [WAV]
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"


@pytest.mark.live
async def test_live_real_phone():
    """Manual: phone connected with the app on its home screen; PC speakers on."""
    from tts_stt_tool.compare.score import compare
    from tts_stt_tool.device.adb import Adb
    from tts_stt_tool.device.player import WinSoundPlayer
    from tts_stt_tool.pipeline.block2 import AdbDriver
    from tts_stt_tool.stt.server_manager import REPO_ROOT

    adb = Adb()
    serial = next(d.serial for d in await adb.devices() if d.state == "device")
    dev = await AdbDriver.connect(adb, serial)
    cap = await run_one(dev, AppProfile(), REPO_ROOT / "data" / "spike" / "t1.wav", WinSoundPlayer())
    print("\n".join(cap.log))
    assert cap.text is not None  # what the app heard; its accuracy is what block 2 measures
    assert compare("Chỉnh nhiệt độ ghế lái lên hai mươi tư độ", cap.text).wer <= 0.5


async def test_history_kept_between_items():
    """Real app sometimes keeps the chat when the sheet is reopened."""
    app = FakeApp(keep_history=True)
    first = await one(app)
    app.transcript = "bật đèn trần"
    second = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, prev_bubbles=first.bubbles)
    assert second.text == "bật đèn trần"


async def test_history_kept_and_app_auto_stopped():
    app = FakeApp(keep_history=True, auto_stop=True)
    first = await one(app)
    app.transcript = "bật đèn trần"
    second = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, prev_bubbles=first.bubbles)
    assert second.text == "bật đèn trần"
    assert second.bubbles == ["chỉnh nhiệt độ ghế lái lên 24 độ", "bật đèn trần"]
