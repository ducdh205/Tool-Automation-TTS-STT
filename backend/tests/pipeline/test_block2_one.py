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
    """Real phone: a stray tap opened a task form; Back shows 'Bỏ thay đổi?'."""
    app = FakeApp(state="form")
    cap = await one(app)
    assert "Bỏ thay đổi" in app.taps
    assert app.drafts == 0
    assert app.launched == 0
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"


async def test_wrong_text_screenshot_taken_while_sheet_open():
    app = FakeApp(transcript="sai hoàn toàn")
    cap = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, is_correct=lambda t: False)
    assert cap.screenshot == b"\x89PNG-fake"
    assert app.shots == ["idle"]  # captured on the open sheet, before the closing Back
    assert app.state == "home"


async def test_correct_text_no_screenshot():
    app = FakeApp()
    cap = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, is_correct=lambda t: True)
    assert cap.screenshot is None and app.shots == []


async def test_no_text_heard_counts_as_wrong():
    app = FakeApp(transcript=None)
    seen = []
    cap = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, is_correct=lambda t: seen.append(t) or False)
    assert seen == [""] and cap.screenshot is not None


async def test_screencap_failure_keeps_result():
    app = FakeApp(transcript="sai")
    app.screencap_error = RuntimeError("adb")
    cap = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, is_correct=lambda t: False)
    assert cap.text == "sai" and cap.screenshot is None
    assert any("Không chụp được màn hình" in line for line in cap.log)


# --- app 2026-11: speaking opens a task form ("Bạn nói: “…”") -----------------
async def test_reads_heard_text_from_task_form():
    app = FakeApp(transcript="nộp bản thảo", form_after_speech=True)
    cap = await one(app)
    assert cap.text == "nộp bản thảo"
    assert any("App nhận: nộp bản thảo" in line for line in cap.log)


async def test_task_form_closed_by_discarding_never_keeping_a_draft():
    app = FakeApp(transcript="nộp bản thảo", form_after_speech=True)
    await one(app)
    assert app.state == "home"
    assert app.taps[-2:] == ["BACK", "Bỏ thay đổi"]
    assert app.drafts == 0 and "Tạo việc" not in app.taps


async def test_task_form_twice_in_a_row():
    app = FakeApp(transcript="nộp bản thảo", form_after_speech=True)
    await one(app)
    app.transcript = "gọi cho anh Huy"
    cap = await one(app)
    assert cap.text == "gọi cho anh Huy"
    assert app.launched == 0 and app.drafts == 0


async def test_task_form_wrong_text_photographed_on_the_form():
    app = FakeApp(transcript="nộp bản thảo", form_after_speech=True)
    cap = await run_one(app, AppProfile(), WAV, app, sleep=no_sleep, is_correct=lambda t: False)
    assert cap.screenshot is not None
    assert app.shots == ["heard_form"]


@pytest.mark.parametrize("state", ["heard_form", "heard_dialog"])
async def test_left_on_heard_form_recovers(state):
    """A previous run stopped on the form (or its dialog): discard it and carry on."""
    app = FakeApp(state=state, form_after_speech=True)
    app.heard = "câu cũ"
    cap = await one(app)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert "Bỏ thay đổi" in app.taps and app.drafts == 0


async def test_heard_prefix_off_falls_back_to_bubbles():
    app = FakeApp()
    cap = await run_one(app, AppProfile(heard_prefix=""), WAV, app, sleep=no_sleep)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"


# --- iPhone: no mic state, a fast UI dump --------------------------------------
class FakeIosApp(FakeApp):
    """iOS: ``mic_active`` is unknown; "Dừng nghe" shows once the mic is live (after N dumps)."""

    fast_ui = True

    def __init__(self, *a, live_after_dumps: int = 2, **kw):
        super().__init__(*a, **kw)
        self.live_after_dumps = live_after_dumps
        self.listen_dumps = 0

    async def nodes(self):
        if self.state == "listening" and not self._mic_live:
            self.listen_dumps += 1
            if self.listen_dumps >= self.live_after_dumps:
                self._mic_live = True
        return await super().nodes()

    def _sheet_nodes(self):
        out = super()._sheet_nodes()
        if self.state == "listening" and not self._mic_live:
            out = [n for n in out if n.label != "Dừng nghe"]
        return out

    async def tap(self, x, y):
        await super().tap(x, y)
        if self.state == "listening":
            self._mic_live, self.listen_dumps = False, 0

    async def mic_active(self):
        return None


async def test_ios_waits_for_stop_button_before_playing():
    app = FakeIosApp(live_after_dumps=3)
    cap = await one(app)
    assert app.played == [WAV]  # played only once "Dừng nghe" was on screen
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert app.taps == ["Nói để tạo việc", "Dừng nghe", "BACK"]


async def test_ios_stop_button_never_shows():
    app = FakeIosApp(live_after_dumps=10**6)
    with pytest.raises(OperationError, match="[Mm]ic"):
        await one(app)
    assert app.played == []


class FakeIosUatApp(FakeIosApp):
    """Vita UAT on iOS: the heard sentence shows as a chat bubble first, then the task form
    replaces it after ``form_after_dumps`` dumps (the real app: ~1 s)."""

    def __init__(self, *a, form_after_dumps: int = 2, **kw):
        super().__init__(*a, **kw)
        self.form_after_dumps = form_after_dumps
        self.bubble_dumps = 0

    async def nodes(self):
        if self.state == "idle" and self.bubbles and self.form_after_dumps is not None:
            self.bubble_dumps += 1
            if self.bubble_dumps > self.form_after_dumps:
                self.state, self.heard, self.bubbles = "heard_form", self.bubbles[-1], []
        return await super().nodes()

    async def back(self):
        if self.state == "idle" and self.bubbles and self.form_after_dumps is not None:
            # closing the chat does not stop the form: it opens on the home screen
            self.taps.append("BACK")
            self.state, self.heard, self.bubbles = "heard_form", self.bubbles[-1], []
            return
        await super().back()


async def test_ios_form_after_bubble_is_discarded():
    app = FakeIosUatApp(live_after_dumps=1, form_after_dumps=2)
    cap = await one(app)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert app.state == "home"  # the late form was closed with "Bỏ thay đổi", nothing left over
    assert app.taps[-2:] == ["BACK", "Bỏ thay đổi"]
    assert app.drafts == 0


async def test_ios_bubble_without_form_waits_briefly_only():
    app = FakeIosUatApp(live_after_dumps=1, form_after_dumps=None)  # "not a task": no form
    cap = await one(app)
    assert cap.text == "chỉnh nhiệt độ ghế lái lên 24 độ"
    assert app.taps[-1] == "BACK" and app.state == "home"
