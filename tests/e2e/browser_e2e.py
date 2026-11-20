"""Browser end-to-end run (real server, real phone) driven through the UI with Microsoft Edge.

Prerequisites: `uv run python -m tts_stt_tool --no-browser` running, phone connected with the
app on its home screen, PC speakers on. Run:

    uv run python tests/e2e/browser_e2e.py [--items 5] [--sheet "ONOFFTemperature Synchronizatio"]

Screenshots and the Excel report land in data/e2e/.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "e2e"
BASE = "http://127.0.0.1:8765"  # overridden by --base


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print(f"  screenshot {name}.png")


def wait_job_end(page: Page, timeout_s: float) -> None:
    t = time.time()
    while time.time() - t < timeout_s:
        if page.request.get(f"{BASE}/api/jobs/current").json() is None:
            return
        page.wait_for_timeout(1000)
    raise TimeoutError("job did not finish")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=5)
    ap.add_argument("--sheet", default="ONOFFTemperature Synchronizatio")
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    globals()["BASE"] = args.base.rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, accept_downloads=True)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("1. open UI")
        page.goto(BASE)
        page.get_by_text("TTS → STT").wait_for()
        for _ in range(60):
            if page.request.get(f"{BASE}/api/health").json()["wyoming"]:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(2500)  # device mirror loads
        shot(page, "01_open")

        print("2. import file, pick one sheet")
        page.get_by_role("button", name="Nạp file").first.click()
        page.locator("input[type=file]").set_input_files(str(REPO / "public" / "DieuKhienXe_Pre.xlsx"))
        sheet_row = page.locator(".modal .sheet-item", has_text=args.sheet)
        sheet_row.wait_for(timeout=30000)
        sheet_row.locator("input").check()
        name = f"E2E trình duyệt {time.strftime('%H%M%S')}"
        page.locator(".modal .field input").fill(name)
        shot(page, "02_import_dialog")
        page.get_by_role("button", name="Tạo bộ audio").click()
        page.get_by_role("heading", name=name).wait_for()
        set_id = max(s["id"] for s in page.request.get(f"{BASE}/api/audio-sets").json())

        print(f"3. keep {args.items} sentences (set {set_id})")
        items = page.request.get(f"{BASE}/api/audio-sets/{set_id}/items").json()
        pending = [i for i in items if i["status"] == "Chờ"]
        for i in pending[args.items:]:
            page.request.patch(f"{BASE}/api/items/{i['id']}", data={"enabled": False})
        page.reload()
        page.get_by_role("heading", name=name).wait_for()
        shot(page, "03_table")

        print("4. block 1: generate + verify")
        page.get_by_role("button", name="Sinh audio + Verify").click()
        page.wait_for_timeout(1500)
        shot(page, "04_block1_running")
        wait_job_end(page, 600)
        page.wait_for_timeout(1500)
        shot(page, "05_block1_done")
        summary = page.request.get(f"{BASE}/api/audio-sets/{set_id}/summary").json()
        print("   block1 summary:", summary)

        print("5. block 2: run on the phone")
        page.get_by_role("button", name="Test app").click()
        page.get_by_role("button", name="Chạy trên app").wait_for()
        shot(page, "06_app_panel")
        page.get_by_role("button", name="Chạy trên app").click()
        page.wait_for_timeout(9000)
        shot(page, "07_app_running")
        wait_job_end(page, 60 * args.items + 120)
        page.wait_for_timeout(2000)
        shot(page, "08_app_done")
        run = page.request.get(f"{BASE}/api/audio-sets/{set_id}/app-runs").json()[0]
        print("   app run:", run["id"], run["summary"])
        for r in page.request.get(f"{BASE}/api/app-runs/{run['id']}/results").json():
            print(f"   {r['status']:<13} | {r['text_tts']} | app: {r['app_text']} | {r['error'] or ''}")

        print("6. export Excel (with block 2)")
        with page.expect_download() as dl:
            page.get_by_role("button", name="Xuất Excel", exact=True).click()
        dest = OUT / dl.value.suggested_filename
        dl.value.save_as(dest)
        print("   report:", dest.name)

        browser.close()
        if errors:
            print("PAGE ERRORS:", *errors, sep="\n  ")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
