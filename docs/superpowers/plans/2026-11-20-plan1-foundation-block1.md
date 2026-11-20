# Kế hoạch 1 — Nền tảng + Khối 1 (TTS → verify STT → báo cáo) + Giao diện

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool chạy từ mã nguồn, mở `localhost` với giao diện 3 cột; nạp file testcase xlsx/csv, sinh audio bằng VieNeu, verify bằng wyoming-vietnamese, so sánh WER/CER và xuất báo cáo Excel. Cột phải (màn hình điện thoại) là khung giữ chỗ — Kế hoạch 2 lấp đầy.

**Architecture:** Backend Python (FastAPI) giữ toàn bộ logic: đọc input, lọc dòng, chuẩn hóa/so sánh, TTS, client Wyoming, hàng đợi job một-luồng, SQLite, xuất Excel. Frontend React + Vite (TypeScript) build ra tĩnh, FastAPI phục vụ; cập nhật tiến độ qua WebSocket. TTS và STT đứng sau interface để test bằng bản giả.

**Tech Stack:** Python 3.12 (uv), FastAPI, uvicorn, openpyxl, jiwer, `vieneu`, `wyoming` (client), numpy + soundfile + soxr (resample), sqlite3 (stdlib), pytest + pytest-asyncio; React 18 + Vite + TypeScript + @tanstack/react-table + @tanstack/react-virtual, vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-tts-stt-automation-design.md`

## Global Constraints

- Windows 11; máy chưa có Python → mọi lệnh Python chạy qua `uv` (`uv run ...`), Python 3.12.
- Chạy từ mã nguồn: `uv run tts-stt-tool` khởi động server ở `http://127.0.0.1:8765` và mở trình duyệt. Không đóng gói .exe; không dùng gì cản việc đóng gói sau (không phụ thuộc Docker trong code backend).
- wyoming-vietnamese chạy như tiến trình riêng, backend chỉ nói chuyện qua Wyoming TCP `127.0.0.1:10300`.
- VieNeu mode `v3turbo`, **một giọng cố định** chọn trong Cài đặt; GPU nếu có, CPU vẫn phải chạy.
- Verify: **Đạt khi WER = 0** sau chuẩn hóa (ngưỡng chỉnh được, mặc định 0.0). Không đạt → sinh lại tối đa **3** lần (chỉnh được), vẫn lỗi → "Audio không đạt".
- Cảnh báo tỉ lệ audio bị loại > **10%** (chỉnh được).
- Một hàm so sánh duy nhất dùng cho cả Khối 1 và Khối 2.
- Không ghi ngược vào file testcase gốc.
- Giao diện tiếng Việt. Trạng thái câu hiển thị: `Chờ`, `Không áp dụng`, `Đã sinh audio`, `Đạt`, `Audio không đạt`, `Lỗi`.
- Chạy được hàng nghìn câu; dừng/tiếp tục không mất kết quả.

## Review Focus

1. **Tắt tool giữa lúc đang ghi WAV** → lần sau không dùng file hỏng: ghi file tạm rồi đổi tên (Task 6), và resume chỉ coi câu là xong khi DB đã ghi trạng thái (Task 8).
2. **Ô Excel có chữ Việt dạng tổ hợp (NFD), xuống dòng `\r\n`, khoảng trắng thừa** → so sánh vẫn ra WER = 0 với cùng câu (Task 3).
3. **Câu chỉ có "Hey Vita" hoặc chỉ dấu câu** → bị loại "Không áp dụng", không gây lỗi chia cho 0 trong jiwer (Task 2, Task 3).
4. **wyoming chưa chạy / cổng bận / treo** → job dừng câu đó với lỗi rõ ràng trong vòng timeout (mặc định 30s), không treo cả hàng đợi (Task 7, Task 8).
5. **Người dùng sửa text một dòng sau khi đã sinh audio** → khóa cache đổi, trạng thái quay về `Chờ`, audio cũ không bị dùng lại (Task 5, Task 6).

---

## Cấu trúc file

```
pyproject.toml                       # uv project, script tts-stt-tool
backend/tts_stt_tool/
  __main__.py / cli.py               # khởi động uvicorn + mở trình duyệt
  config.py                          # Settings (đọc/ghi data/settings.json)
  models.py                          # dataclass dùng chung
  input/testcase_form.py             # đọc form 36 cột
  input/generic.py                   # csv/xlsx khác form + ánh xạ cột
  input/filters.py                   # bỏ wake word, phân loại dòng
  compare/vi_numbers.py              # số → chữ tiếng Việt
  compare/normalize.py               # chuẩn hóa text
  compare/score.py                   # WER/CER + thao tác từ
  store/db.py                        # schema + repository SQLite
  tts/base.py, tts/vieneu_engine.py  # interface + VieNeu
  tts/cache.py                       # khóa cache + ghi atomic
  stt/wyoming_client.py              # client Wyoming
  stt/server_manager.py              # khởi động/kiểm tra wyoming-vietnamese
  pipeline/block1.py                 # sinh → verify → sinh lại
  jobs/runner.py                     # hàng đợi 1 job, hủy, sự kiện tiến độ
  report/excel.py                    # báo cáo Excel
  api/app.py, api/routes.py, api/ws.py
backend/tests/...                    # pytest, cấu trúc gương
frontend/                            # Vite React TS
docs/spikes/2026-11-20-runtime-spike.md
data/                                # (gitignore) settings.json, tool.db, audio/, reports/
```

