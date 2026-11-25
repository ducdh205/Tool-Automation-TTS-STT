# Xuất / nạp bộ audio — thiết kế ngắn

Ngày: 2026-11-25

## Mục đích

Lưu một bộ audio đã sinh (và đã verify) ra một file, để lần sau nạp lại vào chính tool này và test
tiếp ở Bước 2 mà không phải sinh audio / verify lại. `data/` không được commit và nút **Xóa tất cả**
xóa sạch bộ audio, nên hiện không có cách giữ lại một bộ.

## Mục tiêu / không làm

- **Mục tiêu:** xuất từng bộ audio thành một file `.zip`; nạp file đó tạo lại bộ audio với đầy đủ
  trạng thái — câu **Đạt** khi xuất vẫn **Đạt** khi nạp, dùng được ngay ở Bước 2.
- **Không làm:** không kèm kết quả test trên điện thoại (phiên, ảnh chụp) — đã có "Zip phiên".
  Không gộp / ghi đè vào bộ có sẵn. Không xuất nhiều bộ trong một file.
- **Coi là hỏng nếu:** nạp xong câu Đạt bị về Chờ, hoặc Excel theo form của bộ nạp vào thiếu dữ liệu
  form, hoặc nạp file lạ ghi được ra ngoài thư mục audio.

## Các hướng đã cân nhắc

- **A. Zip có `manifest.json` + WAV (đã chọn).** Một file, chọn được từng bộ, giữ trạng thái, không
  phụ thuộc đường dẫn máy. Tốn thêm phần kiểm tra file nạp.
- B. Xuất thư mục WAV + Excel, nạp qua luồng "Nạp file". Mất trạng thái verify → phải làm lại.
- C. Chép thô `tool.db` + `audio/`. Không chọn được từng bộ, dễ đè dữ liệu.

## Thiết kế

**Định dạng zip**

```
<tên bộ>_<yyyy-mm-dd>.zip
├── manifest.json
└── audio/<tên file trong cache>.wav
```

`manifest.json`: `{"format": "tts-stt-audio-set", "version": 1, "exported_at", "audio_set": {name,
source_file, sheets, voice, voice_trung, voice_nam, created_at}, "items": [...]}`. Mỗi item gồm mọi
cột của bảng `items` trừ `id`, `audio_set_id` (kể cả `form_json`, `ops_json`, `status`, `wer`, `cer`,
`ref_text`, `attempts`, `enabled`, `skip_reason`); `audio_path` thay bằng `audio` = đường dẫn
tương đối trong zip (`audio/<tên>.wav`) hoặc `null`.

**Backend**

- `POST /audio-sets/{set_id}/export` → dựng zip trong `reports/` (chạy trong thread), trả token tải
  qua route có sẵn `GET /exports/{token}` (cùng cơ chế "Zip phiên").
- `POST /audio-sets/import` (upload zip) → tạo **bộ mới**:
  - Kiểm tra `format`/`version`; sai → 422 với thông báo tiếng Việt.
  - Tên trùng bộ có sẵn → thêm hậu tố ` (2)`, ` (3)`…
  - WAV chép vào cache audio (`ctx.cache.root`) giữ tên file (cache đánh địa chỉ theo nội dung, file
    trùng tên thì bỏ qua không chép). Chỉ nhận entry dạng `audio/<tên>.wav` không có `..`/thư mục con
    — chặn ghi ra ngoài cache.
  - Item có `audio` nhưng thiếu file trong zip → reset về trạng thái chưa có audio (như `_RESET_SQL`)
    và đếm lại; trả `{"id", "missing_audio": n}`.
  - Bị khóa (409) khi đang chạy job, như xóa bộ.
- `Store`: thêm `export_audio_set(set_id) -> dict` và `import_audio_set(manifest, audio_paths) -> int`
  (chèn thẳng các cột, không chạy lại `classify`).

**Giao diện (thanh trái, danh sách Bộ audio)**

- Mỗi bộ: nút **Xuất** cạnh nút xóa (hiện khi rê chuột) → tải file zip.
- Cạnh tiêu đề *Bộ audio*: nút **Nạp bộ audio** → chọn `.zip` → nạp xong chọn luôn bộ mới; nếu
  `missing_audio > 0` thì báo "n câu thiếu audio, cần sinh lại".

## Quyết định của Claude (có thể sửa)

- Nạp luôn tạo bộ mới, trùng tên thì thêm hậu tố.
- Không kèm kết quả Bước 2.
- Thiếu WAV → câu về chưa có audio, có thông báo.
- Có trường `version` để sau này đổi định dạng vẫn nhận được file cũ.

## Để người làm tự quyết

Tên biểu tượng/nhãn nút cụ thể, cách hiện thông báo (theo kiểu thông báo sẵn có của UI), giới hạn
kích thước upload (theo cấu hình upload hiện có).
