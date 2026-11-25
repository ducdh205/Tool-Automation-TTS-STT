# Nhập testcase bằng mapping cột — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay hộp thoại nạp file bằng luồng chọn sheet + dòng tiêu đề + map cột (có Vùng miền), nhiều sheet chung một mapping → một bộ audio.

**Architecture:** Backend gom việc đọc file về `input/generic.py` (nhãn cột chuẩn hóa, xem trước, gợi ý, đọc theo mapping nhiều sheet); bỏ đường đọc form cố định. API thêm `POST /files/preview`, `POST /audio-sets` bắt buộc `mapping`. Frontend viết lại `ImportDialog.tsx` theo ảnh mẫu.

**Tech Stack:** Python 3 / FastAPI / openpyxl / pytest; React + TypeScript / Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-25-nhap-testcase-mapping-cot-design.md`

## Global Constraints

- Mọi chữ trên UI và thông báo lỗi bằng tiếng Việt.
- Câu lệnh "bắt buộc" duy nhất là **Câu lệnh**; Mã câu / Vùng miền / Kết quả mong đợi là "nên chọn" (cảnh báo, không chặn); Kịch bản hội thoại là tùy chọn.
- Ô → text luôn qua `cell_text` (giữ số 0 đầu, `2.0` → `"2"`).
- Xem trước tối đa **20** dòng dữ liệu.
- Không có Langfuse, không có nút Thay thế / Thêm vào danh sách.
- Màu theo token CSS sẵn có trong `frontend/src/styles.css` (light + dark).

## Review Focus

1. Sheet form thật: 3 dòng tiêu đề nhóm phía trên, tiêu đề ở dòng 4 → map đúng và vẫn lưu `form` 36 ô (Task 1 `test_form_header_keeps_form_cells`).
2. Dòng có Mã câu trống khi đã map cột Mã → bỏ qua (giống hành vi cũ: dòng ghi chú/tiêu đề nhóm không thành testcase) (Task 1 `test_blank_id_rows_skipped_when_id_mapped`).
3. Một sheet trong danh sách thiếu cột đã map → 422 nêu tên sheet, không tạo bộ nửa vời (Task 2 `test_create_set_missing_column_names_sheet`).
4. Tiêu đề trống / trùng / cột trống đuôi → nhãn ổn định `Cột F`, `X (2)`, không sinh hàng chục cột rác (Task 1 `test_header_labels`).
5. Gõ nhanh số dòng tiêu đề → phản hồi preview cũ về sau không ghi đè cái mới (Task 3 `ignores stale preview responses`).

---

### Task 1: Đọc file theo mapping (`input/generic.py`)

**Files:**
- Modify: `backend/tts_stt_tool/input/generic.py` (viết lại)
- Modify: `backend/tts_stt_tool/input/testcase_form.py` — chỉ giữ `InputError`, `cell_text`, `open_workbook`, hằng `ID_HEADER`, `TEXT_HEADER`, `FORM_COLS`; xóa `COLUMNS`, `_IDX`, `_MAX_COL`, `HEADER_ROW`, `FIRST_DATA_ROW`, `_is_form`, `_iter_items`, `is_testcase_form`, `list_sheets`, `read_testcase_items`.
- Modify: `backend/tts_stt_tool/models.py` — xóa `SheetInfo`.
- Test: `backend/tests/input/test_generic.py` (viết lại), `backend/tests/input/test_testcase_form.py` (chỉ giữ test `InputError` với file không tồn tại, đổi sang `sheet_names`; test sample 3986 đổi sang `read_items` với `header_row=4, id_col="TC_ID", text_col="Câu nói (utterance)"` trên các sheet có tiêu đề form).

**Interfaces:**
- Produces (trong `tts_stt_tool.input.generic`):
  - `@dataclass ColumnMapping: text_col: str; header_row: int = 1; id_col: str | None = None; region_col: str | None = None; region_value: str | None = None; expected_col: str | None = None; turn_col: str | None = None`
  - `@dataclass SheetPreview: columns: list[str]; rows: list[list[str]]; row_count: int; suggestions: dict[str, str]`
  - `sheet_names(path: Path) -> list[str]` — CSV → `[]`.
  - `header_labels(cells: list[str]) -> list[str]`
  - `suggest_mapping(columns: list[str]) -> dict[str, str]` — khóa: `text_col`, `id_col`, `region_col`, `expected_col`, `turn_col`.
  - `preview_sheet(path: Path, sheet: str | None, header_row: int, limit: int = 20) -> SheetPreview`
  - `read_items(path: Path, sheets: list[str], mapping: ColumnMapping) -> list[InputItem]` — CSV: `sheets` bỏ qua, tên sheet = `path.stem`.
  - Xóa `preview_columns`, `read_generic`.

**Quy tắc (spec + quyết định của plan):**
- `header_labels`: bỏ các ô trống ở **đuôi**; ô trống ở giữa → `f"Cột {get_column_letter(i)}"`; tên trùng lần thứ k → `f"{name} ({k})"`.
- Dòng dữ liệu = các dòng sau `header_row` có ít nhất một ô khác rỗng; `row_count` đếm các dòng đó.
- `header_row` lớn hơn số dòng sheet (không có dòng tiêu đề) → `InputError(f"Sheet '{name}' không có dòng {header_row}")`; sheet không tồn tại → `InputError(f"Không có sheet '{name}'")`.
- Cột đã map không có trong nhãn của sheet → `InputError(f"Sheet '{name}' không có cột '{col}'")`.
- `id_col` được map mà ô trống → **bỏ qua dòng**; không map → `tc_id = str(số dòng)`.
- `region = cells[region_col]` nếu map, ngược lại `region_value or ""`; `turn` = ô `turn_col` hoặc `"1"` nếu trống/không map; `expected` = ô `expected_col` hoặc `""`.
- Nếu nhãn thứ 0 == `ID_HEADER` và nhãn thứ 12 == `TEXT_HEADER`: `form` = 36 ô đầu (đệm `""`), `feature` = ô B, `priority` = ô E, `speaker` = ô L hoặc `DEFAULT_SPEAKER`. Ngược lại `form = []`, `feature = priority = ""`, `speaker = DEFAULT_SPEAKER`.
- Gợi ý: so khớp `name.strip().lower()` — ưu tiên khớp đúng, sau đó "chứa" — với từ khóa: text `["câu nói (utterance)", "câu nói", "utterance", "câu lệnh", "text"]`; id `["tc_id", "mã câu", "case id", "id"]`; region `["vùng miền", "region"]`; expected `["kết quả mong đợi", "expected"]`; turn `["bước / lượt", "bước", "lượt", "turn"]`. Một cột chỉ gán cho một trường (xét theo thứ tự text, id, region, expected, turn).

- [ ] **Step 1: Viết test thất bại** trong `backend/tests/input/test_generic.py`:

```python
def test_header_labels():
    assert header_labels(["Mã", "", "Câu", "Câu", "", ""]) == ["Mã", "Cột B", "Câu", "Câu (2)"]