---

### Task 0: Repo + spike môi trường (wyoming trên Windows, VieNeu GPU)

Đây là spike: kết quả là một ghi chú, không phải code sản phẩm. Nó quyết định cách khởi động wyoming ở Task 7 và tham số "sinh lại" ở Task 6.

**Files:**
- Create: `.gitignore` (`data/`, `.venv/`, `node_modules/`, `frontend/dist/`, `__pycache__/`), `pyproject.toml`, `docs/spikes/2026-11-20-runtime-spike.md`

- [ ] **Step 1:** `git init`, tạo `.gitignore`, `pyproject.toml` (name `tts-stt-tool`, `requires-python = ">=3.12,<3.13"`, package dir `backend/tts_stt_tool`, script `tts-stt-tool = "tts_stt_tool.cli:main"`, dev deps pytest, pytest-asyncio). Chạy `uv sync`. Expected: tạo `.venv`, không lỗi.
- [ ] **Step 2:** Clone `https://github.com/luuquangvu/wyoming-vietnamese` vào `vendor/wyoming-vietnamese` (thêm vào `.gitignore`), `uv sync` trong đó, chạy theo entrypoint của repo với STT zipformer, cổng 10300. Ghi lại: lệnh chạy chính xác, biến môi trường, thời gian tải model, RAM. Nếu không chạy được trên Windows sau 1 giờ thử → ghi lại lỗi và lệnh Docker dự phòng `docker run -p 10300:10300 ghcr.io/luuquangvu/wyoming-vietnamese:latest`.
- [ ] **Step 3:** Script thử (trong scratchpad, không commit) gửi một WAV 16 kHz mono qua thư viện `wyoming` (`AsyncTcpClient`, sự kiện `Transcribe` → `AudioStart` → `AudioChunk` → `AudioStop`, đọc `Transcript`). Ghi lại: định dạng audio server chấp nhận (rate/width/channels), có cần gửi `Transcribe(language="vi")` không.
- [ ] **Step 4:** Trong `.venv` dự án: cài torch CUDA (cu128) rồi `vieneu`; sinh một câu "Bật đồng bộ nhiệt độ" bằng `Vieneu(mode="v3turbo")`. Ghi lại: chữ ký `infer` thật, danh sách giọng (tên + giới tính + vùng), sample rate đầu ra, tham số nào làm kết quả khác nhau giữa các lần (seed/temperature/speed), thời gian/câu trên GPU và CPU.
- [ ] **Step 5:** Ghi tất cả vào `docs/spikes/2026-11-20-runtime-spike.md`; commit `chore: init repo and runtime spike notes`.

---

### Task 1: Đọc form testcase 36 cột

**Files:**
- Create: `backend/tts_stt_tool/models.py`, `backend/tts_stt_tool/input/testcase_form.py`
- Test: `backend/tests/input/test_testcase_form.py`, fixture `backend/tests/fixtures/mini_form.xlsx` (tạo bằng openpyxl trong `conftest.py`, không commit file nhị phân lớn)

**Interfaces:**
- Produces:
  - `@dataclass InputItem: sheet: str; tc_id: str; turn: str; feature: str; priority: str; region: str; speaker: str; text_raw: str; expected: str; source_row: int`
  - `@dataclass SheetInfo: name: str; item_count: int; is_testcase: bool`
  - `list_sheets(path: Path) -> list[SheetInfo]`
  - `is_testcase_form(path: Path, sheet: str) -> bool` — dòng 4 có `A == "TC_ID"` và `M == "Câu nói (utterance)"`
  - `read_testcase_items(path: Path, sheets: list[str]) -> list[InputItem]`

