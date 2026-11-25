# Export kết quả giữ nguyên format file input — thiết kế ngắn

Ngày: 2026-11-25

## Mục đích

File Excel kết quả của một phiên test (Bước 2) phải là **chính file input của tester**, giữ nguyên
định dạng, chỉ thêm kết quả vào — để tester đọc/gửi tiếp trên file quen thuộc của họ. Bỏ hẳn việc
tuân theo mẫu form 36 cột.

## Mục tiêu / không làm

- **Mục tiêu:**
  - Bản sao file input (giữ màu, độ rộng cột, ô gộp, data validation, conditional formatting).
  - Chỉ giữ các sheet đã chọn khi tạo bộ audio; xóa các sheet còn lại.
  - Sheet **Tổng hợp phiên** chèn lên đầu, nội dung như hiện nay (Bộ audio, File nguồn + khối KHỐI 2 – APP).
  - Mỗi sheet dữ liệu thêm 3 cột ngay sau cột cuối đang dùng: **Text app nghe được**, **Kết quả**,
    **Ghi chú**.
- **Không làm:** không điền / sửa bất kỳ cột nào có sẵn của file gốc. Không còn xử lý riêng mẫu 36 cột.
- **Coi là hỏng nếu:** kết quả ghi lệch dòng, mất định dạng gốc, hoặc còn sót sheet không được chọn.

## Các hướng đã cân nhắc

- **A. Lưu một bản file gốc kèm bộ audio (đã chọn).** Export lúc nào cũng được, không phụ thuộc
  thư mục uploads (bị "Xóa tất cả" dọn). Tốn thêm 1 bản file / bộ.
- B. Hỏi lại file gốc lúc export. Phiền, dễ chọn nhầm phiên bản đã sửa → lệch dòng.
- C. Dựng lại từ dữ liệu đã đọc. Mất định dạng — trái mục đích.

## Thiết kế

**Lưu file gốc**
- Tạo bộ audio: chép file upload vào `data/sources/<set_id>/<tên file gốc>`.
- `audio_sets` thêm cột `source_path TEXT` (đường dẫn bản chép) và `header_row INTEGER` (migration
  như các cột đã thêm trước đây; bộ cũ = NULL).
- Xóa bộ audio / "Xóa tất cả" xóa luôn thư mục `data/sources/<set_id>`.
- Khi làm tính năng xuất/nạp bộ audio (spec 2026-11-25-audio-set-export-import): zip phải kèm file
  gốc + `header_row`, nạp lại thì khôi phục `source_path`.

**Dựng file kết quả** (`report/result_export.py`, thay `form_export.py`)
- Có file gốc (.xlsx/.xlsm): `openpyxl.load_workbook` (`keep_vba=True` với .xlsm, đuôi file giữ
  nguyên); xóa sheet không nằm trong `sheets` của bộ; tạo sheet "Tổng hợp phiên" ở vị trí 0 (trùng
  tên sheet gốc → thêm hậu tố ` (2)`).
- Mỗi sheet: cột mới bắt đầu ở `max_column + 1` của dòng header (cột cuối có header hoặc dữ liệu).
  Header 3 cột ghi ở dòng `header_row`, chép font/fill/border/alignment của ô header cuối cùng bên
  trái. Kết quả ghi vào dòng `source_row` của từng câu. Auto-filter của sheet (nếu có) nới ra bao 3
  cột mới. Độ rộng: 40 / 14 / 50, wrap text ở cột Text app và Ghi chú.
- Giá trị:
  - **Text app nghe được**: câu app trả (hoặc "(app không trả câu)") với câu Đúng/Sai; trống nếu chưa test.
  - **Kết quả**: `Pass` / `Fail` / `Lỗi thao tác: <lỗi>`; trống nếu chưa test.
  - **Ghi chú**: `WER x% · CER y%`, thêm `· sai: <từ sai>` nếu có, `· câu đã đọc: <text_tts>` nếu khác
    câu gốc.
- Không có file gốc (bộ cũ, file bị mất, input CSV): workbook mới, sheet Tổng hợp + mỗi sheet một
  bảng đơn giản (TC_ID, Lượt, Vùng miền, Câu gốc, Kết quả mong đợi) + 3 cột trên.

**Bỏ mẫu 36 cột**
- Xóa `report/form_export.py` và test của nó; `input/generic.py` bỏ nhánh `is_form` (speaker luôn
  mặc định, feature/priority rỗng); bỏ `InputItem.form`, `Store.form_cells`, không ghi `form_json`
  nữa (cột DB để nguyên, không đọc).
- Route `POST /app-runs/{id}/form-report` và zip phiên dùng hàm mới; tên file
  `KetQua_<bộ>_Phien<id>.<đuôi gốc>`. Frontend chỉ đổi tên file tải về theo header của response.

## Để người làm tự quyết

Cách tìm "cột cuối" khi header có ô gộp, tên hàm/biến, bố cục test.

## Bổ sung 2026-11-26: cột Ảnh màn hình

- Cột thứ 4 **Ảnh màn hình** sau Ghi chú (rộng 22), cả file gốc lẫn bảng đơn giản, cả trong zip phiên.
- Câu Fail / Lỗi thao tác có `screenshot_path`: nhúng ảnh thu nhỏ cao 240px (giữ tỉ lệ, JPEG) neo ở ô đó;
  dòng có ảnh nới chiều cao cho vừa (chỗ duy nhất đổi định dạng gốc). File ảnh mất / không đọc được →
  chữ "(không tìm thấy ảnh)". Pass / chưa test / không có ảnh → trống.
- Đã loại: link tới ảnh trong zip (hỏng khi mở Excel riêng), nhúng ảnh gốc (file quá nặng).