def test_suggest_mapping_on_form_headers():
    s = suggest_mapping(HEADER)  # backend.tests.helpers.HEADER
    assert s == {"text_col": "Câu nói (utterance)", "id_col": "TC_ID", "region_col": "Vùng miền",
                 "expected_col": "Kết quả mong đợi", "turn_col": "Bước / Lượt"}

def test_preview_sheet_header_row_4(mini_form):
    p = preview_sheet(mini_form, FORM_SHEET, 4)
    assert p.columns[:2] == ["TC_ID", "Cụm tính năng"]
    assert p.row_count == 4 and len(p.rows) == 4
    assert p.rows[1][8] == "2"
    assert p.suggestions["text_col"] == "Câu nói (utterance)"

def test_preview_limit(tmp_path):  # 25 dòng dữ liệu → rows 20, row_count 25

def test_preview_header_row_out_of_range(mini_form):
    with pytest.raises(InputError, match="không có dòng 99"):
        preview_sheet(mini_form, FORM_SHEET, 99)

def test_form_header_keeps_form_cells(mini_form):
    m = ColumnMapping(text_col="Câu nói (utterance)", header_row=4, id_col="TC_ID",
                      region_col="Vùng miền", expected_col="Kết quả mong đợi", turn_col="Bước / Lượt")
    items = read_items(mini_form, [FORM_SHEET], m)
    assert [(i.tc_id, i.turn, i.text_raw) for i in items] == [
        ("TC-SYN-001", "1", "Đồng bộ nhiệt độ tất cả các vùng"), ("TC-DLG-001", "2", "Bật"), ("TC-SYN-002", "1", "")]
    first = items[0]
    assert (first.source_row, first.region, first.expected, first.feature, first.priority) == \
           (5, "BAC-HN", "expected", "Climate Sync", "P0 - Smoke")
    assert len(first.form) == 36 and first.form[2] == "UC" and first.form[35] == ""

