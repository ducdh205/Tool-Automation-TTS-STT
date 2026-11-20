import type { AppStatus } from "./api";

/** One color per verdict, shared by the filter chips and the table badges. */
export const STATUS_CLASS: Record<string, string> = {
  "Chờ": "st-pending", "Không áp dụng": "st-skip", "Đã sinh audio": "st-gen",
  "Đạt": "st-pass", "Audio không đạt": "st-fail", "Lỗi": "st-error",
  "Đúng": "st-pass", "Sai": "st-fail", "Lỗi thao tác": "st-error",
};

export const APP_STATUSES: AppStatus[] = ["Chờ", "Đúng", "Sai", "Lỗi thao tác"];

/** Share of the scored cases that came out right (null before anything was scored). */
export function passRate(ok: number, bad: number): number | null {
  return ok + bad ? ok / (ok + bad) : null;
}
