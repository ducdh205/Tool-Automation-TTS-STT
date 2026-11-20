import type { ProgressEvent } from "./api";

export type EventClass = "block1-item" | "app-item" | "log" | "progress" | "terminal";

export function classifyEvent(e: ProgressEvent): EventClass {
  if (e.kind === "item") return e.item && "app_run_id" in (e.item as object) ? "app-item" : "block1-item";
  if (e.kind === "log") return "log";
  if (e.kind === "progress") return "progress";
  return "terminal";
}
