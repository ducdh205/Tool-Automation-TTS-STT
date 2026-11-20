"""Browser check of pin mode: tap the mic on the mirrored screen -> its label shows (phone is not tapped)."""

import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    page = b.new_page(viewport={"width": 1600, "height": 900})
    page.goto(BASE)
    img = page.locator("img.phone-img")
    img.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Ghim nút cho hồ sơ app").click()
    box = img.bounding_box()
    nat = img.evaluate("i => [i.naturalWidth, i.naturalHeight]")
    # image is object-fit: contain -> compute where device pixel (360, 1471) is drawn
    scale = min(box["width"] / nat[0], box["height"] / nat[1])
    ox = box["x"] + (box["width"] - nat[0] * scale) / 2
    oy = box["y"] + (box["height"] - nat[1] * scale) / 2
    page.mouse.click(ox + 360 * scale, oy + 1471 * scale)
    result = page.locator(".pin-result b")
    result.wait_for(timeout=20000)
    label = result.inner_text()
    page.screenshot(path="data/e2e/09_pin_mode.png")
    print("pinned label:", label)
    b.close()
    sys.exit(0 if label == "Nói để tạo việc" else 1)
