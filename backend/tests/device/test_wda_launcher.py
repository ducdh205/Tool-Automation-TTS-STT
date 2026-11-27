"""WdaLauncher ("Kết nối iPhone") with fake go-ios, fake processes and a fake WDA."""

import json

import httpx
import pytest

from tts_stt_tool.device.goios import GoIos, GoIosError, IosDeviceInfo
from tts_stt_tool.device.wda import WdaClient
from tts_stt_tool.device.wda_launcher import WdaLauncher, explain, find_wda_bundle

UDID = "00008120-000C09D8266B601E"
WDA_ID = "com.facebook.WebDriverAgentRunner.xctrunner.5TC6MK9H6N"
APPS = json.dumps([{"CFBundleIdentifier": "com.vita.suite.stg"}, {"CFBundleIdentifier": WDA_ID}])


class Goios(GoIos):
    def __init__(self, devices=(UDID,), apps=APPS, error=None):
        super().__init__(enabled=False)
        self.path = "ios.exe"
        self._devices, self._apps, self._error = devices, apps, error

    async def devices(self):
        if self._error:
            raise GoIosError(self._error)
        return [IosDeviceInfo(u) for u in self._devices]

    async def run(self, *args):
        assert args[0] == "apps"
        return self._apps


class Proc:
    def __init__(self, exit_code=None):
        self.code = exit_code
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 1

    def wait(self, timeout=None):
        return self.code


class World:
    """WDA answers once both processes are running (after ``ready_after`` polls)."""

    def __init__(self, ready_after=1, mount=(0, "ok"), proc_exit=None, log_text=""):
        self.ready_after, self.mount, self.proc_exit, self.log_text = ready_after, mount, proc_exit, log_text
        self.spawned: list[tuple[list[str], Proc]] = []
        self.ran: list[list[str]] = []
        self.polls = 0
        self.preexisting = False

    def wda(self) -> WdaClient:
        def handler(req):
            started = len(self.spawned) == 2
            if started:
                self.polls += 1
            ready = self.preexisting or (started and self.polls > self.ready_after and self.proc_exit is None)
            if not ready:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"value": {"ready": True}})

        return WdaClient(transport=httpx.MockTransport(handler))

    def spawn(self, args, log):
        if self.log_text:
            log.write_text(self.log_text, encoding="utf-8")
        p = Proc(self.proc_exit if "xcuitest" in args else None)
        self.spawned.append((args, p))
        return p

    async def run(self, args, timeout):
        self.ran.append(args)
        return self.mount


def launcher(tmp_path, world: World, goios=None) -> WdaLauncher:
    return WdaLauncher(goios or Goios(), world.wda(), tmp_path, spawn=world.spawn, run=world.run,
                       ready_timeout_s=2, poll_s=0.01)


async def connect(lch: WdaLauncher) -> dict:
    lch.start()
    await lch.wait()
    return lch.snapshot()


async def test_connects_in_order(tmp_path):
    w = World()
    lch = launcher(tmp_path, w)
    s = await connect(lch)
    assert s["state"] == "running" and s["error"] is None
    assert s["udid"] == UDID and s["bundle"] == WDA_ID
    assert w.ran[0][-4:] == ["mounter", "auto-mount", "--udid", UDID]
    xcui, fwd = (a for a, _ in w.spawned)
    assert xcui[xcui.index("xcuitest") + 1] == WDA_ID
    assert "--userspace" in xcui and xcui[xcui.index("--udid") + 1] == UDID
    assert fwd == ["ios.exe", "forward", "8100", "8100", f"--udid={UDID}"]


async def test_already_running_wda_is_left_alone(tmp_path):
    w = World()
    w.preexisting = True
    s = await connect(launcher(tmp_path, w))
    assert s["state"] == "running" and s["external"] is True
    assert w.spawned == [] and w.ran == []


async def test_no_iphone(tmp_path):
    s = await connect(launcher(tmp_path, World(), Goios(devices=())))
    assert s["state"] == "error" and "Tin cậy" in s["error"]


async def test_wda_not_installed(tmp_path):
    s = await connect(launcher(tmp_path, World(), Goios(apps=json.dumps([{"CFBundleIdentifier": "x.y"}]))))
    assert s["state"] == "error" and "chưa cài WebDriverAgent" in s["error"]


async def test_mount_failure_explains_developer_mode(tmp_path):
    w = World(mount=(1, "pymobiledevice3.exceptions.DeveloperModeIsNotEnabledError"))
    s = await connect(launcher(tmp_path, w))
    assert s["state"] == "error" and "Chế độ nhà phát triển" in s["error"]
    assert s["detail"] and w.spawned == []


async def test_already_mounted_is_fine(tmp_path):
    s = await connect(launcher(tmp_path, World(mount=(1, "DeveloperDiskImage already mounted"))))
    assert s["state"] == "running"


async def test_wda_exits_with_expired_signature(tmp_path):
    w = World(proc_exit=1, log_text="ERROR Failed to launch: profile has expired")
    lch = launcher(tmp_path, w)
    s = await connect(lch)
    assert s["state"] == "error" and "hết hạn" in s["error"]
    assert all(p.poll() is not None for _, p in w.spawned)  # forward was stopped too


async def test_timeout(tmp_path):
    w = World(ready_after=10_000)
    s = await connect(launcher(tmp_path, w))
    assert s["state"] == "error" and "không trả lời" in s["error"]
    assert all(p.terminated for _, p in w.spawned)


async def test_crash_after_running_is_noticed_and_stop_kills(tmp_path):
    w = World()
    lch = launcher(tmp_path, w)
    assert (await connect(lch))["state"] == "running"
    w.spawned[0][1].code = 1  # WDA died (cable pulled)
    s = lch.snapshot()
    assert s["state"] == "error" and "Kết nối lại" in s["error"]
    assert w.spawned[1][1].terminated

    w2 = World()
    lch2 = launcher(tmp_path, w2)
    await connect(lch2)
    assert lch2.stop()["state"] == "idle"
    assert all(p.terminated for _, p in w2.spawned)


async def test_goios_error_is_explained(tmp_path):
    s = await connect(launcher(tmp_path, World(), Goios(error="dial unix usbmuxd: connection refused")))
    assert s["state"] == "error" and "Apple Devices" in s["error"]


@pytest.mark.parametrize(("apps", "want"), [
    ([{"CFBundleIdentifier": "com.foo.WebDriverAgentRunner"},
      {"CFBundleIdentifier": "com.foo.WebDriverAgentRunner.xctrunner"}], "com.foo.WebDriverAgentRunner.xctrunner"),
    ([{"CFBundleIdentifier": "a.b"}], None),
])
def test_find_wda_bundle(apps, want):
    assert find_wda_bundle('{"level":"info","msg":"x"}\n' + json.dumps(apps)) == want


def test_explain_unknown():
    assert explain("something odd") is None
