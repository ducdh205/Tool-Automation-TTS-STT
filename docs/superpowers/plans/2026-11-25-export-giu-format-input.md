# Export giữ nguyên format file input — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** File Excel kết quả của một phiên test là bản sao file input (chỉ các sheet đã chọn) + sheet "Tổng hợp phiên" ở đầu + 3 cột kết quả ở cuối mỗi sheet; bỏ hẳn mẫu 36 cột.

**Architecture:** Khi tạo bộ audio, chép file input vào `data/sources/<set_id>/` và lưu `source_path`, `header_row` vào `audio_sets`. Module mới `report/result_export.py` mở bản chép bằng openpyxl, cắt sheet, chèn tổng hợp, ghi 3 cột theo `source_row`; không có file gốc thì dựng bảng đơn giản. Route `form-report` và zip phiên gọi module mới; `form_export.py` bị xóa.

**Tech Stack:** Python 3, FastAPI, openpyxl, SQLite, pytest; frontend React/TS (chỉ đổi tên file dự phòng).

**Spec:** `docs/superpowers/specs/2026-11-25-export-giu-format-input-design.md`

## Global Constraints

- Không sửa giá trị/định dạng bất kỳ ô nào có sẵn của file gốc; chỉ xóa sheet không chọn và thêm sheet/cột.
- Tên 3 cột: `Text app nghe được`, `Kết quả`, `Ghi chú`. Độ rộng 40 / 14 / 50; wrap text ở cột 1 và 3.
- Kết quả: `Pass` / `Fail` / `Lỗi thao tác: <lỗi>`; chưa test → trống (cả 3 cột).
- Ghi chú: `WER x% · CER y%` (+ ` · sai: <format_ops>` nếu có op khác equal, + ` · câu đã đọc: <text_tts>` nếu khác `text_raw`). Chỉ có với Pass/Fail.
- Sheet tổng hợp tên `Tổng hợp phiên`, vị trí 0; trùng tên sheet gốc → ` (2)`, ` (3)`….
- File .xlsm mở với `keep_vba=True`, giữ đuôi. Tên file `KetQua_<bộ>_Phien<id><đuôi>`.
- Cột DB `items.form_json` giữ nguyên, không ghi/đọc nữa.
- Mọi chuỗi hiển thị cho người dùng bằng tiếng Việt.

## Review Focus

- Sheet gốc có auto-filter / ô gộp ở header → cột mới vẫn đặt sau cột cuối thật, auto-filter nới ra bao 3 cột (test ở Task 3).
- Tên sheet gốc trùng "Tổng hợp phiên" → không ghi đè sheet gốc (test ở Task 3).
- Bộ audio cũ (`source_path` NULL) hoặc file gốc đã bị xóa khỏi đĩa → vẫn export được bằng bảng đơn giản, không 500 (test ở Task 3).
- Input CSV → không chép file, export bảng đơn giản (test ở Task 2 + Task 3).
- Câu có nhiều lượt / câu "Không áp dụng" không có kết quả → dòng gốc giữ nguyên, 3 cột trống (test ở Task 3).

---

### Task 1: Bỏ mẫu 36 cột khỏi đọc input và Store

**Files:**
- Modify: `backend/tts_stt_tool/input/generic.py` (bỏ `is_form`, `FORM_COLS`, `ID_HEADER`, `TEXT_HEADER` imports; `speaker=DEFAULT_SPEAKER`, `feature=""`, `priority=""`)
- Modify: `backend/tts_stt_tool/input/testcase_form.py` (xóa `ID_HEADER`, `TEXT_HEADER`, `FORM_COLS` nếu không còn ai dùng; sửa docstring)
- Modify: `backend/tts_stt_tool/models.py` (xóa field `form`)
- Modify: `backend/tts_stt_tool/store/db.py` (insert items không còn cột `form_json`; xóa `form_cells`; giữ migration thêm cột `form_json` để DB cũ/mới cùng schema)
- Test: `backend/tests/input/test_generic.py`, `backend/tests/store/test_db.py`, `backend/tests/api/test_routes.py`, `backend/tests/report/conftest.py`

