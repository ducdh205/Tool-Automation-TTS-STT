# Khối 2 trên iPhone (WebDriverAgent) — thiết kế

Ngày: 2026-11-26

## Mục tiêu

Chạy Khối 2 (loa phát câu, app nghe bằng micro thật, tool đọc câu app nhận được) trên iPhone,
từ máy Windows, không cần Mac. Android giữ nguyên.

## Hạ tầng (đã dựng tay, xem `memory` / tóm tắt setup)

- WebDriverAgent (WDA) cài trên iPhone, chạy bằng `pymobiledevice3 developer dvt xcuitest <bundle> --userspace`.
- `vendor/go-ios/ios.exe forward 8100 8100` đưa WDA ra `http://127.0.0.1:8100`.
- `go-ios` còn dùng để liệt kê máy (`list --details`), tên máy (`info`), phiên bản app (`apps`).

Tool **chưa** tự khởi động WDA ở bản này: người dùng chạy 3 lệnh trên; tool chỉ phát hiện và báo
trạng thái ("Chưa chạy WebDriverAgent"). Tự quản lý WDA là bước sau.

## Khảo sát UI Vita trên iOS 26 (mẫu: `data/ios_samples/`, fixtures `backend/tests/fixtures/ios_*.xml`)

| Quan sát | Hệ quả |
|---|---|
| Nhãn nút giống Android: "Nói để tạo việc", "Dừng nghe", "Bấm để nói", "Đóng" | Dùng chung hồ sơ app; bundle id = package (`com.vita.suite.dev`) |
| `/source` ~0,2 s (Android `uiautomator dump` ~2,5 s) | Không có `dumpsys audio`: chờ mic bằng cách đợi nút "Dừng nghe" hiện |
| `TextField` phủ cả sheet, `label` = toàn bộ chữ sheet, chữ đang nghe ở `value` | Không dùng ô nhập làm mốc dưới của chat như `EditText` Android |
| Câu người dùng: `StaticText` canh phải trong sheet; câu lỗi của app canh trái | `right_bubbles` dùng được; loại Button/TextField/Image/Other khỏi bong bóng |
| Phần tử ẩn có kích thước 0 | Bỏ khi parse |
| Toạ độ là point (393×852), ảnh chụp là pixel (×3) | Driver chạy theo point; API điều khiển tay đổi pixel → point |
| Dump ngay sau khi tạo session có thể báo sai hướng xoay | Driver dump lại khi khung app không khớp kích thước cửa sổ |
| Không có phím Back | `back()` = chạm "Đóng"/"Quay lại"/… trên dump mới; không có thì vuốt từ mép trái |

Chưa thấy form "Bạn nói: …" và hộp thoại "Bỏ thay đổi?" trên iOS (máy chủ app báo lỗi lúc khảo sát);
luồng đọc `heard_prefix` / `discard_label` dùng nguyên như Android, cần kiểm lại khi máy chủ chạy.

## Thành phần

- `device/wda.py` — `WdaClient` (httpx): status, session (tự tạo lại khi hết hạn), source, screenshot,
  window size, tap, drag, pressButton, keys, homescreen, launch.
- `device/goios.py` — `GoIos`: `list --details`, `info` (DeviceName), `apps` (CFBundleShortVersionString + CFBundleVersion).
- `device/ui_tree.py` — `parse_wda_source(xml)` → `UiNode` (cls = `XCUIElementType…`).
- `device/ios.py` — `IosDriver` (cài `DeviceDriver`, `fast_ui = True`, `mic_active()` → None) và
  `IosHub` (phát hiện máy, giữ một driver/UDID, điều khiển tay theo pixel ảnh chụp).
- `pipeline/block2.py` — `_wait_mic`: driver `fast_ui` mà không đọc được mic → đợi `stop_label`.
- API `/api/device…` — gộp máy Android (adb) và iPhone; mỗi máy có `platform`. Các route màn hình /
  chạm / ghim nút / chạy Khối 2 chọn backend theo serial (UDID).
- Giao diện — hiện iPhone trong bảng Thiết bị và Thiết bị kiểm thử; ẩn phím Đa nhiệm/Nguồn với iPhone;
  gõ được tiếng Việt có dấu với iPhone.

## Giới hạn

- Một WDA (cổng 8100) ⇒ một iPhone điều khiển được tại một thời điểm.
- Chữ ký WDA (Apple ID thường) hết hạn sau 7 ngày — hiện tại 03/12/2026.
