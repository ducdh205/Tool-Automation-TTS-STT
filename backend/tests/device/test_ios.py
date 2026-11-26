"""IosDriver / WdaClient against a fake WebDriverAgent, and go-ios output parsing."""

import base64
import json
import struct
from pathlib import Path

import httpx
import pytest

from tts_stt_tool.device.goios import GoIosError, last_json, parse_app_version, parse_list
from tts_stt_tool.device.ios import IosDriver, IosHub, app_frame
from tts_stt_tool.device.wda import WdaClient, WdaError

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def fake_png(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\0" * 8


class FakeWda:
    """Records calls; serves fixture XML as /source."""

    def __init__(self, sources: list[str], size=(393, 852)) -> None:
        self.sources = list(sources)
        self.size = size
        self.calls: list[tuple[str, str, dict | None]] = []
        self.session = "S1"
        self.stale_once = False

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        path = req.url.path
        self.calls.append((req.method, path, body))
        ok = lambda v=None, **kw: httpx.Response(200, json={"value": v, "sessionId": self.session, **kw})  # noqa: E731
        if path == "/status":
            return ok({"ready": True})
        if path == "/source":
            return ok(self.sources.pop(0) if len(self.sources) > 1 else self.sources[0])
        if path == "/screenshot":
            return ok(base64.b64encode(fake_png(self.size[0] * 3, self.size[1] * 3)).decode())
        if path.startswith("/session/"):
            if self.stale_once:
                self.stale_once = False
                return httpx.Response(404, json={"value": {"error": "invalid session id", "message": "x"}})
            if path.endswith("/window/size"):
                return ok({"width": self.size[0], "height": self.size[1]})
            return ok(None)
        if path == "/session":
            return ok({"sessionId": self.session})
        return httpx.Response(404, json={"value": {"error": "unknown command", "message": path}})


def client(fake: FakeWda) -> WdaClient:
    return WdaClient(transport=httpx.MockTransport(fake.handler))


def xml(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


async def no_sleep(_s: float) -> None:
    return None


async def test_driver_connect_and_nodes():
    fake = FakeWda([xml("ios_home.xml")])
    d = await IosDriver.connect(client(fake))
    assert (d.screen_w, d.screen_h) == (393, 852)
    assert any(n.label.startswith("Nói để tạo việc") for n in await d.nodes())
    assert await d.mic_active() is None and d.fast_ui


async def test_rotated_dump_is_read_again():
    fake = FakeWda([xml("ios_home_rotated.xml"), xml("ios_home.xml")])
    d = IosDriver(client(fake), 393, 852, sleep=no_sleep)
    assert app_frame(xml("ios_home_rotated.xml")) == (852, 393)
    nodes = await d.nodes()
    mic = next(n for n in nodes if n.label.startswith("Nói để tạo việc"))
    assert mic.center == (196, 786)  # from the second (portrait) dump
    assert [c[1] for c in fake.calls].count("/source") == 2


async def test_tap_uses_session_and_recreates_stale_one():
    fake = FakeWda([xml("ios_home.xml")])
    d = IosDriver(client(fake), 393, 852)
    await d.tap(10, 20)
    assert fake.calls[-1] == ("POST", "/session/S1/wda/tap", {"x": 10, "y": 20})
    fake.stale_once = True
    await d.tap(1, 2)
    assert fake.calls[-1] == ("POST", "/session/S1/wda/tap", {"x": 1, "y": 2})


async def test_back_taps_close_button():
    fake = FakeWda([xml("ios_listening.xml")])
    d = IosDriver(client(fake), 393, 852)
    await d.back()
    assert fake.calls[-1] == ("POST", "/session/S1/wda/tap", {"x": 365, "y": 545})  # "Đóng" 341,521 48x48


async def test_back_without_button_swipes_from_left_edge():
    fake = FakeWda([xml("ios_home.xml")])
    d = IosDriver(client(fake), 393, 852)
    await d.back()
    method, path, body = fake.calls[-1]
    assert path == "/session/S1/wda/dragfromtoforduration" and body["fromX"] == 1


async def test_keys_and_unicode_text():
    fake = FakeWda([xml("ios_home.xml")])
    d = IosDriver(client(fake), 393, 852)
    await d.text("sữa")
    assert fake.calls[-1][2] == {"value": ["s", "ữ", "a"]}
    await d.key("volup")
    assert fake.calls[-1][2] == {"name": "volumeUp"}
    with pytest.raises(WdaError):
        await d.key("recents")


async def test_hub_maps_screenshot_pixels_to_points():
    fake = FakeWda([xml("ios_home.xml")])
    hub = IosHub(wda=client(fake))
    await hub.tap_px("U", 588, 2358)
    assert fake.calls[-1] == ("POST", "/session/S1/wda/tap", {"x": 196, "y": 786})
    nodes, scale = await hub.nodes_px("U")
    assert scale == 3.0 and nodes


async def test_wda_down_raises_wda_error():
    def boom(req):
        raise httpx.ConnectError("refused")

    wda = WdaClient(transport=httpx.MockTransport(boom))
    assert await wda.ready() is False
    with pytest.raises(WdaError, match="WebDriverAgent"):
        await wda.source()


GOIOS_LIST = """{"time":"x","level":"WARN","msg":"go-ios agent is not running."}
{"deviceList":[{"Udid":"00008120-000C09D8266B601E","ProductName":"iPhone OS","ProductType":"iPhone15,4","ProductVersion":"26.2.1","ConnectionType":"USB"}]}
"""


def test_goios_parse_list():
    (d,) = parse_list(GOIOS_LIST)
    assert (d.udid, d.product_type, d.version) == ("00008120-000C09D8266B601E", "iPhone15,4", "26.2.1")
    assert parse_list('{"deviceList":[]}') == []


def test_goios_parse_app_version():
    out = ('{"level":"INFO","msg":"no udid"}\n'
           '[{"CFBundleIdentifier":"com.other"},'
           '{"CFBundleIdentifier":"com.vita.suite.dev","CFBundleShortVersionString":"0.1.0","CFBundleVersion":"15"}]')
    assert parse_app_version(out, "com.vita.suite.dev") == "0.1.0 (15)"
    assert parse_app_version(out, "com.missing") is None


def test_goios_last_json_without_answer():
    with pytest.raises(GoIosError):
        last_json('{"level":"WARN","msg":"x"}\n')