**Interfaces:**
- Produces: `InputItem` không còn `form`; `Store.form_cells` không còn.

- [ ] **Step 1: Sửa test**
  - `test_generic.py::test_form_header_keeps_form_cells` → đổi thành `test_form_header_read_like_any_sheet`: đọc mini form, assert `first.speaker == DEFAULT_SPEAKER`, `first.feature == ""`, `not hasattr(first, "form")`.
  - Dòng 122: bỏ `i.form` khỏi tuple.
  - `test_db.py::test_form_cells_kept_but_not_in_payload` → xóa; giữ test migration `form_json` (dòng 185).
  - `test_routes.py::test_create_set_keeps_form_cells` → xóa.
  - `tests/report/conftest.py`: bỏ `form_row`, tham số `form`, `form=` trong `InputItem`.
- [ ] **Step 2: Chạy** `cd backend && uv run pytest tests/input tests/store -q` → FAIL (`form` vẫn tồn tại).
- [ ] **Step 3: Sửa code** theo danh sách Files.
- [ ] **Step 4: Chạy** `uv run pytest tests/input tests/store tests/api/test_routes.py -q` → PASS (test `form_export` sẽ hỏng — bỏ qua, xóa ở Task 4; chạy với `--ignore=tests/report/test_form_export.py`).
- [ ] **Step 5: Commit** `refactor: drop the 36-column form from input reading`

### Task 2: Lưu bản file gốc kèm bộ audio

**Files:**
- Modify: `backend/tts_stt_tool/store/db.py` (SCHEMA `audio_sets` thêm `source_path TEXT, header_row INTEGER`; migration riêng cho 2 cột này với đúng kiểu; method mới)
- Modify: `backend/tts_stt_tool/api/app.py` (property `sources -> data_dir / "sources"`)
- Modify: `backend/tts_stt_tool/api/routes.py` (`create_audio_set`, `delete_audio_set`, `clear_all_data`)
- Test: `backend/tests/store/test_db.py`, `backend/tests/api/test_routes.py`

**Interfaces:**
- Produces: `Store.set_source(audio_set_id: int, source_path: str | None, header_row: int) -> None`; `get_audio_set(...)` trả thêm `source_path`, `header_row` (int hoặc None); `AppContext.sources: Path`.

- [ ] **Step 1: Test**
  - `test_db.py::test_set_source_roundtrip`: `set_source(id, "x/a.xlsx", 3)` → `get_audio_set(id)` có `source_path == "x/a.xlsx"`, `header_row == 3`; bộ mới chưa set → cả hai `None`.
  - `test_db.py::test_old_db_gets_source_columns`: DB tạo bằng SCHEMA cũ (không có 2 cột) → mở `Store` → `PRAGMA table_info(audio_sets)` có `source_path`, `header_row`.
  - `test_routes.py::test_create_set_copies_source`: upload xlsx, tạo bộ với `header_row=1` → file `ctx.sources / str(set_id) / <tên gốc>` tồn tại, bytes bằng file upload; `get_audio_set` có `source_path` trỏ tới nó, `header_row == 1`.
  - `test_routes.py::test_create_set_csv_no_source`: input CSV → `source_path is None`, thư mục `sources/<id>` không tồn tại.
  - `test_routes.py::test_delete_set_removes_source` và mở rộng test `DELETE /data` có sẵn: thư mục `sources/<id>` / `sources` bị dọn.
