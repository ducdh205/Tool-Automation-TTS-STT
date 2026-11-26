"""iPhone backend: ``IosDriver`` (block 2 ``DeviceDriver`` over WebDriverAgent) and ``IosHub``
(discovery through go-ios + manual control from the device panel, in screenshot pixels)."""

from __future__ import annotations

import asyncio
import re
import struct
from collections.abc import Awaitable, Callable

from tts_stt_tool.device.goios import GoIos, GoIosError
from tts_stt_tool.device.ui_tree import UiNode, find, parse_wda_source
from tts_stt_tool.device.wda import WdaClient, WdaError

# iOS has no Back key: close / go back by tapping one of these (fresh dump), else edge-swipe.
BACK_LABELS = ("Đóng", "Quay lại", "Huỷ", "Hủy", "Back", "Close", "Cancel")
_APP_SIZE = re.compile(r'<XCUIElementTypeApplication\b[^>]*?\swidth="(\d+)"[^>]*?\sheight="(\d+)"')
Sleep = Callable[[float], Awaitable[None]]


def png_width(png: bytes) -> int:
    return struct.unpack(">I", png[16:20])[0]


def app_frame(xml: str) -> tuple[int, int] | None:
    m = _APP_SIZE.search(xml)
    return (int(m[1]), int(m[2])) if m else None


class IosDriver:
    """``DeviceDriver`` over WDA. Points everywhere; ``scale`` converts screenshot pixels."""

    fast_ui = True  # /source takes ~0.2 s: block 2 waits for the stop button instead of the mic state

    def __init__(self, wda: WdaClient, screen_w: int, screen_h: int, sleep: Sleep = asyncio.sleep) -> None:
        self.wda, self.screen_w, self.screen_h = wda, screen_w, screen_h
        self._sleep = sleep
        self._scale: float | None = None

    @classmethod
    async def connect(cls, wda: WdaClient) -> IosDriver:
        w, h = await wda.window_size()
        return cls(wda, w, h)

    async def nodes(self) -> list[UiNode]:
        """A dump taken right after (re)launch can report the app frame rotated: read it again."""
        xml = await self.wda.source()
        frame = app_frame(xml)
        if frame and frame != (self.screen_w, self.screen_h):
            self.screen_w, self.screen_h = await self.wda.window_size()
            if frame != (self.screen_w, self.screen_h):
                await self._sleep(0.5)
                xml = await self.wda.source()
        return parse_wda_source(xml)

    async def tap(self, x: int, y: int) -> None:
        await self.wda.tap(x, y)

    async def back(self) -> None:
        nodes = await self.nodes()
        for label in BACK_LABELS:
            n = find(nodes, label)
            if n is not None:
                await self.wda.tap(*n.center)
                return
        h = self.screen_h
        await self.wda.drag(1, h // 2, int(self.screen_w * 0.7), h // 2, 0.3)

    async def launch(self, package: str) -> None:
        await self.wda.launch(package)

    async def mic_active(self) -> bool | None:
        return None  # iOS does not tell other processes who records

    async def screencap(self) -> bytes:
        png = await self.wda.screenshot()
        if self.screen_w:
            self._scale = png_width(png) / self.screen_w
        return png

    async def scale(self) -> float:
        """Screenshot pixels per point (3.0 on an iPhone 15)."""
        if self._scale is None:
            await self.screencap()
        return self._scale or 1.0

    # -- manual control (points) ------------------------------------------------
    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        await self.wda.drag(x1, y1, x2, y2, duration_ms / 1000)

    async def key(self, key: str) -> None:
        if key == "back":
            await self.back()
        elif key == "home":
            await self.wda.home()
        elif key == "volup":
            await self.wda.press_button("volumeUp")
        elif key == "voldown":
            await self.wda.press_button("volumeDown")
        elif key == "enter":
            await self.wda.keys("\n")
        elif key == "del":
            await self.wda.keys("\b")
        else:
            raise WdaError(f"iPhone không có phím '{key}'")

    async def text(self, text: str) -> None:
        await self.wda.keys(text)


class IosHub:
    """iPhones seen by go-ios; the one WDA instance (``wda_url``) drives them."""

    def __init__(self, goios: GoIos | None = None, wda_url: str = "http://127.0.0.1:8100",
                 wda: WdaClient | None = None) -> None:
        self.goios = goios or GoIos()
        self.wda = wda or WdaClient(wda_url)
        self._udids: set[str] = set()
        self._driver: IosDriver | None = None
        self._driver_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return self.goios.available

    async def devices(self) -> list[dict]:
        """``[{serial, state, model, platform}]``; state "device" when WDA answers, else "no_wda"."""
        if not self.available:
            return []
        found = await self.goios.devices()
        self._udids = {d.udid for d in found}
        if not found:
            return []
        ready = await self.wda.ready()
        out = []
        for d in found:
            try:
                model = await self.goios.device_name(d.udid)
            except GoIosError:
                model = None
            out.append({"serial": d.udid, "state": "device" if ready else "no_wda",
                        "model": model or d.product_type, "platform": "ios"})
        return out

    async def is_ios(self, serial: str) -> bool:
        if serial in self._udids:
            return True
        if not self.available:
            return False
        try:
            await self.devices()
        except GoIosError:
            return False
        return serial in self._udids

    async def driver(self, serial: str) -> IosDriver:  # noqa: ARG002 — one WDA, one phone
        async with self._driver_lock:
            if self._driver is None:
                self._driver = await IosDriver.connect(self.wda)
            return self._driver

    async def app_version(self, serial: str, bundle_id: str) -> str | None:
        return await self.goios.app_version(serial, bundle_id)

    async def model(self, serial: str) -> str | None:
        try:
            return await self.goios.device_name(serial)
        except GoIosError:
            return None

    # -- device panel: screenshot pixels ------------------------------------------
    async def screencap(self, serial: str) -> bytes:
        return await (await self.driver(serial)).screencap()

    async def _pt(self, serial: str, *xy: int) -> list[int]:
        s = await (await self.driver(serial)).scale()
        return [round(v / s) for v in xy]

    async def tap_px(self, serial: str, x: int, y: int) -> None:
        await (await self.driver(serial)).tap(*await self._pt(serial, x, y))

    async def swipe_px(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        d = await self.driver(serial)
        await d.swipe(*await self._pt(serial, x1, y1, x2, y2), duration_ms)

    async def nodes_px(self, serial: str) -> tuple[list[UiNode], float]:
        """Nodes (bounds in points) and the pixel scale, for "pin a button"."""
        d = await self.driver(serial)
        return await d.nodes(), await d.scale()
