import { jobAfterStart, jobFromServer } from "./jobState";

describe("job state (review #6)", () => {
  it("ignores a start response that arrives after the job already finished", () => {
    const finished = new Set(["abc"]);
    expect(jobAfterStart("abc", finished)).toBeNull();
  });
  it("tracks a freshly started job", () => {
    expect(jobAfterStart("xyz", new Set())).toEqual({ id: "xyz", name: "Khối 1", done: 0, total: 0 });
  });
  it("server state wins over a stale local job", () => {
    const local = { id: "old", name: "Khối 1", done: 3, total: 10 };
    expect(jobFromServer(local, null)).toBeNull();
    const server = { id: "new", name: "Khối 1", done: 5, total: 9 };
    expect(jobFromServer(local, server)).toEqual(server);
  });
  it("keeps local progress when server reports the same job behind", () => {
    const local = { id: "j", name: "Khối 1", done: 7, total: 10 };
    expect(jobFromServer(local, { id: "j", name: "Khối 1", done: 6, total: 10 })).toEqual(local);
  });
});
