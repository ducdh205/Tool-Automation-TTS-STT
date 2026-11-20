# Spike môi trường — 2026-11-20

Máy dev: Windows 11, **không có GPU NVIDIA** (chỉ Intel Iris Xe). Không có Docker, không có adb trong PATH.
Windows bật **Application Control (Smart App Control)**: chặn một số file nhị phân "lạ".

## Python

- Dự án: Python **3.12** qua uv (`uv sync`). `ssl` import được.
- `python3.15.exe` trong `~/.local/bin` bị Application Control chặn → luôn gọi qua `uv`.

## wyoming-vietnamese

- Clone vào `vendor/wyoming-vietnamese` (git-ignored). Repo yêu cầu Python ≥ 3.14, `uv sync --no-dev`.
- **Python 3.14.10 bị chặn** khi nạp `_ssl.pyd` ("An Application Control policy has blocked this file").
  **3.14.8 không bị chặn** → dùng `uv sync --no-dev --python 3.14.8`.
  Python 3.15 không dùng được (pyyaml không có wheel, repo đặt `no-build`).
- Repo import `fcntl` (chỉ có trên Unix) để khóa file khi tải model → chạy qua
  `backend/tts_stt_tool/stt/wyoming_win_launcher.py`, launcher thay `fcntl` bằng bản rỗng.
  Launcher phải chạy với **cwd = vendor/wyoming-vietnamese** (repo không cài thành package).
- Lệnh chạy:
  ```
  cd vendor/wyoming-vietnamese
  set CACHE_DIR=<repo>/data/wyoming/cache
  set DOWNLOAD_DIR=<repo>/data/wyoming/models
  set WYOMING_PORT=10300
  set PYTHONIOENCODING=utf-8
  .venv/Scripts/python.exe ../../backend/tts_stt_tool/stt/wyoming_win_launcher.py
  ```
  Thiếu `PYTHONIOENCODING=utf-8` thì log tên giọng tiếng Việt sinh "Logging error" (không làm dừng server).
- Lần đầu tải model STT `hynt/Zipformer-30M-RNNT-6000h` + giọng NghiTTS từ Hugging Face (~40 s).
- **`piper_phonemize` (phần TTS của wyoming) bị Application Control chặn DLL.** Server luôn khởi tạo
  TTS, nên launcher thay `piper_phonemize` bằng stub khi import lỗi. Chỉ dùng STT của wyoming;
  TTS của wyoming coi như tắt.
- Server sẵn sàng sau ~5 s (khi model đã có): log `Wyoming STT/TTS service is ready at tcp://0.0.0.0:10300`.

### Giao thức (đã kiểm chứng)

- `Describe` → `Info.asr[0]`: name `wyoming_vietnamese`, model `hynt/Zipformer-30M-RNNT-6000h`, ngôn ngữ `vi`.
- Nhận dạng: `Transcribe(language="vi")` → `AudioStart(rate=16000, width=2, channels=1)` →
  `AudioChunk` (PCM16 LE, mỗi chunk 2048 byte) → `AudioStop` → đọc tới `Transcript`.
  Audio VieNeu 48 kHz float32 → `soxr.resample(..., 48000, 16000)` → int16.
- Kết quả thử: "Bật đồng bộ nhiệt độ" → `bật đồng bộ nhiệt độ` (0.13 s);
  "Chỉnh nhiệt độ ghế lái lên hai mươi tư độ" → `chỉnh nhiệt độ ghế lái lên hai mươi tư độ` (0.17 s).
  STT trả chữ thường, không dấu câu, số đọc thành chữ.

## VieNeu-TTS

- `uv add vieneu` (3.8.5). Không cài torch: v3turbo chạy CPU qua ONNX Runtime.
- `Vieneu(mode="v3turbo")`: lần đầu tải model ~165 s, các lần sau nạp ~9 s.
- Sample rate **48000**, đầu ra `numpy.float32` mono.
- `infer(text, voice=<tên>, temperature=0.8, top_k=25, top_p=0.95, ...)` — lấy mẫu ngẫu nhiên, nên
  mỗi lần gọi ra audio khác nhau. **Sinh lại (attempt > 0):** đặt seed `numpy`/`random` = attempt và
  giảm `temperature` dần: `temperature = max(0.4, 0.8 - 0.1*attempt)`.
- `list_preset_voices()` → 25 tuple `(nhãn, id)`, ví dụ `('⭐ Ngọc Huyền — Nữ · Bắc · Giọng đọc tự nhiên', 'Ngọc Huyền')`.
  Giọng mặc định đề xuất: **"Ngọc Huyền"** (Nữ · Bắc), vì gần như toàn bộ testcase là BAC-HN.
- CPU (máy dev): câu ~1.3–2 s audio mất ~1.1 s (lần đầu ~3.6 s khởi động). ~4.000 câu ≈ 1–2 giờ.
