# Nhập testcase bằng mapping cột — thiết kế

Ngày: 2026-11-25

## Mục đích

Hộp thoại nạp file hiện có 2 nhánh: (1) tự nhận diện form 36 cột, chỉ tick sheet, cột cố định theo chữ cái,
tiêu đề cố định dòng 4; (2) file khác chỉ chọn cột câu nói + cột mã, tiêu đề cố định dòng 1. File testcase
thực tế có cột lệch, tiêu đề không ở dòng 4, hoặc không theo form → không nạp được hoặc mất dữ liệu (vùng miền,
kết quả mong đợi). Người dùng muốn **tự chọn sheet, dòng tiêu đề và cột cho từng trường**, thay cho nhận diện tự động.

## Mục tiêu

- Một luồng duy nhất cho mọi file .xlsx / .xlsm / .csv: chọn sheet → dòng tiêu đề → map cột → xem trước → tạo bộ audio.
- Bố cục theo ảnh mẫu (tiêu đề "NHẬP DỮ LIỆU TESTCASE" + tên file, khung Sheet / Dòng tiêu đề / Tổng số dòng,
  lưới mapping 3 cột có chú thích, bảng xem trước tối đa 20 dòng, footer nút).
- Thêm trường **Vùng miền**.
- Đánh dấu rõ trường bắt buộc / nên chọn / tùy chọn.
- Nạp **nhiều sheet dùng chung một mapping** thành **một** bộ audio (phương án B).

## Không làm (non-goals)

- Không có "Luồng mong đợi (Langfuse)".
- Không có nút "Thay thế danh sách" / "Thêm vào danh sách" (mỗi lần tạo là một bộ audio mới).
- Không có mapping riêng cho từng sheet.
- Không nhận diện form 36 cột trên giao diện (không còn `is_form`, không tự tick sheet).

## Anti-goals

- File Excel kết quả (xuất form) **không được** mất cột so với hiện nay khi file nguồn là form 36 cột.
- Câu lệnh dạng số (vd "0912345678") không được mất số 0 đầu (giữ hành vi `cell_text`).

## Các phương án đã cân nhắc

- **A. Mỗi lần một sheet → một bộ audio.** Đúng ảnh nhất, đơn giản. Nhưng file nhiều sheet bị tách thành nhiều bộ,
  chạy và xuất riêng. Không chọn.
- **B. Nhiều sheet, chung mapping, một bộ audio. ← Đã chọn.** Ô Sheet trong ảnh dùng để chọn sheet xem trước; thêm
  danh sách tick "Nạp các sheet". Mapping khớp theo **tên cột**; sheet nào thiếu cột đã map → báo lỗi nêu tên sheet.
  Giữ được hành vi xuất một file nhiều sheet như hiện nay.
- **C. Mapping riêng từng sheet.** Linh hoạt nhất nhưng thao tác nhiều, UI phức tạp. Không chọn.

## Trường mapping (đã chốt)

| Trường | Mức | Lưu vào | Không map thì |
|---|---|---|---|
| Câu lệnh | **Bắt buộc** `*` | `text_raw` | Không cho tạo |
| Mã câu (Case ID) | Nên chọn | `tc_id` | Tự sinh = số dòng Excel. Khi đã map: dòng có ô mã trống bị bỏ qua (giữ hành vi cũ) |
| Vùng miền | Nên chọn | `region` | Rỗng. Có thêm lựa chọn "Giá trị cố định…" → ô nhập (vd `BAC-HN`) áp cho mọi dòng |
| Kết quả mong đợi | Nên chọn | `expected` | Rỗng (AI chấm thiếu căn cứ) |
| Kịch bản hội thoại (Bước / Lượt) | Tùy chọn | `turn` | `"1"` |

Trường "nên chọn" chưa map hiện chú thích màu cảnh báo nhẹ, **không** chặn nút tạo.

## Thiết kế

### Backend

- `POST /files/inspect` (giữ đường dẫn): lưu file, trả `{file_id, sheets: [{name}]}`. CSV → `sheets: []`.
  Bỏ `is_form`, `columns`, `item_count`, `is_testcase`.
- **Mới** `POST /files/preview` `{file_id, sheet: str|null, header_row: int}` →
  `{columns: string[], rows: string[][] (≤20 dòng dữ liệu không rỗng), row_count: int (số dòng dữ liệu không rỗng
  sau dòng tiêu đề), suggestions: {text_col?, id_col?, region_col?, expected_col?, turn_col?}}`.
  `header_row` ngoài phạm vi / sheet không có → 422 với thông báo tiếng Việt.
- `POST /audio-sets` `{file_id, sheets, name, mapping}` — `mapping` **bắt buộc**:
  `{header_row, text_col, id_col?, region_col?, region_value?, expected_col?, turn_col?}`.
  `region_col` và `region_value` loại trừ nhau (cả hai → 422). Xlsx phải có ≥1 sheet.
  Đọc lần lượt từng sheet; cột đã map không có trong tiêu đề sheet nào → 422 `Sheet 'X' không có cột 'Y'`.