- [ ] **Step 2: Chạy** các test trên → FAIL.
- [ ] **Step 3: Code.** Route tạo bộ: sau `create_audio_set`, nếu không phải `.csv` thì `shutil.copyfile(path, ctx.sources / str(set_id) / source)` (trong `asyncio.to_thread`), rồi `set_source(set_id, str(dest), m.header_row)`; CSV → `set_source(set_id, None, m.header_row)`. Xóa bộ: `shutil.rmtree(ctx.sources / str(set_id), ignore_errors=True)` trong `cleanup`. `clear_all_data`: thêm `ctx.sources` vào danh sách `_empty_dir`. `reset_progress` không đụng `sources`.
- [ ] **Step 4: Chạy** `uv run pytest tests/store tests/api -q --ignore=tests/report/test_form_export.py` → PASS.
- [ ] **Step 5: Commit** `feat: keep a copy of the input file with each audio set`

### Task 3: `report/result_export.py`

**Files:**
- Create: `backend/tts_stt_tool/report/result_export.py`
- Test: `backend/tests/report/test_result_export.py`, `backend/tests/report/conftest.py`

**Interfaces:**
- Consumes: `Store.get_audio_set` (`source_path`, `header_row`, `sheets`, `name`, `source_file`), `Store.app_results`, `Store.get_app_run`; `report.excel._app_overview`, `format_ops`, `BOLD`; `layout.DEFAULT_SHEET`.
- Produces:
  - `OVERVIEW_SHEET = "Tổng hợp phiên"`, `RESULT_HEADERS = ["Text app nghe được", "Kết quả", "Ghi chú"]`
  - `result_values(result: dict) -> tuple[str, str, str]` — 3 giá trị theo Global Constraints.
  - `result_suffix(audio_set: dict) -> str` — `".xlsm"` nếu `source_path` tồn tại và đuôi `.xlsm`, còn lại `".xlsx"`.
  - `build_result_report(store: Store, run_id: int, out_path: Path) -> Path`.

- [ ] **Step 1: Fixture.** Trong `conftest.py`, `make_session(tmp_path, *, source=True)`: khi `source=True` tạo file `src.xlsx` với 2 sheet: `SHEET` (header ở dòng 4: `A=TC_ID, B=Lượt, C=Câu nói`, ô `A4:C4` fill vàng `FFFFF2CC` + bold, `A1:C1` gộp tiêu đề, auto-filter `A4:C7`, dữ liệu dòng 5–7, độ rộng cột C = 33) và `"Sheet bỏ"`; gọi `store.set_source(set_id, str(src), 4)`.
- [ ] **Step 2: Test** trong `test_result_export.py`:
  - `test_result_values`: Pass → `("bật ionizer", "Pass", "WER 0% · CER 0%")`; Fail TC2 → `("mở cửa số", "Fail", ...)` với ghi chú chứa `"WER "`, `"CER "`, `"sai: sổ→số"`; OP_ERROR → `("", "Lỗi thao tác: Mic không bật", "")`; PENDING → `("", "", "")`; Pass với `app_text=None` → text `"(app không trả câu)"`.
  - `test_keeps_source_format`: `wb.sheetnames == ["Tổng hợp phiên", SHEET]`; `ws["A1"]` gộp `A1:C1` còn nguyên; `column_dimensions["C"].width == 33`; `D4/E4/F4 == RESULT_HEADERS`, `D4.font.bold` và `D4.fill.fgColor.rgb == "FFFFF2CC"` (chép kiểu ô `C4`); `D5 == "bật ionizer"`, `E6 == "Fail"`, `E7.startswith("Lỗi thao tác")`; `A5..C7` giữ giá trị gốc; `ws.auto_filter.ref == "A4:F7"`.
  - `test_overview_first`: sheet 0 có dòng `"Bộ audio"` và `"Tỉ lệ đúng của app"`.
  - `test_overview_name_clash`: file gốc có sheet tên `Tổng hợp phiên` (được chọn) → sheetnames `["Tổng hợp phiên (2)", "Tổng hợp phiên", ...]`, sheet gốc giữ dữ liệu.
  - `test_untested_rows_blank`: thêm một item thứ 4 ở dòng 8 không có kết quả (status PENDING) → `D8, E8, F8` là `None`.
  - `test_fallback_without_source` (`source=False`) và `test_fallback_when_file_missing` (xóa `src.xlsx` trước khi export): sheetnames `["Tổng hợp phiên", SHEET]`; dòng 1 header `["TC_ID", "Lượt", "Vùng miền", "Câu gốc", "Kết quả mong đợi", *RESULT_HEADERS]`; 3 dòng dữ liệu đúng thứ tự `source_row`.
  - `test_xlsm_suffix`: `result_suffix({"source_path": "a.xlsm"})` với file tồn tại → `".xlsm"`; không tồn tại → `".xlsx"`.
