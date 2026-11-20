"""A fake 'Vita Work' app driven like the real one (see plan 2, real-device findings)."""

from __future__ import annotations

from pathlib import Path

from tts_stt_tool.device.ui_tree import UiNode

MIC = (304, 1436, 416, 1507)
SHEET_MIC = (304, 1412, 416, 1507)
CLOSE = (624, 644, 712, 732)


def _n(label, bounds, cls="android.widget.Button"):
    return UiNode(text="", desc=label, cls=cls, bounds=bounds, clickable=cls.endswith("Button"))


class FakeApp:
    screen_w = 720

    def __init__(self, transcript: str | None = "chỉnh nhiệt độ ghế lái lên 24 độ", *, state: str = "home",
                 auto_stop: bool = False, sheet_opens: bool = True, mic_visible: bool = True,
                 launch_fixes: bool = True, silence_dumps: int | None = None,
                 keep_history: bool = False, mic_delay_checks: int = 0):
        self.transcript = transcript
        self.state = state
        self.auto_stop = auto_stop
        self.sheet_opens = sheet_opens
        self.mic_visible = mic_visible
        self.launch_fixes = launch_fixes
        self.keep_history = keep_history
        self.mic_delay_checks = mic_delay_checks  # mic goes live after N mic_active() checks
        self.mic_checks = 0
        self._mic_live = mic_delay_checks == 0
        self.bubbles: list[str] = []
        self.taps: list[str] = []
        self.launched = 0
        self.played: list[Path] = []
        # Like the real app: stops listening on its own if nothing is heard for a while.
        # Each dump takes ~2.5 s on the real phone, so "N dumps of silence" models that timeout.
        self.silence_dumps = silence_dumps
        self._silent = 0

    # -- DeviceDriver ----------------------------------------------------------
    async def nodes(self) -> list[UiNode]:
        if self.state == "listening" and not self.played and self.silence_dumps is not None:
            self._silent += 1
            if self._silent > self.silence_dumps:
                self.state = "idle"  # gave up: "Chưa nghe rõ"
        if self.state == "background":
            return [_n("Màn hình chính", (0, 0, 720, 1650), "android.view.View")]
        if self.state == "home":
            return [_n("Nói để tạo việc", MIC)] if self.mic_visible else [_n("Việc", (160, 1436, 300, 1507))]
        out = [_n("Tạo việc", (32, 660, 608, 716), "android.view.View"), _n("Đóng", CLOSE)]
        for i, b in enumerate(self.bubbles):
            y = 900 + i * 100
            out.append(_n(b, (300, y, 680, y + 40), "android.view.View"))
            out.append(_n("Câu này chưa phải một việc cần làm.", (32, y + 50, 624, y + 90), "android.view.View"))
        out.append(UiNode("", "", "android.widget.EditText", (32, 1212, 688, 1388), True))
        out.append(_n("Còn lại 1.000 ký tự", (567, 1356, 656, 1388), "android.view.View"))
        out.append(_n("Dừng nghe" if self.state == "listening" else "Bấm để nói", SHEET_MIC))
        return out

    async def tap(self, x: int, y: int) -> None:
        hit = [n for n in await self.nodes() if n.contains(x, y) and n.cls.endswith("Button")]
        label = hit[0].label if hit else f"({x},{y})"
        self.taps.append(label)
        if label == "Nói để tạo việc" and self.sheet_opens:
            self.state = "listening"
            self.mic_checks = 0
            self._mic_live = self.mic_delay_checks == 0
        elif label == "Dừng nghe":
            self._finish()
        elif label == "Bấm để nói":
            self.state = "listening"
        elif label == "Đóng":
            self.state = "home"
            if not self.keep_history:
                self.bubbles = []

    async def back(self) -> None:
        self.taps.append("BACK")
        if self.state in ("listening", "idle"):
            self.state = "home"
            self.bubbles = []

    async def mic_active(self) -> bool | None:
        self.mic_checks += 1
        if self.state == "listening" and self.mic_checks >= self.mic_delay_checks:
            self._mic_live = True
        return self.state == "listening" and self._mic_live

    async def launch(self, package: str) -> None:
        self.launched += 1
        if self.launch_fixes:
            self.state = "home"
            self.mic_visible = True

    # -- fake speaker ----------------------------------------------------------
    def play(self, path: Path) -> None:
        if self.state != "listening" or not self._mic_live:
            return  # nobody listening (or mic not live yet): audio is lost
        self.played.append(path)
        self._heard = True
        if self.auto_stop and self.state == "listening":
            self._finish()

    def _finish(self) -> None:
        self.state = "idle"
        if self.transcript is not None and getattr(self, "_heard", False):
            self.bubbles.append(self.transcript)
        self._heard = False


async def no_sleep(_s: float) -> None:
    return None
