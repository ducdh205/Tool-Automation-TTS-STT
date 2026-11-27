import type { Job } from "./api";
import { blockReason, jobAfterStart, jobsFromServer, laneBlocker, progressJob, removeJob, upsertJob } from "./jobState";

const j = (over: Partial<Job>): Job => ({ id: "j", name: "x", done: 0, total: 0, lane: "block1", set_id: 1, ...over });

describe("job state (review #6)", () => {
  it("ignores a start response that arrives after the job already finished", () => {
    expect(jobAfterStart("abc", new Set(["abc"]))).toBeNull();
  });
  it("tracks a freshly started job with its lane and set", () => {
    expect(jobAfterStart("xyz", new Set(), "block2", 4))
      .toEqual({ id: "xyz", name: "Khối 2", done: 0, total: 0, lane: "block2", set_id: 4, exclusive: false });
  });
  it("server state wins over a stale local job", () => {
    expect(jobsFromServer([j({ id: "old", done: 3 })], [])).toEqual([]);
    const server = j({ id: "new", done: 5, total: 9 });
    expect(jobsFromServer([j({ id: "old", done: 3 })], [server])).toEqual([server]);
  });
  it("keeps local progress when server reports the same job behind", () => {
    const local = j({ done: 7, total: 10, name: "Khối 1" });
    const server = j({ done: 6, total: 10, name: "Sinh audio – bộ 1" });
    expect(jobsFromServer([local], [server])).toEqual([{ ...server, done: 7 }]);
  });
  it("upserts, removes and tracks progress per job id", () => {
    let js = upsertJob([], j({ id: "a" }));
    js = upsertJob(js, j({ id: "b", lane: "block2" }));
    js = upsertJob(js, null);
    js = progressJob(js, { job_id: "b", kind: "progress", done: 2, total: 5, item: null, message: null });
    expect(js.map((x) => [x.id, x.done])).toEqual([["a", 0], ["b", 2]]);
    js = progressJob(js, { job_id: "c", kind: "progress", done: 1, total: 3, item: null, message: null, lane: "block2" });
    expect(js.find((x) => x.id === "c")?.lane).toBe("block2");
    expect(removeJob(js, "a").map((x) => x.id)).toEqual(["b", "c"]);
  });
});

describe("lane locks", () => {
  const app = j({ id: "app", lane: "block2", set_id: 1, name: "Khối 2 – lần test 3" });
  it("Block 1 on another set is free while Block 2 runs", () => {
    expect(laneBlocker([app], "block1", 2)).toBeNull();
  });
  it("on the same set only Sinh lại (exclusive) clashes, with a reason that says so", () => {
    expect(laneBlocker([app], "block1", 1)).toBeNull();
    expect(laneBlocker([app], "block1", 1, true)).toBe(app);
    expect(blockReason(app, "block1")).toContain("cùng bộ audio");
    const regen = j({ id: "r", lane: "block1", set_id: 1, exclusive: true });
    expect(laneBlocker([regen], "block2", 1)).toBe(regen);
    expect(laneBlocker([j({ id: "g", lane: "block1", set_id: 1 })], "block2", 1)).toBeNull();
  });
  it("one job per lane, whatever the set", () => {
    expect(laneBlocker([app], "block2", 9)).toBe(app);
    expect(blockReason(app, "block2")).toBe("Đang chạy: Khối 2 – lần test 3");
    expect(blockReason(null, "block2")).toBeNull();
  });
});