- [ ] **Step 3: Chạy** `uv run pytest tests/report/test_result_export.py -q` → FAIL (module chưa có).
- [ ] **Step 4: Code.** Cột cuối = `max(c.column for c in ws[header_row] if c.value is not None)`, xét cả ô gộp chạm dòng header (`ws.merged_cells.ranges` có `min_row <= header_row <= max_row` → lấy `max_col`); nếu dòng header trống thì `ws.max_column`. Ghi giá trị theo `source_row` của mỗi result trong sheet đó (sheet trong DB là `sheet_name`; result `sheet` khớp tên sheet trong workbook). Chép kiểu bằng `copy()` của `font/fill/border/alignment` từ ô header cuối. Auto-filter: nếu `ws.auto_filter.ref` có, đổi cột cuối của ref sang cột mới cuối cùng. Sheet tổng hợp: `wb.create_sheet(name, 0)` rồi ghi như `build_form_report` cũ (Bộ audio, File nguồn, `_app_overview`). Fallback: `Workbook()` mới; header ở dòng 1, bold, freeze `A2`.
- [ ] **Step 5: Chạy** lại → PASS.
- [ ] **Step 6: Commit** `feat: result workbook built on the original input file`

### Task 4: Nối route + zip phiên, xóa `form_export.py`

**Files:**
- Modify: `backend/tts_stt_tool/api/routes.py:612-618` (dùng `build_result_report`, đuôi `result_suffix(audio_set)`; `media_type` `application/vnd.ms-excel.sheet.macroEnabled.12` cho .xlsm)
- Modify: `backend/tts_stt_tool/report/session_zip.py:114-115` (cùng hàm, tên `KetQua_<bộ>_Phien<id><đuôi>`)
- Delete: `backend/tts_stt_tool/report/form_export.py`, `backend/tests/report/test_form_export.py`
- Modify: `backend/tests/report/test_session_zip.py` (xóa `test_zip_paths_match_form_evidence`; thêm test mới), `backend/tests/api/test_block2_routes.py::test_form_report_endpoint`
- Modify: `frontend/src/api.ts:143` (fallback name giữ `KetQua_Phien${runId}.xlsx` — tên thật lấy từ Content-Disposition, không đổi logic)

**Interfaces:**
- Consumes: `build_result_report`, `result_suffix`, `RESULT_HEADERS` từ Task 3.

- [ ] **Step 1: Test**
  - `test_session_zip.py::test_zip_result_workbook`: workbook `KetQua_...xlsx` trong zip có sheetnames `["Tổng hợp phiên", SHEET]` và `E6 == "Fail"` (fixture có file gốc).
  - `test_form_report_endpoint`: response 200, `content-disposition` chứa `KetQua_`, mở được bằng openpyxl, sheet đầu `Tổng hợp phiên`; run 999 → 404.
- [ ] **Step 2: Chạy** → FAIL.
- [ ] **Step 3: Code** theo Files; `grep -rn form_export backend` phải rỗng.
- [ ] **Step 4: Chạy toàn bộ** `cd backend && uv run pytest -q` → PASS; `cd frontend && npm test -- --run` → PASS.
- [ ] **Step 5: Commit** `feat: export results into the original input file; remove the form export`