- [ ] **Step 1: Test** — fixture có sheet "Tổng hợp" (không phải form), sheet "Hướng dẫn" trống, sheet "ONOFFTemperature Synchronizatio" với header dòng 4 và 4 dòng dữ liệu từ dòng 5: `TC-SYN-001` lượt `1` "Đồng bộ nhiệt độ tất cả các vùng"; `TC-DLG-001` lượt `2` (số) "Bật"; `TC-SYN-002` lượt `1` ô M trống; một dòng ô A trống.
  ```python
  def test_list_sheets_marks_only_form_sheets_with_data(mini_form):
      infos = {s.name: s for s in list_sheets(mini_form)}
      assert infos["ONOFFTemperature Synchronizatio"].is_testcase and infos["ONOFFTemperature Synchronizatio"].item_count == 3
      assert not infos["Tổng hợp"].is_testcase
      assert infos["Hướng dẫn"].item_count == 0

  def test_read_items_maps_columns_and_keeps_turn(mini_form):
      items = read_testcase_items(mini_form, ["ONOFFTemperature Synchronizatio"])
      assert [(i.tc_id, i.turn, i.text_raw) for i in items] == [
          ("TC-SYN-001","1","Đồng bộ nhiệt độ tất cả các vùng"), ("TC-DLG-001","2","Bật"), ("TC-SYN-002","1","")]
      assert items[0].source_row == 5 and items[0].region == "BAC-HN"
  ```
  Dòng có A trống bị bỏ; dòng có M trống **vẫn trả về** (Task 2 phân loại nó là "Ô trống").
- [ ] **Step 2:** `uv run pytest backend/tests/input -v` → FAIL (import error).
- [ ] **Step 3:** Cài openpyxl. Implement bằng `load_workbook(read_only=True, data_only=True)`; cột theo chữ: A,B,E,H,I,L,M,N. Giá trị số (ví dụ lượt `1`) chuyển `str(int(v))`. Lỗi file bị khóa (`PermissionError`) ném `InputError("File đang được mở bởi chương trình khác: ...")`.
- [ ] **Step 4:** Test PASS. Thêm test thật (đánh dấu `@pytest.mark.sample`, skip nếu không có file) đọc `public/DieuKhienXe_Pre.xlsx`: tổng số dòng có TC_ID của 12 sheet dữ liệu == 3986.
- [ ] **Step 5:** Commit `feat(input): read 36-column testcase form`.

### Task 2: Lọc dòng + bỏ từ đánh thức + input chung (csv/xlsx khác form)

**Files:**
- Create: `backend/tts_stt_tool/input/filters.py`, `backend/tts_stt_tool/input/generic.py`
- Test: `backend/tests/input/test_filters.py`, `backend/tests/input/test_generic.py`

**Interfaces:**
- Consumes: `InputItem`
- Produces:
  - `strip_wake_word(text: str) -> str` — bỏ `^\s*hey\s+vi(ta)?\b\s*[,.!:]?\s*` (không phân biệt hoa thường)
  - `classify(item: InputItem) -> tuple[str | None, str | None]` → `(text_tts, skip_reason)`, đúng một trong hai khác None
  - Lý do (chuỗi cố định): `"Dòng hệ thống"`, `"Ô trống"`, `"Chú thích trong ngoặc"`, `"Ký tự không đọc được"`, `"Chỉ có từ đánh thức"`
  - `ColumnMapping: text_col: str; id_col: str | None; header_row: int = 1`
  - `read_generic(path: Path, sheet: str | None, mapping: ColumnMapping) -> list[InputItem]` (csv: utf-8-sig; `sheet=None`)
  - `preview_columns(path: Path, sheet: str | None, header_row: int) -> list[str]`

- [ ] **Step 1: Test**
  ```python
  @pytest.mark.parametrize("raw,expected", [
      ("Hey Vita, bật ionizer nhé", "bật ionizer nhé"),
      ("hey vi bật ionizer", "bật ionizer"),
      ("Bật ionizer", "Bật ionizer"),
      ("Heyy Vita bật", "Heyy Vita bật"),
  ])
  def test_strip_wake_word(raw, expected): assert strip_wake_word(raw) == expected

  @pytest.mark.parametrize("speaker,text,reason", [
      ("🚗 Hệ thống (sự kiện)", "Xe chuyển số D", "Dòng hệ thống"),
      ("👤 Người dùng", "   ", "Ô trống"),
      ("👤 Người dùng", "(không nói gì, chờ quá 8 giây)", "Chú thích trong ngoặc"),
      ("👤 Người dùng", "Mở cổng sạc (lặp 20 lần với 20 cách nói khác nhau)", "Chú thích trong ngoặc"),
      ("👤 Người dùng", "Bật ionizer <script>alert(1)</script>", "Ký tự không đọc được"),
      ("👤 Người dùng", "Mở gương ra đi (nói lần 1) … Mở gương", "Chú thích trong ngoặc"),
      ("👤 Người dùng", "Phát lại toàn bộ câu nói TC-SYN-001 → TC-SYN-079", "Ký tự không đọc được"),
      ("👤 Người dùng", "Hey Vita", "Chỉ có từ đánh thức"),
      ("👤 Người dùng (nữ, giọng Hà Nội, nói nhanh)", "Hey Vita, tắt ionizer đi", None),
  ])
  def test_classify(speaker, text, reason): ...
      # reason None → text_tts == "tắt ionizer đi"
  ```
  Thứ tự kiểm tra: hệ thống → trống → ngoặc `(`/`)` → ký tự `<>{}[]…→|#` → bỏ wake word → rỗng sau khi bỏ.
  Test generic: csv `id,cau\n1,Bật điều hòa` với mapping `text_col="cau", id_col="id"` → 1 item, `sheet == "<file stem>"`, `speaker == "👤 Người dùng"`.
- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat(input): row filters, wake-word strip, generic csv/xlsx`.

### Task 3: Chuẩn hóa text + so sánh WER/CER

**Files:**
- Create: `backend/tts_stt_tool/compare/vi_numbers.py`, `compare/normalize.py`, `compare/score.py`, `backend/tts_stt_tool/compare/rules.json`
- Test: `backend/tests/compare/test_vi_numbers.py`, `test_normalize.py`, `test_score.py`

**Interfaces:**
- Produces:
  - `number_to_words(n: int) -> str` (0 ≤ n < 10^9)
  - `normalize(text: str) -> str`
  - `@dataclass WordOp: op: Literal["equal","sub","del","ins"]; ref: str | None; hyp: str | None`
  - `@dataclass CompareResult: wer: float; cer: float; correct: bool; ref_norm: str; hyp_norm: str; ops: list[WordOp]`
  - `compare(ref: str, hyp: str, wer_threshold: float = 0.0) -> CompareResult` — `correct = wer <= wer_threshold`; ref chuẩn hóa rỗng → `ValueError` (đã được lọc trước đó); hyp rỗng → wer = 1.0, cer = 1.0.

- [ ] **Step 1: Test số**
  ```python
  @pytest.mark.parametrize("n,w", [(0,"không"),(5,"năm"),(10,"mười"),(15,"mười năm"),(21,"hai mươi một"),
      (24,"hai mươi bốn"),(25,"hai mươi năm"),(30,"ba mươi"),(105,"một trăm linh năm"),(110,"một trăm mười"),
      (1000,"một nghìn"),(2024,"hai nghìn không trăm hai mươi bốn"),(1000000,"một triệu")])
  def test_number_to_words(n, w): assert number_to_words(n) == w
  ```
  Dạng chính tắc dùng "một/bốn/năm/linh/nghìn" (không "mốt/tư/lăm/lẻ/ngàn"); biến thể được quy về ở `normalize`.
- [ ] **Step 2: Test chuẩn hóa**
  ```python
  @pytest.mark.parametrize("a,b", [
      ("Chỉnh nhiệt độ ghế lái lên 24 độ", "chỉnh nhiệt độ ghế lái lên hai mươi tư độ"),
      ("Mở cửa kính 30%", "mở cửa kính ba mươi phần trăm"),
      ("Mở cửa kính 30 phần trăm", "Mở cửa kính ba mươi phần trăm."),
      ("Họp lúc 9h", "họp lúc chín giờ"),
      ("Đặt 21 độ", "đặt hai mươi mốt độ"),
      ("Đặt 25 độ", "đặt hai mươi lăm độ"),
      ("một trăm lẻ năm", "105"),
      ("Bật  điều hoà\r\n", "bật điều hòa"),
      (unicodedata.normalize("NFD", "Bật điều hòa"), "Bật điều hòa"),
      ("SĐT của anh", "số điện thoại của anh"),
  ])
  def test_equivalent(a, b): assert normalize(a) == normalize(b)
  ```
  Thứ tự: NFC → chữ thường → kiểu bỏ dấu cũ/mới (`hoà`→`hòa`, `oà/oá/oả/oã/oạ/uỳ…` theo bảng trong `rules.json`) → thay từ tương đương (`rules.json`: `"sđt": "số điện thoại"`) → `(\d+)\s*%` → `\1 phần trăm` → `(\d+)h\b` → `\1 giờ` → số → chữ → bỏ dấu câu → gộp khoảng trắng → biến thể số đứng ngay sau `mươi`/`mười` (`mốt→một`, `tư→bốn`, `lăm|nhăm→năm`) và `lẻ→linh`, `ngàn→nghìn`. Thêm case test `("mười lăm", "15")`.
- [ ] **Step 3: Test so sánh**
  ```python
  def test_identical_is_correct(): r = compare("Bật điều hòa", "bật điều hoà."); assert r.correct and r.wer == 0 and r.cer == 0
  def test_one_sub(): r = compare("mua sữa", "mua sửa"); assert r.wer == 0.5 and not r.correct and WordOp("sub","sữa","sửa") in r.ops
  def test_threshold(): assert compare("a b c d", "a b c x", wer_threshold=0.25).correct
  def test_empty_hyp(): r = compare("bật đèn", ""); assert r.wer == 1.0 and not r.correct
  def test_empty_ref_raises(): pytest.raises(ValueError, compare, "  ...", "x")
  ```
- [ ] **Step 4:** Chạy → FAIL; cài `jiwer`; implement (`jiwer.process_words` để lấy ops, `jiwer.cer` trên chuỗi đã chuẩn hóa); chạy → PASS.
- [ ] **Step 5:** Commit `feat(compare): Vietnamese normalization and WER/CER scoring`.

### Task 4: Settings

**Files:**
- Create: `backend/tts_stt_tool/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass Settings: data_dir: Path; voice: str | None = None; max_regen: int = 3; wer_threshold: float = 0.0; reject_warn_ratio: float = 0.10; wyoming_host: str = "127.0.0.1"; wyoming_port: int = 10300; stt_timeout_s: float = 30.0; wyoming_cmd: list[str] = []; port: int = 8765`; `load_settings(data_dir: Path) -> Settings`; `save_settings(s: Settings) -> None` (JSON tại `data_dir/settings.json`, khóa lạ bị bỏ qua, file hỏng → mặc định + log cảnh báo).

- [ ] **Step 1:** Test: lần đầu → mặc định; lưu `max_regen=5` rồi load → 5; file JSON hỏng → mặc định, không ném lỗi.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat: settings persistence`.

