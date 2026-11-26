"""/api/device… routes with an iPhone (fake go-ios + fake WebDriverAgent)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.tests.api.test_routes import EchoStt
from backend.tests.device.test_ios import FakeWda, xml
from backend.tests.pipeline.test_block1 import FakeTts
from tts_stt_tool.api.app import create_app
from tts_stt_tool.config import Settings
from tts_stt_tool.device.goios import GoIos, IosDeviceInfo
from tts_stt_tool.device.ios import IosHub
from tts_stt_tool.device.wda import WdaClient

UDID = "00008120-000C09D8266B601E"


class FakeGoIos(GoIos):
    def __init__(self):
        super().__init__(enabled=False)
        self.path = "ios.exe"  # "available"

    async def devices(self):
        return [IosDeviceInfo(UDID, "iPhone15,4", "26.2.1")]

    async def device_name(self, udid):
        return "iPhone 15"

    async def app_version(self, udid, bundle_id):
        return "0.1.0 (15)"


@pytest.fixture
def ios_client(tmp_path):
    wda = FakeWda([xml("ios_home.xml")])
    hub = IosHub(FakeGoIos(), wda=WdaClient(transport=httpx.MockTransport(wda.handler)))
    tts = FakeTts()
    app = create_app(Settings(data_dir=tmp_path), tts=tts, stt=EchoStt(tts), manage_wyoming=False,
                     player=object(), ios=hub)
    app.state.ctx.adb.path = None  # no Android phone in these tests
    with TestClient(app) as c:
        yield c, wda


def test_device_list_includes_iphone(ios_client):
    c, _ = ios_client
    s = c.get("/api/device").json()
    assert s["ios"] is True and s["adb"] is False and s["error"] is None
    assert s["devices"] == [{"serial": UDID, "state": "device", "model": "iPhone 15", "platform": "ios"}]


def test_screen_and_tap_in_pixels(ios_client):
    c, wda = ios_client
    r = c.get(f"/api/device/{UDID}/screen")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert c.post(f"/api/device/{UDID}/input", json={"action": "tap", "x": 588, "y": 2358}).status_code == 200
    assert wda.calls[-1] == ("POST", "/session/S1/wda/tap", {"x": 196, "y": 786})


def test_vietnamese_text_and_unsupported_key(ios_client):
    c, wda = ios_client
    assert c.post(f"/api/device/{UDID}/input", json={"action": "text", "text": "bật đèn"}).status_code == 200
    assert wda.calls[-1][2] == {"value": list("bật đèn")}
    assert c.post(f"/api/device/{UDID}/input", json={"action": "key", "key": "power"}).status_code == 503


def test_node_at_uses_pixels(ios_client):
    c, _ = ios_client
    r = c.get(f"/api/device/{UDID}/node-at", params={"x": 588, "y": 2358})
    assert r.status_code == 200
    j = r.json()
    assert j["label"].startswith("Nói để tạo việc") and j["bounds"] == [504, 2274, 675, 2442]


def test_wda_down_is_reported_per_device(tmp_path):
    def boom(req):
        raise httpx.ConnectError("refused")

    hub = IosHub(FakeGoIos(), wda=WdaClient(transport=httpx.MockTransport(boom)))
    tts = FakeTts()
    app = create_app(Settings(data_dir=tmp_path), tts=tts, stt=EchoStt(tts), manage_wyoming=False,
                     player=object(), ios=hub)
    app.state.ctx.adb.path = None
    with TestClient(app) as c:
        (d,) = c.get("/api/device").json()["devices"]
        assert d["state"] == "no_wda"
        assert c.get(f"/api/device/{UDID}/screen").status_code == 503