def test_blank_id_rows_skipped_when_id_mapped(mini_form):  # row 8 has no TC_ID → 3 items, not 4

def test_region_value_and_defaults(tmp_path):
    # csv "cau\nBật đèn\n", ColumnMapping(text_col="cau", region_value="NAM-HCM")
    # → region "NAM-HCM", turn "1", tc_id "2", expected "", form [], speaker DEFAULT_SPEAKER

def test_multiple_sheets_and_missing_column(tmp_path):
    # wb: sheet "A" [Mã, Câu] + 1 row, sheet "B" [Mã, Câu] + 1 row, sheet "C" [Mã, Lệnh]
    # read_items(p, ["A", "B"], ...) → 2 items, sheets ["A", "B"]
    # read_items(p, ["A", "C"], ...) raises InputError match "Sheet 'C' không có cột 'Câu'"

def test_csv_header_row_2(tmp_path):  # "ghi chú\nid,cau\n1,Mở cốp\n" header_row=2 → 1 item, source_row 3
```

Giữ lại 4 test cũ, đổi `read_generic(p, s, m)` → `read_items(p, [s] if s else [], m)` và `preview_columns` → `preview_sheet(...).columns`. Thêm `test_sheet_names(mini_form) == ["Tổng hợp", "Hướng dẫn", FORM_SHEET]`.

- [ ] **Step 2:** `pytest backend/tests/input -q` → FAIL (ImportError `read_items`).
- [ ] **Step 3:** Cài đặt theo Interfaces + Quy tắc. Đọc xlsx bằng `open_workbook` + `ws.iter_rows(min_row=header_row, values_only=True)`; một hàm sinh `(row_number, cells)` dùng chung cho CSV/xlsx như `_rows` hiện tại.
- [ ] **Step 4:** `pytest backend/tests/input -q` → PASS.
- [ ] **Step 5:** Commit `feat(input): read any sheet through a user column mapping`.

---

### Task 2: API inspect / preview / audio-sets

**Files:**
- Modify: `backend/tts_stt_tool/api/routes.py:25-26, 70-123`
- Test: `backend/tests/api/test_routes.py`

**Interfaces:**
- Consumes: Task 1 `sheet_names`, `preview_sheet`, `read_items`, `ColumnMapping`, `InputError`.
- Produces (HTTP):
  - `POST /api/files/inspect` (multipart) → `{file_id: str, sheets: string[]}`
  - `POST /api/files/preview` `{file_id, sheet: str|null, header_row: int (≥1)}` → `{columns, rows, row_count, suggestions}`
  - `POST /api/audio-sets` `{file_id, sheets: string[], name, mapping: {text_col, header_row=1, id_col?, region_col?, region_value?, expected_col?, turn_col?}}` → `{id}`. `mapping` bắt buộc. `region_col` và `region_value` cùng có → 422 `"Chọn cột vùng miền hoặc giá trị cố định, không chọn cả hai"`. File xlsx với `sheets` rỗng → 422 `"Chọn ít nhất một sheet"`. `InputError` → 422 với thông điệp của nó. Không có dòng nào → 422 `"Không có dòng dữ liệu nào"`.

- [ ] **Step 1: Sửa/viết test** trong `test_routes.py`:
  - Helper `create_set` gửi `mapping={"header_row": 4, "id_col": "TC_ID", "text_col": "Câu nói (utterance)", "region_col": "Vùng miền", "expected_col": "Kết quả mong đợi", "turn_col": "Bước / Lượt"}` → các test dùng nó (kể cả `test_block2_routes.py`) giữ nguyên kỳ vọng (3 item: `Chờ, Chờ, Không áp dụng`).
  - `test_inspect_detects_form` → `test_inspect_lists_sheets`: `info["sheets"] == ["Tổng hợp", "Hướng dẫn", FORM_SHEET]`, không có khóa `is_form`.
  - `test_preview_route`: header_row 4 → `row_count == 4`, `suggestions["id_col"] == "TC_ID"`; header_row 99 → 422; header_row 0 → 422.
  - `test_inspect_csv_returns_columns` → inspect trả `sheets == []`, preview `sheet=None` trả `columns == ["id", "cau"]`, tạo set như cũ (thêm `header_row` mặc định).
  - `test_create_set_missing_column_names_sheet`: `sheets=[FORM_SHEET, "Tổng hợp"]` → 422, `"Tổng hợp"` trong `detail`, `GET /api/audio-sets` vẫn rỗng.
  - `test_create_set_region_value_and_col_conflict` → 422; `test_create_set_xlsx_without_sheets` → 422.
  - `test_create_set_keeps_form_cells`: sau `create_set`, `ctx.store.form_cells(set_id)` có 3 entry dài 36.
- [ ] **Step 2:** `pytest backend/tests/api -q` → FAIL.
- [ ] **Step 3:** Cài đặt: `MappingIn` thêm field + `header_row: int = Field(1, ge=1)`; `PreviewIn` mới; `AudioSetIn.mapping: MappingIn`; chạy đọc file trong `asyncio.to_thread`. Xóa import `list_sheets`, `read_testcase_items`, `preview_columns`, `read_generic`.
- [ ] **Step 4:** `pytest backend -q` → PASS toàn bộ (kể cả report/store/cli).
- [ ] **Step 5:** Commit `feat(api): sheet preview and column-mapped audio set import`.

---

### Task 3: Hộp thoại nhập testcase (frontend)

**Files:**
- Modify: `frontend/src/api.ts:20-22, 88-94`
- Modify: `frontend/src/components/ImportDialog.tsx` (viết lại)
- Modify: `frontend/src/App.tsx:440-450` — `onCreated` không gọi `setDialog(null)` nữa.
- Modify: `frontend/src/styles.css` — class mới `import-*`, dùng token màu sẵn có.
- Test: `frontend/src/components/ImportDialog.test.tsx` (mới), `frontend/src/api.test.ts` nếu có assert về inspect.

**Interfaces:**
- Consumes: HTTP của Task 2.
- Produces (`api.ts`):
  - `interface InspectResult { file_id: string; sheets: string[] }`
  - `interface SheetPreview { columns: string[]; rows: string[][]; row_count: number; suggestions: Partial<Record<MappingField, string>> }`
  - `type MappingField = "text_col" | "id_col" | "region_col" | "expected_col" | "turn_col"`
  - `interface ColumnMapping { text_col: string; header_row: number; id_col?: string | null; region_col?: string | null; region_value?: string | null; expected_col?: string | null; turn_col?: string | null }`
  - `api.preview(b: { file_id: string; sheet: string | null; header_row: number }) => Promise<SheetPreview>`
  - `api.createSet(b: { file_id: string; sheets: string[]; name: string; mapping: ColumnMapping })`
  - Xóa `SheetInfo`.
- `ImportDialog` props không đổi: `{ onClose(): void; onCreated(setId: number): void }`; dialog tự gọi `onClose()` sau khi tạo nếu không tick "Giữ cửa sổ".

**Giao diện (copy cố định):** tiêu đề nhỏ `NHẬP DỮ LIỆU TESTCASE` + tên file; khung: `Sheet` · `Dòng tiêu đề` · `Tổng số dòng`; chú thích `Chọn sheet để xem trước. Các sheet được tick dùng chung mapping và gộp thành một bộ audio.`; nhóm tick `Nạp các sheet` + nút `Chọn tất cả`/`Bỏ chọn`; checkbox `Giữ cửa sổ này để nạp tiếp sheet khác`; các trường và chú thích:

| Nhãn | Chú thích |
|---|---|
| `Mã câu (Case ID)` | `Tự sinh theo số dòng nếu để trống.` |
| `Câu lệnh *` | `Cột dùng để đọc thành audio.` |
| `Kịch bản hội thoại` | `Bước / lượt — gom các câu cùng hội thoại.` |
| `Kết quả mong đợi` | `Dùng để AI đối chiếu chấm điểm.` |
| `Vùng miền` | `Giọng vùng miền của câu (vd BAC-HN).` |

Mỗi select có `— Không map —` + các cột; Vùng miền thêm option `Giá trị cố định…` → hiện ô nhập. Trường "nên chọn" chưa map: chú thích đổi màu `--warn`. Bảng `Xem trước dữ liệu` + `{row_count} dòng dữ liệu · hiển thị tối đa 20 dòng`, cuộn ngang, header dính, cột đang được map có nền `--accent-soft`. Ô `Tên bộ audio`. Footer `Huỷ` · `Tạo bộ audio`. CSV: ẩn ô Sheet và nhóm tick.

**Hành vi:** sau inspect, sheet xem trước = sheet đầu, tick sẵn nó; đổi sheet / dòng tiêu đề (debounce 300 ms) → `api.preview`; chỉ áp phản hồi của yêu cầu mới nhất (bộ đếm tăng dần); gợi ý chỉ điền vào trường người dùng chưa tự đổi; nếu cột đã map không còn trong `columns` mới → đặt về rỗng. Nút tạo disabled khi: chưa map Câu lệnh, xlsx chưa tick sheet, tên rỗng, đang xử lý, hoặc chọn `Giá trị cố định…` mà ô trống.

- [ ] **Step 1: Viết test thất bại** `ImportDialog.test.tsx` (`vi.mock("../api")`):
  - `prefills mapping from suggestions and creates with the mapping`: inspect → `{file_id:"f", sheets:["S1","S2"]}`, preview → columns `["TC_ID","Câu nói (utterance)","Vùng miền"]`, suggestions tương ứng; upload file; bấm `Tạo bộ audio` → `createSet` nhận `{file_id:"f", sheets:["S1"], name:"mini", mapping:{header_row:1, text_col:"Câu nói (utterance)", id_col:"TC_ID", region_col:"Vùng miền", region_value:null, expected_col:null, turn_col:null}}`; `onCreated(7)` và `onClose` được gọi.
  - `create is disabled until a text column is mapped`: suggestions rỗng → nút disabled; chọn cột ở `Câu lệnh *` → enabled.
  - `changing header row re-fetches preview`: đổi `Dòng tiêu đề` thành 4 → `preview` gọi với `header_row: 4` (dùng fake timers cho debounce).
  - `fixed region value is sent`: chọn `Giá trị cố định…`, gõ `BAC-HN` → mapping có `region_col:null, region_value:"BAC-HN"`.
  - `keep open unticks imported sheets`: tick "Giữ cửa sổ…" → sau tạo, `onClose` không gọi, checkbox `S1` bỏ tick, nút tạo disabled.
  - `ignores stale preview responses`: preview thứ nhất resolve sau thứ hai → `Tổng số dòng` hiển thị giá trị của lần thứ hai.
- [ ] **Step 2:** `cd frontend && npx vitest run src/components/ImportDialog.test.tsx` → FAIL.
- [ ] **Step 3:** Cài đặt `api.ts`, `ImportDialog.tsx`, CSS, `App.tsx`.
- [ ] **Step 4:** `npx vitest run` và `npx tsc --noEmit` → PASS / không lỗi.
- [ ] **Step 5:** Mở app (skill `run`), nạp một file form thật: kiểm tra bố cục giống ảnh ở light và dark, rộng màn hình nhỏ không tràn ngang trang.
- [ ] **Step 6:** Commit `feat(ui): import dialog with sheet, header row and column mapping`.
