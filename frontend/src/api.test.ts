import { api } from "./api";

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
