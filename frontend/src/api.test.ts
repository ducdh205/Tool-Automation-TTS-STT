import { api, downloadFile } from "./api";

afterEach(() => vi.restoreAllMocks());

test("session zip: POST builds it, then the browser follows a plain link (no in-page blob)", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ download_url: "/api/exports/abc" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const hrefs: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    hrefs.push(this.getAttribute("href") ?? "");
  });
  const blob = vi.spyOn(Response.prototype, "blob");

  await api.downloadSessionZip(7, "selected", [1, 2]);

  expect(fetchMock).toHaveBeenCalledWith("/api/app-runs/7/export-zip", expect.objectContaining({
    method: "POST", body: JSON.stringify({ audio: "selected", item_ids: [1, 2] }),
  }));
  expect(hrefs).toEqual(["/api/exports/abc"]);
  expect(blob).not.toHaveBeenCalled();
});

test("deleteSet sends DELETE for the audio set", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);

  await api.deleteSet(4);

  expect(fetchMock).toHaveBeenCalledWith("/api/audio-sets/4", expect.objectContaining({ method: "DELETE" }));
});

test("clearAllData sends DELETE /api/data", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true, sets: 2 }), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);

  expect(await api.clearAllData()).toEqual({ ok: true, sets: 2 });

  expect(fetchMock).toHaveBeenCalledWith("/api/data", expect.objectContaining({ method: "DELETE" }));
});

const reply = (status: number, body: string, type = "application/json") =>
  vi.fn().mockImplementation(async () => new Response(body, { status, headers: { "Content-Type": type } }));

test("a failed request throws ApiError with the server's detail and status", async () => {
  vi.stubGlobal("fetch", reply(409, JSON.stringify({ detail: "Đang chạy: Khối 2" })));
  await expect(api.deleteSet(4)).rejects.toMatchObject({ message: "Đang chạy: Khối 2", status: 409 });
});

test("a failed request without a JSON detail falls back to the status code", async () => {
  vi.stubGlobal("fetch", reply(502, "Bad Gateway", "text/plain"));
  await expect(api.deleteSet(4)).rejects.toMatchObject({ message: "502", status: 502 });
});

test("a failed file export says so, and still prefers the server's detail", async () => {
  vi.stubGlobal("fetch", reply(500, "boom", "text/plain"));
  await expect(downloadFile("/api/x", { a: 1 }, "f.xlsx")).rejects.toMatchObject({ message: "Xuất file lỗi (500)", status: 500 });
  vi.stubGlobal("fetch", reply(404, JSON.stringify({ detail: "Không tìm thấy lần test app" })));
  await expect(downloadFile("/api/x", undefined, "f.xlsx")).rejects.toMatchObject({ message: "Không tìm thấy lần test app" });
});

test("JSON and FormData bodies are sent as before", async () => {
  const fetchMock = reply(200, JSON.stringify({ ok: true }));
  vi.stubGlobal("fetch", fetchMock);
  await api.saveSettings({ voice: "v" } as never);
  expect(fetchMock).toHaveBeenLastCalledWith("/api/settings", {
    method: "PUT", body: JSON.stringify({ voice: "v" }), headers: { "Content-Type": "application/json" },
  });
  await api.deleteSet(4);
  expect(fetchMock).toHaveBeenLastCalledWith("/api/audio-sets/4", { method: "DELETE" });
});
