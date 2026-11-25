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


def test_app_run_needs_generated_audio(ctx):
    c, _, _, tmp_path = ctx
    set_id = create_set(c, tmp_path)  # block 1 not run: no audio
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


def test_app_run_selection_without_audio_is_422(ctx):
    c, _, _, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    skipped = [i["id"] for i in c.get(f"/api/audio-sets/{set_id}/items").json() if not i["audio_path"]]
    assert skipped
    runs_before = len(c.get(f"/api/audio-sets/{set_id}/app-runs").json())
    r = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name, "item_ids": skipped})
    assert r.status_code == 422 and r.json()["detail"] == "Không có câu nào có audio trong các case đã chọn"
    assert len(c.get(f"/api/audio-sets/{set_id}/app-runs").json()) == runs_before


def finished_run(c, tmp_path):
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    run_id = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name}).json()["id"]
    wait_job_end(c)
    return set_id, run_id


def test_form_report_endpoint(ctx):
    c, _, _, tmp_path = ctx
    _, run_id = finished_run(c, tmp_path)
    r = c.post(f"/api/app-runs/{run_id}/form-report")
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]
    assert f"Phien{run_id}.xlsx" in r.headers["content-disposition"]
    assert c.post("/api/app-runs/999/form-report").status_code == 404


def test_export_zip_endpoint(ctx):
    import io
    import zipfile

    c, app, _, tmp_path = ctx
    _, run_id = finished_run(c, tmp_path)
    r = c.post(f"/api/app-runs/{run_id}/export-zip", json={"audio": "selected"})
    assert r.status_code == 422 and r.json()["detail"] == "Chưa chọn case nào"
    r = c.post(f"/api/app-runs/{run_id}/export-zip", json={})
    assert r.status_code == 200, r.text
    url = r.json()["download_url"]
    assert url.startswith("/api/exports/")
    got = c.get(url)  # a plain GET: the browser streams it to disk instead of holding a blob
    assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
    assert f"Phien{run_id}_" in got.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(got.content)).namelist()
    assert any(n.endswith("manhinh.png") for n in names)  # the fake app's answers are wrong -> screenshots
    assert any(n.endswith("thong_tin_phien.txt") for n in names)
    assert list(app.state.ctx.reports.rglob("*.zip")) == []  # deleted after sending
    assert c.get(url).status_code == 404  # one download per export
    assert c.get("/api/exports/not-a-token").status_code == 404
    assert c.post("/api/app-runs/999/export-zip", json={}).status_code == 404


def test_failed_zip_build_leaves_no_file(ctx, monkeypatch):
    import tts_stt_tool.api.routes as routes

    c, app, _, tmp_path = ctx
    _, run_id = finished_run(c, tmp_path)

    def broken(store, run_id, settings, out, *a, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"PK-partial")
        raise OSError("disk full")

    monkeypatch.setattr(routes, "build_session_zip", broken)
    with pytest.raises(OSError):
        c.post(f"/api/app-runs/{run_id}/export-zip", json={})
    assert list(app.state.ctx.reports.rglob("*.zip")) == []


def test_delete_audio_set_removes_app_run_files(ctx):
    c, app, _, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    run_id = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name}).json()["id"]
    wait_job_end(c)
    run_dir = app.state.ctx.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "shot.png").write_bytes(b"png")

    assert c.delete(f"/api/audio-sets/{set_id}").status_code == 200
    assert not run_dir.exists()
    assert c.get(f"/api/app-runs/{run_id}/results").status_code == 404


def test_clear_all_data_removes_outputs_and_keeps_settings(ctx):
    c, app, _, tmp_path = ctx
    name = fast_profile(c)
    set_id = verified_set(c, tmp_path)
    run_id = c.post(f"/api/audio-sets/{set_id}/app-runs", json={"serial": "SER", "profile": name}).json()["id"]
    wait_job_end(c)
    actx = app.state.ctx
    run_dir = actx.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "shot.png").write_bytes(b"png")
    assert c.post(f"/api/audio-sets/{set_id}/report?format=csv").status_code == 200
    assert c.put("/api/settings", json={**c.get("/api/settings").json(), "wer_threshold": 0.2}).status_code == 200
    assert any(actx.cache.root.iterdir()) and any(actx.reports.iterdir()) and any(actx.uploads.iterdir())

    r = c.delete("/api/data")

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "sets": 1}
    assert c.get("/api/audio-sets").json() == []
    assert c.get(f"/api/app-runs/{run_id}/results").status_code == 404
    for d in (actx.cache.root, actx.reports, actx.uploads, actx.settings.data_dir / "app_runs"):
        assert not d.exists() or not any(d.iterdir()), d
    # kept: settings, app profiles
    assert (tmp_path / "settings.json").is_file()
    assert c.get("/api/settings").json()["wer_threshold"] == 0.2
    assert any(p["name"] == name for p in c.get("/api/profiles").json())
    # the tool keeps working: a new set can be generated into the emptied audio cache
    new_id = create_set(c, tmp_path)
    verify_all(c, new_id)


def test_profile_between_delay(ctx):
    c, *_ = ctx
    p = c.get("/api/profiles").json()[0]
    assert p["between_delay_s"] == 0
    assert c.put(f"/api/profiles/{p['name']}", json=p | {"between_delay_s": 3}).status_code == 200
    assert next(x for x in c.get("/api/profiles").json() if x["name"] == p["name"])["between_delay_s"] == 3
    assert c.put(f"/api/profiles/{p['name']}", json=p | {"between_delay_s": -1}).status_code == 422
    assert c.put(f"/api/profiles/{p['name']}", json=p | {"between_delay_s": 61}).status_code == 422
    old = {k: v for k, v in p.items() if k != "between_delay_s"}  # older clients omit the field
    assert c.put(f"/api/profiles/{p['name']}", json=old).status_code == 200
