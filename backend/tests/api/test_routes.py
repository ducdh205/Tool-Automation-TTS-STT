import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.helpers import FORM_SHEET, build_mini_form
from backend.tests.pipeline.test_block1 import FakeTts
from tts_stt_tool.api.app import create_app
from tts_stt_tool.config import Settings
from tts_stt_tool.tts.base import VoiceInfo


class EchoStt:
    """Reference STT that 'hears' exactly what the fake TTS put in the audio."""

    def __init__(self, tts):
        self.tts = tts

    async def transcribe(self, audio, sr):
        return self.tts.text_of(audio)


@pytest.fixture
def client(tmp_path):
    tts = FakeTts()
    app = create_app(Settings(data_dir=tmp_path), tts=tts, stt=EchoStt(tts), manage_wyoming=False)
    with TestClient(app) as c:
        yield c


def upload_form(client, tmp_path):
    p = build_mini_form(tmp_path / "mini.xlsx")
    with p.open("rb") as f:
        r = client.post("/api/files/inspect", files={"file": ("mini.xlsx", f)})
    assert r.status_code == 200, r.text
    return r.json()


FORM_MAPPING = {
    "header_row": 4, "id_col": "TC_ID", "text_col": "Câu nói (utterance)", "region_col": "Vùng miền",
    "expected_col": "Kết quả mong đợi", "turn_col": "Bước / Lượt",
}


