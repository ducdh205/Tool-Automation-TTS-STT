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
    assert app.taps == ["Nói để tạo việc", "Dừng nghe", "BACK"]  # close with Back, not a stale tap
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
    assert app.taps[0] == "BACK"


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
    with pytest.raises(OperationError, match="Mic không bật"):
        await one(app)


async def test_plays_before_app_gives_up_listening():
    """Real phone: one dump ~2.5 s and the app stops after ~3 s of silence.
    Playback must not wait for a dump: only the baseline dump, which runs concurrently with
    playback, may happen before the audio starts."""
    app = FakeApp(silence_dumps=1)
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
    second = await one(app)
    assert second.text == "bật đèn trần"


async def test_history_kept_and_app_auto_stopped():
    app = FakeApp(keep_history=True, auto_stop=True)
    first = await one(app)
    app.transcript = "bật đèn trần"
    second = await one(app)
    assert second.text == "bật đèn trần"
    assert second.bubbles == ["chỉnh nhiệt độ ghế lái lên 24 độ", "bật đèn trần"]


async def test_waits_for_mic_before_playing():
    """Real phone: the mic starts 0.6-1+ s after tapping; audio played earlier is lost."""
    app = FakeApp(mic_delay_checks=3)
    cap = await one(app)
    assert app.played == [WAV]  # FakeApp drops audio played before the mic is live
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert app.mic_checks >= 3


async def test_mic_never_starts():
    app = FakeApp(mic_delay_checks=10**6)
    with pytest.raises(OperationError, match="[Mm]ic"):
        await one(app)
    assert app.played == []


# --- review 2 fixes -----------------------------------------------------------
async def test_app_stops_during_the_stop_check_dump():
    """Review2 #1: the dump shows 'Dừng nghe' but the app stops before the tap lands."""
    app = FakeApp(stop_during_dump=True)
    cap = await one(app)
    assert "Bấm để nói" not in app.taps
    assert "Dừng nghe" not in app.taps
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"


async def test_stale_history_with_auto_stop_is_not_reported():
    """Review2 #2a: chat kept, app auto-stops, app heard nothing -> no text (not the old bubble)."""
    app = FakeApp(keep_history=True, auto_stop=True)
    await one(app)
    app.transcript = None
    cap = await one(app)
    assert cap.text is None


async def test_sheet_gone_while_reading_is_op_error():
    """Review2 #2c: app navigated away -> do not read the home screen as bubbles."""
    app = FakeApp(transcript=None, leave_after_stop=True)
    with pytest.raises(OperationError, match="Tạo việc"):
        await one(app)


async def test_op_error_carries_log():
    """Review2 #5."""
    app = FakeApp(mic_delay_checks=10**6)
    with pytest.raises(OperationError) as ei:
        await one(app)
    assert any("Nói để tạo việc" in line for line in ei.value.log)


async def test_recovers_from_task_form_via_discard_dialog():
    """Real phone: a stray tap opened a task form; Back shows 'Ở lại' / 'Bỏ'."""
    app = FakeApp(state="form")
    cap = await one(app)
    assert "Bỏ" in app.taps
    assert app.launched == 0
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