### Task 5: SQLite store

**Files:**
- Create: `backend/tts_stt_tool/store/db.py`
- Test: `backend/tests/store/test_db.py`

**Interfaces:**
- Consumes: `InputItem`, `classify`, `CompareResult`
- Produces:
  - Trạng thái `ItemStatus(StrEnum)`: `PENDING="Chờ"`, `SKIPPED="Không áp dụng"`, `GENERATED="Đã sinh audio"`, `PASSED="Đạt"`, `AUDIO_FAILED="Audio không đạt"`, `ERROR="Lỗi"`
  - Bảng `audio_sets(id, name, source_file, sheets_json, voice, created_at)`; `items(id, audio_set_id, sheet, tc_id, turn, feature, priority, region, speaker, expected, source_row, text_raw, text_tts, skip_reason, enabled, status, audio_path, attempts, ref_text, wer, cer, ops_json, error, updated_at)`. Bảng cho Khối 2 thuộc Kế hoạch 2.
  - `class Store(path: Path)` với: `create_audio_set(name, source_file, sheets, voice, items: list[InputItem]) -> int` (gọi `classify`; dòng bị loại → `SKIPPED`, `enabled=0`); `list_audio_sets() -> list[dict]`; `get_items(audio_set_id, status: ItemStatus | None = None) -> list[dict]`; `pending_for_block1(audio_set_id) -> list[dict]` (enabled và status ∈ {PENDING, GENERATED, ERROR}); `set_item_text(item_id, text_tts)` (→ status PENDING, xóa audio_path/ref/wer/cer, `enabled=1`, `skip_reason=None`); `set_enabled(item_id, enabled: bool)`; `record_generated(item_id, audio_path, attempts)`; `record_verify(item_id, ref_text, result: CompareResult, status)`; `record_error(item_id, msg)`; `summary(audio_set_id) -> dict[str,int]` (đếm theo status).
  - WAL mode; mỗi lần ghi một transaction.