def create_set(client, tmp_path):
    info = upload_form(client, tmp_path)
    r = client.post("/api/audio-sets", json={"file_id": info["file_id"], "sheets": [FORM_SHEET], "name": "bộ 1",
                                             "mapping": FORM_MAPPING})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def wait_job_end(client, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        if client.get("/api/jobs/current").json() is None:
            return
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def verify_all(client, set_id):
    """Generate then verify every row (what the old combined /block1 job did)."""
    assert client.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
    wait_job_end(client)
    assert client.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
    wait_job_end(client)


def statuses(client, set_id):
    return {i["id"]: i["status"] for i in client.get(f"/api/audio-sets/{set_id}/items").json()}


def test_inspect_lists_sheets(client, tmp_path):
    info = upload_form(client, tmp_path)
    assert info["sheets"] == ["Tổng hợp", "Hướng dẫn", FORM_SHEET]
    assert "is_form" not in info


def test_preview_route(client, tmp_path):
    info = upload_form(client, tmp_path)
    ok = client.post("/api/files/preview", json={"file_id": info["file_id"], "sheet": FORM_SHEET, "header_row": 4})
    assert ok.status_code == 200
    assert ok.json()["row_count"] == 4
    assert ok.json()["suggestions"]["id_col"] == "TC_ID"
    for bad in (99, 0):
        r = client.post("/api/files/preview", json={"file_id": info["file_id"], "sheet": FORM_SHEET, "header_row": bad})
        assert r.status_code == 422


def test_create_set_missing_column_names_sheet(client, tmp_path):
    info = upload_form(client, tmp_path)
    r = client.post("/api/audio-sets", json={"file_id": info["file_id"], "sheets": [FORM_SHEET, "Tổng hợp"],
                                             "name": "x", "mapping": FORM_MAPPING})
    assert r.status_code == 422
    assert "Tổng hợp" in r.json()["detail"]
    assert client.get("/api/audio-sets").json() == []


def test_create_set_rejects_region_conflict_and_missing_sheets(client, tmp_path):
    info = upload_form(client, tmp_path)
    both = {**FORM_MAPPING, "region_value": "NAM-HCM"}
    r = client.post("/api/audio-sets", json={"file_id": info["file_id"], "sheets": [FORM_SHEET], "name": "x",
                                             "mapping": both})
    assert r.status_code == 422
    r = client.post("/api/audio-sets", json={"file_id": info["file_id"], "sheets": [], "name": "x",
                                             "mapping": FORM_MAPPING})
    assert r.status_code == 422


def test_create_set_keeps_form_cells(client, tmp_path):
    set_id = create_set(client, tmp_path)
    cells = client.app.state.ctx.store.form_cells(set_id)
    assert len(cells) == 3 and all(len(v) == 36 for v in cells.values())


def test_voice_preview_caches_a_wav_for_the_selected_preset(client, monkeypatch):
    ctx = client.app.state.ctx
    tts = ctx.tts
    voice_id = "Quang Sơn"
    monkeypatch.setattr(tts, "voices", lambda: [VoiceInfo(voice_id, "Quang Sơn — Nam · Trung · Tự nhiên")])
    synthesize = tts.synthesize
    voices_used = []

    def record_voice(text, voice, attempt):
        voices_used.append(voice)
        return synthesize(text, voice, attempt)

    monkeypatch.setattr(tts, "synthesize", record_voice)
    assert client.get("/api/voices/preview", params={"voice_id": "Unknown"}).status_code == 404
    first = client.get("/api/voices/preview", params={"voice_id": voice_id})
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert first.content.startswith(b"RIFF")
    second = client.get("/api/voices/preview", params={"voice_id": voice_id})
    assert second.content == first.content
    assert voices_used == [voice_id]
    assert client.get("/api/settings").json()["voice"] == "Ngọc Huyền"


def test_inspect_csv_returns_columns(client, tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("id,cau\n1,Bật đèn\n", encoding="utf-8")
    with p.open("rb") as f:
        info = client.post("/api/files/inspect", files={"file": ("a.csv", f)}).json()
    assert info["sheets"] == []
    pv = client.post("/api/files/preview", json={"file_id": info["file_id"], "sheet": None, "header_row": 1}).json()
    assert pv["columns"] == ["id", "cau"]
    r = client.post("/api/audio-sets", json={"file_id": info["file_id"], "sheets": [], "name": "csv",
                                             "mapping": {"text_col": "cau", "id_col": "id"}})
    assert r.status_code == 200
    items = client.get(f"/api/audio-sets/{r.json()['id']}/items").json()
    assert items[0]["text_tts"] == "Bật đèn"


def test_create_set_and_items(client, tmp_path):
    set_id = create_set(client, tmp_path)
    items = client.get(f"/api/audio-sets/{set_id}/items").json()
    assert [i["status"] for i in items] == ["Chờ", "Chờ", "Không áp dụng"]
    only_skipped = client.get(f"/api/audio-sets/{set_id}/items", params={"status": "Không áp dụng"}).json()
    assert len(only_skipped) == 1
    sets = client.get("/api/audio-sets").json()
    assert sets[0]["id"] == set_id


def test_patch_item_text(client, tmp_path):
    set_id = create_set(client, tmp_path)
    skipped = client.get(f"/api/audio-sets/{set_id}/items").json()[2]
    r = client.patch(f"/api/items/{skipped['id']}", json={"text_tts": "Bật đồng bộ"})
    assert r.status_code == 200
    assert r.json()["status"] == "Chờ"
    assert client.patch(f"/api/items/{skipped['id']}", json={"text_tts": "   "}).status_code == 422
    assert client.patch("/api/items/99999", json={"enabled": False}).status_code == 404


def test_block1_run_audio_and_report(client, tmp_path):
    set_id = create_set(client, tmp_path)
    verify_all(client, set_id)
    summary = client.get(f"/api/audio-sets/{set_id}/summary").json()
    assert summary["Đạt"] == 2
    item = client.get(f"/api/audio-sets/{set_id}/items").json()[0]
    audio = client.get(f"/api/items/{item['id']}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    rep = client.post(f"/api/audio-sets/{set_id}/report")
    assert rep.status_code == 200
    assert "spreadsheetml" in rep.headers["content-type"]
    csv = client.post(f"/api/audio-sets/{set_id}/report", params={"format": "csv"})
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")


def test_second_job_while_running_is_409(tmp_path):
    class SlowStt:
        async def transcribe(self, audio, sr):
            import asyncio
            await asyncio.sleep(0.5)
            return "x"

    app = create_app(Settings(data_dir=tmp_path), tts=FakeTts(), stt=SlowStt(), manage_wyoming=False)
    with TestClient(app) as c:
        set_id = create_set(c, tmp_path)
        assert c.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
        wait_job_end(c)
        assert c.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
        assert c.post(f"/api/audio-sets/{set_id}/verify").status_code == 409
        assert c.post(f"/api/audio-sets/{set_id}/regenerate", json={"item_ids": None}).status_code in (409, 422)
        job = c.get("/api/jobs/current").json()
        assert c.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
        wait_job_end(c)


def test_websocket_receives_events(client, tmp_path):
    set_id = create_set(client, tmp_path)
    with client.websocket_connect("/ws") as ws:
        client.post(f"/api/audio-sets/{set_id}/generate")
        kinds = []
        while True:
            e = ws.receive_json()
            kinds.append(e["kind"])
            if e["kind"] in ("done", "error", "cancelled"):
                break
    assert kinds.count("item") == 2
    assert kinds[-1] == "done"


def test_settings_roundtrip_and_health(client):
    s = client.get("/api/settings").json()
    assert s["max_regen"] == 3
    s["max_regen"] = 4
    assert client.put("/api/settings", json=s).status_code == 200
    assert client.get("/api/settings").json()["max_regen"] == 4
    h = client.get("/api/health").json()
    assert set(h) >= {"wyoming", "gpu", "job"}


def test_unknown_set_404(client):
    assert client.get("/api/audio-sets/999/items").status_code == 404
    for action in ("generate", "verify", "regenerate"):
        assert client.post(f"/api/audio-sets/999/{action}").status_code == 404


# --- final review fixes -------------------------------------------------------
def test_patch_rejects_text_without_words(client, tmp_path):
    set_id = create_set(client, tmp_path)
    item = client.get(f"/api/audio-sets/{set_id}/items").json()[0]
    assert client.patch(f"/api/items/{item['id']}", json={"text_tts": "👍"}).status_code == 422


def test_patch_text_is_nfc(client, tmp_path):
    import unicodedata

    set_id = create_set(client, tmp_path)
    item = client.get(f"/api/audio-sets/{set_id}/items").json()[0]
    r = client.patch(f"/api/items/{item['id']}", json={"text_tts": unicodedata.normalize("NFD", "Bật hòa")})
    assert r.json()["text_tts"] == unicodedata.normalize("NFC", "Bật hòa")


def test_settings_validation(client):
    s = client.get("/api/settings").json()
    assert client.put("/api/settings", json={**s, "max_regen": "abc"}).status_code == 422
    assert client.put("/api/settings", json={**s, "max_regen": -1}).status_code == 422
    assert client.put("/api/settings", json={**s, "wer_threshold": 2}).status_code == 422
    assert client.put("/api/settings", json={**s, "stt_timeout_s": 0}).status_code == 422


def test_stt_timeout_applies_without_restart(tmp_path):
    """Review #7: saved stt_timeout_s must reach the WyomingStt in use."""
    app = create_app(Settings(data_dir=tmp_path), tts=FakeTts(), manage_wyoming=False)
    with TestClient(app) as c:
        s = c.get("/api/settings").json()
        assert c.put("/api/settings", json={**s, "stt_timeout_s": 7}).status_code == 200
        assert app.state.ctx.stt.timeout_s == 7


def test_audio_not_cached_by_browser(client, tmp_path):
    """Review #8."""
    set_id = create_set(client, tmp_path)
    client.post(f"/api/audio-sets/{set_id}/generate")
    wait_job_end(client)
    item = client.get(f"/api/audio-sets/{set_id}/items").json()[0]
    r = client.get(f"/api/items/{item['id']}/audio")
    assert r.headers["cache-control"] == "no-store"


# --- plan 3: separate jobs on selected rows ------------------------------------
def test_generate_verify_regenerate_flow(client, tmp_path):
    set_id = create_set(client, tmp_path)
    r = client.post(f"/api/audio-sets/{set_id}/verify")
    assert r.status_code == 422 and r.json()["detail"] == "Không có câu nào có audio để verify"
    assert client.post(f"/api/audio-sets/{set_id}/regenerate").json()["detail"] == "Không có câu nào để sinh lại"
    ids = [i["id"] for i in client.get(f"/api/audio-sets/{set_id}/items").json() if i["enabled"]]
    assert client.post(f"/api/audio-sets/{set_id}/generate", json={"item_ids": ids[:1]}).status_code == 200
    wait_job_end(client)
    st = statuses(client, set_id)
    assert st[ids[0]] == "Đã sinh audio" and st[ids[1]] == "Chờ"
    assert client.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
    wait_job_end(client)
    assert statuses(client, set_id)[ids[0]] == "Đạt"
    assert client.post(f"/api/audio-sets/{set_id}/regenerate", json={"item_ids": [ids[0]]}).status_code == 200
    wait_job_end(client)
    item = next(i for i in client.get(f"/api/audio-sets/{set_id}/items").json() if i["id"] == ids[0])
    assert item["status"] == "Đã sinh audio" and item["attempts"] == 2
    assert client.post(f"/api/audio-sets/{set_id}/generate", json={"item_ids": [ids[0]]}).json()["detail"] \
        == "Không có câu nào cần sinh audio"


def test_block1_endpoint_removed(client, tmp_path):
    set_id = create_set(client, tmp_path)
    assert client.post(f"/api/audio-sets/{set_id}/block1").status_code in (404, 405)


def test_verify_does_not_regenerate(tmp_path):
    tts = FakeTts()

    class WrongStt:
        async def transcribe(self, audio, sr):
            return "hoàn toàn khác"

    app = create_app(Settings(data_dir=tmp_path), tts=tts, stt=WrongStt(), manage_wyoming=False)
    with TestClient(app) as c:
        set_id = create_set(c, tmp_path)
        verify_all(c, set_id)
        assert len(tts.calls) == 2
        assert set(statuses(c, set_id).values()) >= {"Audio không đạt"}


def test_delete_audio_set_removes_rows_and_unshared_wavs(client, tmp_path):
    first = create_set(client, tmp_path)
    second = create_set(client, tmp_path)  # same sentences + voice -> same cached WAVs
    for sid in (first, second):
        assert client.post(f"/api/audio-sets/{sid}/generate").status_code == 200
        wait_job_end(client)
    wavs = {i["audio_path"] for i in client.get(f"/api/audio-sets/{first}/items").json() if i["audio_path"]}
    assert wavs

    assert client.delete(f"/api/audio-sets/{first}").status_code == 200
    assert client.get(f"/api/audio-sets/{first}/items").status_code == 404
    assert [s["id"] for s in client.get("/api/audio-sets").json()] == [second]
    assert all(Path(p).is_file() for p in wavs)  # still used by the second set

    assert client.delete(f"/api/audio-sets/{second}").status_code == 200
    assert not any(Path(p).exists() for p in wavs)
    assert client.get("/api/audio-sets").json() == []


def test_delete_audio_set_unknown_is_404(client):
    assert client.delete("/api/audio-sets/999").status_code == 404


def test_delete_audio_set_while_job_runs_is_409(tmp_path):
    class SlowStt:
        async def transcribe(self, audio, sr):
            import asyncio
            await asyncio.sleep(0.5)
            return "x"

    app = create_app(Settings(data_dir=tmp_path), tts=FakeTts(), stt=SlowStt(), manage_wyoming=False)
    with TestClient(app) as c:
        set_id = create_set(c, tmp_path)
        assert c.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
        wait_job_end(c)
        assert c.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
        assert c.delete(f"/api/audio-sets/{set_id}").status_code == 409
        assert c.get(f"/api/audio-sets/{set_id}/items").status_code == 200
        job = c.get("/api/jobs/current").json()
        c.post(f"/api/jobs/{job['id']}/cancel")
        wait_job_end(c)


def test_clear_all_data_while_job_runs_is_409(tmp_path):
    class SlowStt:
        async def transcribe(self, audio, sr):
            import asyncio
            await asyncio.sleep(0.5)
            return "x"

    app = create_app(Settings(data_dir=tmp_path), tts=FakeTts(), stt=SlowStt(), manage_wyoming=False)
    with TestClient(app) as c:
        set_id = create_set(c, tmp_path)
        assert c.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
        wait_job_end(c)
        assert c.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
        assert c.delete("/api/data").status_code == 409
        assert c.get(f"/api/audio-sets/{set_id}/items").status_code == 200
        job = c.get("/api/jobs/current").json()
        c.post(f"/api/jobs/{job['id']}/cancel")
        wait_job_end(c)


def export_set_zip(client, set_id):
    r = client.post(f"/api/audio-sets/{set_id}/export")
    assert r.status_code == 200, r.text
    dl = client.get(r.json()["download_url"])
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    return dl.content


def import_set_zip(client, data, name="x.zip"):
    return client.post("/api/audio-sets/import", files={"file": (name, data)})


def test_export_then_import_restores_a_verified_set(client, tmp_path):
    set_id = create_set(client, tmp_path)
    verify_all(client, set_id)
    before = statuses(client, set_id)
    assert "Đạt" in before.values()
    data = export_set_zip(client, set_id)
    assert client.delete(f"/api/audio-sets/{set_id}").status_code == 200

    r = import_set_zip(client, data)

    assert r.status_code == 200, r.text
    assert r.json()["missing_audio"] == 0
    new_id = r.json()["id"]
    assert sorted(statuses(client, new_id).values()) == sorted(before.values())
    passed = next(i for i in client.get(f"/api/audio-sets/{new_id}/items").json() if i["status"] == "Đạt")
    audio = client.get(f"/api/items/{passed['id']}/audio")
    assert audio.status_code == 200 and audio.content


def test_import_keeps_form_cells(client, tmp_path):
    set_id = create_set(client, tmp_path)
    data = export_set_zip(client, set_id)
    new_id = import_set_zip(client, data).json()["id"]
    cells = client.app.state.ctx.store.form_cells(new_id)
    assert len(cells) == 3 and all(len(v) == 36 for v in cells.values())


def test_import_rejects_non_zip_with_422(client):
    r = import_set_zip(client, b"not a zip")
    assert r.status_code == 422 and r.json()["detail"]
    assert client.get("/api/audio-sets").json() == []


def test_export_unknown_set_is_404(client):
    r = client.post("/api/audio-sets/999/export")
    assert r.status_code == 404 and r.json()["detail"] == "Không tìm thấy bộ audio"


def test_import_twice_names_second_set_with_suffix(client, tmp_path):
    set_id = create_set(client, tmp_path)
    data = export_set_zip(client, set_id)
    import_set_zip(client, data)
    import_set_zip(client, data)
    names = sorted(s["name"] for s in client.get("/api/audio-sets").json())
    assert names == ["bộ 1", "bộ 1 (2)", "bộ 1 (3)"]


def test_export_and_import_while_job_runs_are_409(tmp_path):
    class SlowStt:
        async def transcribe(self, audio, sr):
            import asyncio
            await asyncio.sleep(0.5)
            return "x"

    app = create_app(Settings(data_dir=tmp_path), tts=FakeTts(), stt=SlowStt(), manage_wyoming=False)
    with TestClient(app) as c:
        set_id = create_set(c, tmp_path)
        assert c.post(f"/api/audio-sets/{set_id}/generate").status_code == 200
        wait_job_end(c)
        data = export_set_zip(c, set_id)
        assert c.post(f"/api/audio-sets/{set_id}/verify").status_code == 200
        assert c.post(f"/api/audio-sets/{set_id}/export").status_code == 409
        assert import_set_zip(c, data).status_code == 409
        assert len(c.get("/api/audio-sets").json()) == 1
        job = c.get("/api/jobs/current").json()
        c.post(f"/api/jobs/{job['id']}/cancel")
        wait_job_end(c)
