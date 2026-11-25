# Bảng "Thiết bị kiểm thử" + chọn CPU/GPU cho TTS — thiết kế ngắn

## Mục đích
Footer sidebar hiện chỉ có 3 chip (STT · CPU · ADB), không thấy hết thiết bị và không chọn được
CPU/GPU. Người dùng cần một bảng checklist kiểu "sẵn sàng test chưa" (theo mẫu tham khảo), nhìn
được mọi điện thoại đang cắm, và chọn sinh audio bằng CPU hay GPU — GPU thì app tự kiểm tra và tự
cài CUDA (PyTorch bản CUDA) nếu thiếu.

## Mục tiêu / không làm
- Có: bảng thu gọn được "Thiết bị kiểm thử" ở chân sidebar, thay 3 chip; mỗi thiết bị ADB một dòng;
  nút gạt CPU | GPU; tự cài torch CUDA trong app với xác nhận + tiến độ; lưu lựa chọn vào settings.
- Không: cài driver NVIDIA; chọn điện thoại cho Bước 2 từ bảng này (Bước 2 giữ cách chọn hiện tại).
- Thất bại nếu: đổi thiết bị giữa lúc đang sinh audio làm hỏng job; app treo/khởi động lại khi cài.

## Cách tiếp cận (đã chọn A)
- **A. Cài trong app (chọn)** — backend dò `nvidia-smi`, nếu có card mà chưa có torch CUDA thì sau khi
  người dùng xác nhận (~2.5 GB) chạy `uv pip install torch --index-url https://download.pytorch.org/whl/cu128`
  ở nền, xong nạp lại model trên GPU, không cần restart.
- B. Chỉ hiện lệnh cài để người dùng tự chạy — đơn giản nhưng không "tự cài".

## Thiết kế
**Giao diện** (chân sidebar, thu gọn được, nhớ trạng thái mở/đóng trong localStorage):
```
 Thiết bị kiểm thử                ● ^
 [ Sẵn sàng test | Chưa sẵn sàng test ]
 Điện thoại · ADB    ● <model> (<serial>)      — mỗi thiết bị một dòng, trạng thái riêng
 STT tham chiếu      ● Sẵn sàng / Chưa chạy
 Sinh audio (TTS)    [CPU | GPU]  ● CPU/GPU    — tiến độ cài hiện ngay dưới khi đang cài
 <dòng gợi ý việc cần làm tiếp, nếu có>
```
"Sẵn sàng test" = STT chạy + có ít nhất 1 điện thoại trạng thái `device`. Công tắc giao diện sáng/tối
giữ ở đầu bảng.

**Backend**
- `Settings.tts_device: "cpu" | "cuda"` (mặc định `cpu`).
- `VieneuEngine(device=...)` truyền `device` vào `Vieneu(mode="v3turbo", device=...)`;
  `set_device(d)` bỏ model cũ (dưới lock) để lần gọi sau nạp lại.
- `GET /api/tts/device` → `{device, nvidia: bool, gpu_name, torch_cuda: bool, install: {state, log_tail, error}}`.
  `nvidia` từ `nvidia-smi` (có cache); `torch_cuda` kiểm bằng subprocess `python -c "import torch; ..."`
  để không bị kẹt kết quả import cũ trong tiến trình.
- `PUT /api/tts/device {device}`: 409 nếu đang có job; `cuda` mà chưa có torch CUDA → 409 kèm lý do
  (frontend dùng để hỏi cài); hợp lệ thì lưu settings + `set_device`.
- `POST /api/tts/install-cuda`: 400 nếu không có NVIDIA; chạy cài ở nền (một lần một lúc), state
  `idle|running|done|failed` + đuôi log; xong thì tự đặt `tts_device=cuda`.
- `/health.gpu` giữ nguyên để không vỡ chỗ khác.

**Frontend**: `DeviceStatusPanel` mới thay `side-footer`; poll `/api/tts/device` (2s khi đang cài,
còn lại cùng nhịp health). Bấm GPU: không có NVIDIA → nút khóa + tooltip; thiếu torch CUDA →
`confirm("Tải PyTorch CUDA ~2.5 GB?")` → gọi install.

## Quyết định của builder (mình tự chốt)
- Bỏ dòng "Loa máy tính": không có cách kiểm tra tin cậy mà không thêm thư viện.
- Đang cài thì vẫn sinh audio bằng CPU được; chỉ chuyển sang GPU khi cài xong.
- Nếu cài xong mà torch vẫn báo không có CUDA (driver quá cũ) → báo lỗi, giữ CPU.