- [ ] **Step 1:** Test: tạo set với 3 item (1 hợp lệ, 1 "Dòng hệ thống", 1 "Hey Vita") → summary `{"Chờ":1,"Không áp dụng":2}`; `set_item_text` trên dòng SKIPPED → trở thành `Chờ`, enabled; `record_verify` lưu wer và ops; mở lại Store cùng file → dữ liệu còn.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(store): sqlite schema for audio sets and items`.

### Task 6: TTS — interface, cache atomic, VieNeu

**Files:**
- Create: `backend/tts_stt_tool/tts/base.py`, `tts/cache.py`, `tts/vieneu_engine.py`
- Test: `backend/tests/tts/test_cache.py`, `backend/tests/tts/test_vieneu_engine.py` (đánh dấu `@pytest.mark.gpu`, skip mặc định)

**Interfaces:**
- Produces:
  - `class TtsEngine(Protocol): def voices(self) -> list[VoiceInfo]; def synthesize(self, text: str, voice: str, attempt: int) -> tuple[np.ndarray, int]` (mảng float32 mono, sample rate). `attempt=0` là mặc định; `attempt>0` đổi tham số theo ghi chú spike (Task 0) để ra kết quả khác.
  - `@dataclass VoiceInfo: id: str; label: str`
  - `cache_key(text_tts: str, voice: str, attempt: int, engine_version: str) -> str` (sha256 hex 16 ký tự của `normalize`-nhẹ: NFC + strip + gộp khoảng trắng — **không** dùng `normalize` của Task 3 để "24" và "hai mươi tư" sinh audio khác nhau)
  - `class AudioCache(root: Path): path_for(key) -> Path; exists(key) -> bool; write(key, audio, sr) -> Path` (ghi `key.wav.tmp` rồi `os.replace`)
  - `class VieneuEngine(TtsEngine)` — tải model lười (lần gọi đầu), dùng GPU nếu `torch.cuda.is_available()`.

- [ ] **Step 1:** Test cache: `cache_key` khác nhau khi đổi text/voice/attempt, giống nhau khi chỉ khác khoảng trắng; `write` tạo WAV đọc lại được bằng soundfile; nếu tồn tại `key.wav.tmp` cũ, `exists(key)` là False.
- [ ] **Step 2–4:** FAIL → implement (soundfile, PCM_16) → PASS.
- [ ] **Step 5:** Test GPU (chạy tay `uv run pytest -m gpu`): `VieneuEngine().synthesize("Bật đồng bộ nhiệt độ", voice, 0)` trả mảng dài > 0.5 s; `voices()` không rỗng.
- [ ] **Step 6:** Commit `feat(tts): engine interface, atomic audio cache, VieNeu engine`.

### Task 7: STT tham chiếu — client Wyoming + quản lý server

**Files:**
- Create: `backend/tts_stt_tool/stt/wyoming_client.py`, `stt/server_manager.py`
- Test: `backend/tests/stt/test_wyoming_client.py` (server Wyoming giả trong test, dùng `wyoming.server.AsyncServer`)

**Interfaces:**
- Produces:
  - `class SttEngine(Protocol): async def transcribe(self, audio: np.ndarray, sr: int) -> str`
  - `class WyomingStt(host: str, port: int, timeout_s: float)` — resample về rate/width/channels ghi trong spike (mặc định 16000/2/1) bằng soxr, chunk 1024 mẫu; vượt `timeout_s` → `SttError("Hết thời gian chờ STT ...")`; không kết nối được → `SttError("Không kết nối được wyoming tại host:port")`.
  - `class WyomingServerManager(cmd: list[str], host, port)`: `async def ensure_running() -> None` (nếu cổng đã mở thì dùng luôn; nếu không, chạy `cmd` bằng subprocess, chờ cổng mở tối đa 120 s); `def stop() -> None`; `async def is_up() -> bool`.

- [ ] **Step 1:** Test: server giả trả `Transcript(text="bật điều hòa")` → `transcribe` trả đúng chuỗi, và server nhận được audio 16 kHz; server giả không trả lời → `SttError` trong ≤ `timeout_s + 1`; cổng đóng → `SttError` kết nối.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Kiểm tra tay với wyoming thật (lệnh từ spike): transcribe WAV từ Task 6 ra text gần đúng. Ghi `wyoming_cmd` mặc định vào `Settings` theo spike.
- [ ] **Step 6:** Commit `feat(stt): wyoming client and server manager`.

### Task 8: Pipeline Khối 1 + job runner

**Files:**
- Create: `backend/tts_stt_tool/pipeline/block1.py`, `backend/tts_stt_tool/jobs/runner.py`
- Test: `backend/tests/pipeline/test_block1.py`, `backend/tests/jobs/test_runner.py`

**Interfaces:**
- Consumes: `Store`, `TtsEngine`, `AudioCache`, `SttEngine`, `compare`, `Settings`
- Produces:
  - `@dataclass ProgressEvent: job_id: str; kind: Literal["item","progress","done","error","cancelled"]; done: int; total: int; item: dict | None = None; message: str | None = None`
  - `async def run_block1(store, audio_set_id, tts, cache, stt, settings, emit: Callable[[ProgressEvent], None], cancel: asyncio.Event) -> None` — với mỗi item của `pending_for_block1`: attempt 0..max_regen → lấy/ghi cache → `record_generated` → transcribe → `compare(text_tts, hyp, wer_threshold)` → đúng thì `PASSED`, dừng; sau lần cuối vẫn sai → `AUDIO_FAILED` (lưu kết quả lần cuối). `SttError`/lỗi TTS ở một item → `record_error`, sang item tiếp. Gọi TTS (đồng bộ, GPU) qua `asyncio.to_thread`. Kiểm tra `cancel` giữa các item.
  - `class JobRunner`: `start(name: str, coro_factory) -> str` (đang có job → `JobBusyError`); `cancel(job_id)`; `subscribe() -> asyncio.Queue[ProgressEvent]`; `current() -> dict | None`.

- [ ] **Step 1:** Test với `FakeTts` (trả sóng sin, ghi lại attempt) và `FakeStt` (trả theo bảng):
  - câu A STT trả đúng ngay → `Đạt`, attempts=1, TTS gọi 1 lần;
  - câu B STT sai 2 lần rồi đúng → `Đạt`, attempts=3;
  - câu C luôn sai, `max_regen=3` → `Audio không đạt`, TTS gọi 4 lần (attempt 0..3);
  - câu D STT ném `SttError` → `Lỗi`, câu E sau đó vẫn chạy;
  - chạy lại `run_block1` lần hai → không gọi TTS cho câu đã `Đạt`; câu `Đã sinh audio` dùng lại cache (TTS không gọi);
  - `cancel` đặt sau item đầu → chỉ 1 item được xử lý, sự kiện cuối `cancelled`.
- [ ] **Step 2:** Test runner: start khi đang chạy → `JobBusyError`; subscriber nhận đủ sự kiện theo thứ tự.
- [ ] **Step 3–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(pipeline): block1 generate-verify-retry with resumable job runner`.