- `input/generic.py`: `ColumnMapping` thêm các trường trên; `read_generic` nhận danh sách sheet, điền
  `region`/`expected`/`turn`; giữ bỏ qua dòng rỗng và `tc_id` = số dòng khi trống.
- **Giữ cột cho file xuất (ẩn, không lên UI):** nếu dòng tiêu đề của sheet có ô A = `TC_ID` và ô M =
  `Câu nói (utterance)` (tiêu chí cũ, nhưng ở dòng tiêu đề người dùng chọn), lưu 36 ô A..AJ của mỗi dòng vào
  `form` → `form_json` như hiện nay, và điền thêm `feature` (B), `priority` (E), `speaker` (L) từ các ô đó.
  Ngược lại `form = []`, export dùng `_FALLBACK` như với bộ audio cũ.
- Tiêu đề trống hiển thị/khớp là `Cột <chữ cái>` (vd `Cột F`); tiêu đề trùng tên thêm hậu tố ` (2)`, ` (3)`… —
  cùng một hàm chuẩn hóa dùng cho cả preview và đọc, nên mapping theo tên vẫn ổn định.
- Gợi ý tự động: so khớp tên cột đã chuẩn hóa (chữ thường, bỏ dấu cách thừa) với danh sách từ khóa
  (text: "câu nói", "utterance", "câu lệnh", "text"; id: "tc_id", "mã câu", "case id", "id"; region: "vùng miền",
  "region"; expected: "kết quả mong đợi", "expected"; turn: "bước / lượt", "bước", "lượt", "turn").
- `input/testcase_form.py`: giữ `InputError`, `cell_text`, `open_workbook`; xóa `list_sheets`/`read_testcase_items`/
  `is_testcase_form`/`_is_form` cùng test của chúng; `SheetInfo` chỉ còn `name` (hoặc bỏ).

### Frontend (`ImportDialog.tsx`)

1. Chưa có file: vùng chọn file như hiện tại.
2. Có file: header "NHẬP DỮ LIỆU TESTCASE" + tên file + nút ✕.
3. Khung xám: **Sheet** (select, sheet xem trước; ẩn với CSV) · **Dòng tiêu đề** (số, mặc định 1) ·
   **Tổng số dòng** (`row_count` của sheet đang xem). Đổi sheet/dòng tiêu đề → gọi lại `/files/preview`
   (debounce ~300 ms cho ô số).
4. Chú thích + danh sách tick **Nạp các sheet** (mặc định tick sheet đang xem; "Chọn tất cả").
5. Checkbox **Giữ cửa sổ này để nạp tiếp sheet khác**: sau khi tạo, gọi `onCreated` nhưng không đóng; bỏ tick
   các sheet vừa nạp, giữ mapping.
6. Lưới mapping 3 cột (Mã câu · Câu lệnh* · Kịch bản hội thoại / Kết quả mong đợi · Vùng miền), mỗi ô là select
   `— Không map —` + các cột, chú thích nhỏ bên dưới như ảnh. Vùng miền có thêm `Giá trị cố định…` → ô nhập.
   Khi preview trả gợi ý, chỉ điền vào trường người dùng chưa tự chọn.
7. **Xem trước dữ liệu**: "N dòng dữ liệu · hiển thị tối đa 20 dòng", bảng cuộn ngang, header dính; cột đang
   được map tô nhẹ + nhãn trường.
8. Ô **Tên bộ audio** (mặc định tên file).
9. Footer: lỗi (nếu có) · **Hủy** · **Tạo bộ audio** (disabled khi chưa map Câu lệnh, chưa chọn sheet với xlsx,
   tên rỗng, hoặc đang xử lý).

`App.tsx`: `onCreated` không tự đóng dialog nữa — dialog tự gọi `onClose` khi không tick "Giữ cửa sổ".

## Để người làm quyết định

- Class CSS / kích thước modal (rộng ~900px, theo token màu sẵn có, hỗ trợ dark mode).
- Cách tính `row_count` hiệu quả (đọc một lượt `read_only`).
- Chi tiết thông báo lỗi.

## Kiểm thử

- Backend: preview (header_row khác 1, tiêu đề trống/trùng, gợi ý), tạo bộ audio nhiều sheet, thiếu cột ở một sheet
  → 422, `region_value`, file form 36 cột vẫn lưu `form_json` khi header ở dòng 4, CSV.
- Frontend: render sau inspect, nút tạo bị khóa khi chưa map Câu lệnh, body gửi đúng mapping, chế độ giữ cửa sổ.
- Cập nhật `test_routes.py` (bỏ assert `is_form`), `api.test.ts`.
