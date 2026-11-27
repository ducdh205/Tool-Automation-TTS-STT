import io
import zipfile

import openpyxl

from backend.tests.report.conftest import SHEET
from tts_stt_tool.report.session_zip import build_session_zip, session_root_name


def open_zip(session, tmp_path, **kw):
    out = build_session_zip(session.store, session.run_id, session.settings, tmp_path / "s.zip", **kw)
    z = zipfile.ZipFile(out)
    return z, set(z.namelist()), session_root_name(session.store.get_app_run(session.run_id))


def test_root_name():
    run = {"id": 12, "serial": "SER", "device_model": "Pixel 7/Pro", "created_at": "2026-11-20T15:30:12"}
    assert session_root_name(run) == "Phien12_2026-11-20_1530_Android_Pixel 7_Pro"
    assert session_root_name(run | {"device_model": None}) == "Phien12_2026-11-20_1530_Android_SER"


def test_zip_layout_default_audio_failed(tmp_path, session):
    z, names, root = open_zip(session, tmp_path)
    case = f"{root}/{SHEET}"
    assert {f"{root}/thong_tin_phien.txt", f"{root}/TongQuan.xlsx",
            f"{root}/KetQua_Bộ điều khiển_Phien{session.run_id}_Android_Pixel 7.xlsx"} <= names
    assert {f"{case}/PASS_TC1/luot1_ketqua.txt", f"{case}/PASS_TC1/luot1_log.txt"} <= names
    assert f"{case}/PASS_TC1/luot1_audio.wav" not in names and f"{case}/PASS_TC1/luot1_manhinh.png" not in names
    assert z.read(f"{case}/FAIL_TC2/luot1_manhinh.png") == b"\x89PNG-wrong"
    assert z.read(f"{case}/LOI_TC3/luot1_manhinh.png") == b"\x89PNG-op"
    assert z.read(f"{case}/FAIL_TC2/luot1_audio.wav").startswith(b"RIFF-fake")
    assert f"{case}/LOI_TC3/luot1_audio.wav" in names
    assert z.getinfo(f"{case}/FAIL_TC2/luot1_audio.wav").compress_type == zipfile.ZIP_STORED
    assert z.getinfo(f"{case}/FAIL_TC2/luot1_manhinh.png").compress_type == zipfile.ZIP_STORED
    assert z.getinfo(f"{case}/FAIL_TC2/luot1_ketqua.txt").compress_type == zipfile.ZIP_DEFLATED
    raw = z.read(f"{case}/FAIL_TC2/luot1_ketqua.txt")
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "TC_ID: TC2" in text and "Câu app nghe: mở cửa số" in text and "Kết quả: Sai" in text
    assert "Từ sai: sổ→số" in text and "Câu đã đọc: mở cửa sổ" in text and "Câu gốc: Hey Vita, mở cửa sổ" in text
    assert "Lỗi: Mic không bật" in z.read(f"{case}/LOI_TC3/luot1_ketqua.txt").decode("utf-8-sig")
    info = z.read(f"{root}/thong_tin_phien.txt").decode("utf-8-sig")
    assert "Pixel 7 (SER123)" in info and "Chỉ case Sai / Lỗi thao tác" in info and "Sai: 1" in info


def test_zip_audio_all_and_selected(tmp_path, session):
    _, names, _ = open_zip(session, tmp_path, audio="all")
    assert sum(n.endswith("audio.wav") for n in names) == 3
    tc1 = session.by_tc["TC1"]["item_id"]
    z, names, root = open_zip(session, tmp_path, audio="selected", selected_item_ids={tc1})
    assert [n for n in names if n.endswith("audio.wav")] == [f"{root}/{SHEET}/PASS_TC1/luot1_audio.wav"]
    assert "Các case đang chọn (1)" in z.read(f"{root}/thong_tin_phien.txt").decode("utf-8-sig")


def test_missing_audio_is_noted_not_fatal(tmp_path, session):
    from pathlib import Path

    Path(session.by_tc["TC2"]["audio_path"]).unlink()
    z, names, root = open_zip(session, tmp_path)
    assert f"{root}/{SHEET}/FAIL_TC2/luot1_audio.wav" not in names
    assert "Không tìm thấy file audio" in z.read(f"{root}/{SHEET}/FAIL_TC2/luot1_ketqua.txt").decode("utf-8-sig")


def test_zip_result_workbook(tmp_path, session):
    z, names, root = open_zip(session, tmp_path)
    wb = openpyxl.load_workbook(io.BytesIO(z.read(f"{root}/KetQua_Bộ điều khiển_Phien{session.run_id}_Android_Pixel 7.xlsx")))
    assert wb.sheetnames == ["Tổng hợp phiên", SHEET]
    assert wb[SHEET]["E6"].value == "Fail"


def test_profile_written_when_given(tmp_path, session):
    z, _, root = open_zip(session, tmp_path, profile={"name": "Vita Work (dev)", "package": "vn.vita"})
    assert '"package": "vn.vita"' in z.read(f"{root}/thong_tin_phien.txt").decode("utf-8-sig")