### Task 9: Báo cáo Excel

**Files:**
- Create: `backend/tts_stt_tool/report/excel.py`
- Test: `backend/tests/report/test_excel.py`

**Interfaces:**
- Consumes: `Store`, `Settings`
- Produces: `build_block1_report(store, audio_set_id, settings, out_path: Path) -> Path`. Hàm nhận thêm tham số `app_run_id: int | None = None` để Kế hoạch 2 bổ sung sheet "Khối 2 – App"; ở kế hoạch này luôn None.
  - Sheet **"Tổng quan"**: thông tin set (file, sheet, giọng, thời gian), số câu theo trạng thái, WER/CER trung bình trên các câu đã verify, **tỉ lệ audio bị loại** = Audio không đạt / (Đạt + Audio không đạt), tô đỏ + dòng cảnh báo khi > `reject_warn_ratio`; bảng theo từng sheet tính năng (số câu, Đạt, Audio không đạt, Không áp dụng, tỉ lệ loại).
  - Sheet **"Khối 1 – Verify"**: Sheet, TC_ID, Lượt, Cụm tính năng, Ưu tiên, Câu gốc, Câu đọc (text_tts), Text STT tham chiếu, WER, CER, Từ sai (dạng `sữa→sửa; -từ; +từ`), Số lần sinh, Trạng thái.
  - Sheet **"Audio không đạt"**, **"Không áp dụng"** (kèm lý do), **"Lỗi"**.
  - Header in đậm, cố định dòng đầu, tự lọc, độ rộng cột hợp lý; WER/CER định dạng %.
  - `export_block1_csv(store, audio_set_id, out_path: Path) -> Path` — cùng cột với sheet "Khối 1 – Verify", UTF-8 có BOM (để Excel mở đúng tiếng Việt). Spec §5.2 bước 4 yêu cầu xuất được xlsx hoặc csv; API Task 10 nhận `?format=xlsx|csv`.
- [ ] **Step 1:** Test: CSV xuất ra mở bằng `encoding="utf-8-sig"` có 9 dòng dữ liệu và header đúng. Set có 10 câu (7 Đạt, 2 Audio không đạt, 1 Không áp dụng) → đọc lại file: có đủ 5 sheet; "Tổng quan" chứa tỉ lệ loại `2/9` ≈ 22.2% và ô cảnh báo có màu đỏ (`fill.fgColor.rgb` chứa `FF`… đỏ); "Khối 1 – Verify" có 9 dòng dữ liệu; tên sheet đúng chính tả.
- [ ] **Step 2–4:** FAIL → implement (openpyxl ghi thường, không read_only) → PASS.
- [ ] **Step 5:** Commit `feat(report): block1 Excel report`.

### Task 10: API + WebSocket + CLI

**Files:**
- Create: `backend/tts_stt_tool/api/app.py`, `api/routes.py`, `api/ws.py`, `backend/tts_stt_tool/cli.py`, `backend/tts_stt_tool/__main__.py`
- Test: `backend/tests/api/test_routes.py` (FastAPI TestClient, engine giả qua dependency override)

**Interfaces:**
- Consumes: mọi thứ ở trên.
- Produces (JSON, tiền tố `/api`):
  - `POST /files/inspect` (multipart file) → lưu vào `data/uploads/<uuid>_<tên>`; trả `{file_id, sheets: SheetInfo[], is_form: bool, columns?: string[]}`
  - `POST /audio-sets` `{file_id, sheets: string[], name, mapping?: ColumnMapping}` → `{id}`
  - `GET /audio-sets` · `GET /audio-sets/{id}/items?status=` · `GET /audio-sets/{id}/summary`
  - `PATCH /items/{id}` `{text_tts?: string, enabled?: bool}`
  - `POST /audio-sets/{id}/block1` → `{job_id}` (409 nếu đang có job) · `POST /jobs/{job_id}/cancel` · `GET /jobs/current`
  - `GET /items/{id}/audio` → `audio/wav`
  - `POST /audio-sets/{id}/report` → tải file xlsx (`reports/<tên set>_<yyyyMMdd-HHmm>.xlsx`)
  - `GET/PUT /settings` · `GET /voices` · `GET /health` → `{wyoming: bool, gpu: bool}`
  - WS `/ws` phát `ProgressEvent` dạng JSON.
  - CLI `main()`: `load_settings(Path("data"))`, khởi động `WyomingServerManager.ensure_running()` khi app startup (lỗi → log + `/health` báo false, app vẫn chạy), uvicorn `127.0.0.1:settings.port`, mở trình duyệt; phục vụ `frontend/dist` ở `/`.
