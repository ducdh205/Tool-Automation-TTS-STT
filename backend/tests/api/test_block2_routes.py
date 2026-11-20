from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.api.test_routes import EchoStt, create_set, verify_all, wait_job_end
from backend.tests.pipeline.fake_app import FakeApp
from backend.tests.pipeline.test_block2_one import no_sleep  # noqa: F401  (fake app helpers)
from backend.tests.pipeline.test_block1 import FakeTts
from tts_stt_tool.api.app import create_app
from tts_stt_tool.config import Settings

FIX = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    import tts_stt_tool.pipeline.block2 as b2

    monkeypatch.setattr(b2, "POLL_S", 0.001)
    fake = FakeApp()
    fake.pre = 0

    async def factory(serial):
        return fake

    tts = FakeTts()
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, tts=tts, stt=EchoStt(tts), manage_wyoming=False, device_factory=factory, player=fake)
    with TestClient(app) as c:
        yield c, app, fake, tmp_path


def fast_profile(c):
    p = next(x for x in c.get("/api/profiles").json() if x["name"] == "Vita Work (dev)")
    p.update(pre_delay_s=0, post_delay_s=0, listen_timeout_s=0.1, result_timeout_s=0.1)
    assert c.put(f"/api/profiles/{p['name']}", json=p).status_code == 200
    return p["name"]


def verified_set(c, tmp_path):
    set_id = create_set(c, tmp_path)
    verify_all(c, set_id)
    return set_id


def test_profiles_list_and_validation(ctx):
    c, *_ = ctx
    names = [p["name"] for p in c.get("/api/profiles").json()]
    assert "Vita Work (dev)" in names
    bad = c.get("/api/profiles").json()[0] | {"pre_delay_s": -1}
    assert c.put(f"/api/profiles/{bad['name']}", json=bad).status_code == 422


def test_app_run_end_to_end(ctx):
    c, app, fake, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    r = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name})
    assert r.status_code == 200, r.text
    run_id = r.json()["id"]
    wait_job_end(c)
    results = c.get(f"/api/app-runs/{run_id}/results").json()
    assert len(results) == 2
    assert [(x["status"], x["app_text"], x["error"]) for x in results] == [("Sai", fake.transcript, None)] * 2
    assert {x["status"] for x in results} == {"Sai"}
    runs = c.get(f"/api/audio-sets/{set_id}/app-runs").json()
    assert runs[0]["id"] == run_id and runs[0]["summary"] == {"Sai": 2}
    assert c.post(f"/api/app-runs/{run_id}/resume").status_code == 200
    wait_job_end(c)


def test_app_run_needs_verified_items(ctx):
    c, _, _, tmp_path = ctx
    set_id = create_set(c, tmp_path)  # block 1 not run: nothing Đạt
    r = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": "Vita Work (dev)"})
    assert r.status_code == 422


def test_unknown_profile_and_run(ctx):
    c, _, _, tmp_path = ctx
    set_id = verified_set(c, tmp_path)
    assert c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "S", "profile": "nope"}).status_code == 404
    assert c.get("/api/app-runs/999/results").status_code == 404


def test_node_at(ctx, monkeypatch):
    c, app, *_ = ctx

    async def dump(serial):
        return (FIX / "ui_home.xml").read_text(encoding="utf-8")

    monkeypatch.setattr(app.state.ctx.adb, "dump_ui", dump)
    r = c.get("/api/device/SER/node-at", params={"x": 360, "y": 1471})
    assert r.status_code == 200
    assert r.json()["label"] == "Nói để tạo việc"


def test_manual_input_and_pin_blocked_while_job_uses_the_phone(ctx):
    """Review2 #4: user taps / pin-mode dumps must not interfere with a running block 2 job."""
    import time

    c, app, fake, tmp_path = ctx
    fake.transcript = None  # nothing heard -> the job polls until result_timeout_s
    name = fast_profile(c)
    p = next(x for x in c.get("/api/profiles").json() if x["name"] == name) | {"result_timeout_s": 3}
    c.put(f"/api/profiles/{name}", json=p)
    set_id = verified_set(c, tmp_path)
    c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name})
    time.sleep(0.3)
    assert c.post("/api/device/SER/input", json={"action": "tap", "x": 1, "y": 1}).status_code == 409
    assert c.get("/api/device/SER/node-at", params={"x": 1, "y": 1}).status_code == 409
    assert c.get("/api/device").json()["busy"] == "SER"
    wait_job_end(c, timeout=30)
    assert c.get("/api/device").json()["busy"] is None


def test_app_run_on_selected_items_saves_shots(ctx):
    c, app, fake, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    items = c.get(f"/api/audio-sets/{set_id}/items").json()
    passed = [i["id"] for i in items if i["status"] == "Đạt"]
    r = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name, "item_ids": passed[:1]})
    assert r.status_code == 200, r.text
    run_id = r.json()["id"]
    wait_job_end(c)
    results = c.get(f"/api/app-runs/{run_id}/results").json()
    assert [x["item_id"] for x in results] == passed[:1]
    assert results[0]["status"] == "Sai"  # the fake app hears its own transcript
    shot = Path(results[0]["screenshot_path"])
    assert shot.is_file() and shot.parent == app.state.ctx.run_dir(run_id).resolve()


def test_app_run_selection_without_passed_items_is_422(ctx):
    c, _, _, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    skipped = [i["id"] for i in c.get(f"/api/audio-sets/{set_id}/items").json() if i["status"] != "Đạt"]
    runs_before = len(c.get(f"/api/audio-sets/{set_id}/app-runs").json())
    r = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name, "item_ids": skipped})
    assert r.status_code == 422 and r.json()["detail"] == "Không có câu Đạt nào trong các case đã chọn"
    assert len(c.get(f"/api/audio-sets/{set_id}/app-runs").json()) == runs_before
