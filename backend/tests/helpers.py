from pathlib import Path

import openpyxl


REPO = Path(__file__).resolve().parents[2]
SAMPLE_XLSX = REPO / "public" / "DieuKhienXe_Pre.xlsx"

FORM_SHEET = "ONOFFTemperature Synchronizatio"

HEADER = [
    "TC_ID", "Cụm tính năng", "Use case / Req ID", "Mục đích kiểm thử", "Mức ưu tiên",
    "Loại test", "Mã lĩnh vực KT (A–V)", "Vùng miền", "Bước / Lượt",
    "Tiền điều kiện & môi trường", "Các bước thực hiện", "Người nói",
    "Câu nói (utterance)", "Kết quả mong đợi",
]


def _row(tc_id, turn, text, speaker="👤 Người dùng"):
    # Columns A..N (14 columns)
    return [tc_id, "Climate Sync", "UC", "purpose", "P0 - Smoke", "Chức năng", "A",
            "BAC-HN", turn, "pre", "steps", speaker, text, "expected"]


def build_mini_form(path: Path) -> Path:
    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = "Tổng hợp"
    summary["A1"] = "TỔNG HỢP"
    summary["A5"] = "Sheet testcase"
    wb.create_sheet("Hướng dẫn")
    ws = wb.create_sheet(FORM_SHEET)
    ws["A1"] = "ĐIỀU KHIỂN XE"
    ws["A3"] = "THÔNG TIN CHUNG"
    for col, name in enumerate(HEADER, start=1):
        ws.cell(row=4, column=col, value=name)
    rows = [
        _row("TC-SYN-001", "1", "Đồng bộ nhiệt độ tất cả các vùng"),
        _row("TC-DLG-001", 2, "Bật"),
        _row("TC-SYN-002", "1", None),
        _row(None, "1", "dòng không có TC_ID"),
    ]
    for r, values in enumerate(rows, start=5):
        for c, v in enumerate(values, start=1):
            ws.cell(row=r, column=c, value=v)
    wb.save(path)
    return path