- [ ] **Step 1:** Test: upload `mini_form.xlsx` → `is_form` true; tạo set → items có trạng thái đúng; PATCH text → status `Chờ`; chạy block1 với engine giả → `GET summary` cuối cùng có `Đạt`; gọi block1 lần hai khi đang chạy → 409; report trả content-type xlsx.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `feat(api): REST + websocket + CLI entrypoint`.

### Task 11: Frontend — khung 3 cột, nạp file, bảng, chạy Khối 1, báo cáo

**Files:**
- Create: `frontend/` (Vite React TS), `frontend/src/api.ts`, `src/ws.ts`, `src/App.tsx`, `src/components/{Sidebar,ImportDialog,ItemTable,RunBar,SettingsPanel,DevicePanel}.tsx`, `src/format.ts`
- Test: `frontend/src/format.test.ts`, `frontend/src/components/ItemTable.test.tsx` (vitest + testing-library)

**Interfaces:**
- Consumes: API Task 10.
- Bố cục (theo spec §5.5): **trái** 220px — mục Dữ liệu, Sinh audio & Verify, Test app (mờ, "Kế hoạch 2"), Báo cáo; dưới cùng: trạng thái wyoming/GPU (từ `/health`), Hồ sơ app (mờ), Cài đặt. **Giữa** — thanh nút `[Nạp file] [Sinh audio + Verify] [Dừng] [Xuất Excel]`, bộ chọn bộ audio, bộ lọc trạng thái, bảng, thanh tiến độ + "Đạt x% · Loại y%". **Phải** 360px — `DevicePanel` hiển thị "Chưa kết nối thiết bị (Khối 2)".
- Bảng: cột `# | Sheet | TC_ID | Lượt | Câu gốc | Câu đọc (sửa được) | ▶ | Text STT | WER | CER | Trạng thái`, cuộn ảo (@tanstack/react-virtual) chịu 4.000 dòng; checkbox bật/tắt dòng; ô "Câu đọc" sửa inline (Enter lưu → PATCH); ▶ phát `/api/items/{id}/audio`; ô Text STT tô từ sai dựa trên `ops` (sub vàng, del gạch đỏ, ins xanh); dòng "Không áp dụng" hiện lý do khi hover.
- ImportDialog: chọn file → nếu là form: danh sách sheet có checkbox (sheet `is_testcase && item_count>0`, hiện số câu) → tạo bộ audio; nếu không: chọn cột Text/ID.
- `format.ts`: `formatPct(x: number) -> string` (`0.222 → "22,2%"`), `renderOps(ops) -> Segment[]`.

- [ ] **Step 1:** `npm create vite@latest frontend -- --template react-ts`, cài deps; cấu hình proxy `/api` & `/ws` → `127.0.0.1:8765` khi dev; `build.outDir = "dist"`.
- [ ] **Step 2: Test** — `formatPct(0.2222) === "22,2%"`; `renderOps` trả segment đúng loại; `ItemTable` với 4.000 dòng giả chỉ render < 100 hàng DOM và tô vàng từ `sub`.
- [ ] **Step 3:** `npx vitest run` → FAIL → implement → PASS.
- [ ] **Step 4:** `npm run build`, `uv run tts-stt-tool` → mở trình duyệt; kiểm tra tay với `public/DieuKhienXe_Pre.xlsx`: chọn sheet "ONOFFTemperature Synchronizatio" → bảng 261 dòng, các dòng "(...)"/"Hệ thống" ở trạng thái "Không áp dụng"; chạy Sinh audio + Verify trên ~20 câu (bộ lọc), thấy tiến độ cập nhật, nghe được audio, Dừng rồi chạy lại tiếp tục đúng chỗ; Xuất Excel mở được.
- [ ] **Step 5:** Commit `feat(ui): three-column UI with import, table, block1 run and report`.

### Task 12: README chạy tool

**Files:**
- Create: `README.md`
- [ ] **Step 1:** Ghi: cài uv; `uv sync`; cài torch CUDA (lệnh từ spike); cách chạy wyoming (lệnh từ spike, hoặc để tool tự bật qua `wyoming_cmd`); `cd frontend && npm i && npm run build`; `uv run tts-stt-tool`; vị trí dữ liệu `data/`.
- [ ] **Step 2:** Làm theo README trên một terminal mới từ đầu → tool mở được. Commit `docs: how to run`.
