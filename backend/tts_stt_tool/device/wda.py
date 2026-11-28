"""Minimal WebDriverAgent (iOS) HTTP client — the iOS counterpart of ``adb.py``.

WDA runs on the iPhone (``pymobiledevice3 developer dvt xcuitest …``) and is forwarded to
``http://127.0.0.1:8100`` (``go-ios forward 8100 8100``). Coordinates are in points.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

DEFAULT_WDA_URL = "http://127.0.0.1:8100"


class WdaError(RuntimeError):
    pass


def _error_of(body: Any) -> str | None:
    if isinstance(body, dict):
        v = body.get("value")
        if isinstance(v, dict) and v.get("error"):
            return f"{v.get('error')}: {v.get('message') or ''}".strip(": ")
    return None


class WdaClient:
    def __init__(self, base_url: str = DEFAULT_WDA_URL, timeout_s: float = 30.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s, transport=transport)
        self._session: str | None = None
        self._session_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _json(self, method: str, path: str, body: dict | None = None) -> dict:
        """The whole JSON reply (``{"value": …, "sessionId": …}``); WDA errors raise ``WdaError``."""
        try:
            r = await self._http.request(method, path, json=body)
        except httpx.HTTPError as e:
            raise WdaError(f"Không kết nối được WebDriverAgent ({self.base_url}): {e or type(e).__name__}") from e
        try:
            data = r.json()
        except ValueError:
            data = None
        err = _error_of(data)
        if r.status_code >= 400 or err:
            raise WdaError(err or f"WDA {method} {path}: HTTP {r.status_code}")
        return data if isinstance(data, dict) else {}

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        return (await self._json(method, path, body)).get("value")

    async def status(self) -> dict:
        return await self._request("GET", "/status") or {}

    async def ready(self) -> bool:
        try:
            return bool((await self.status()).get("ready"))
        except WdaError:
            return False

    # -- session ------------------------------------------------------------------
    async def session_id(self) -> str:
        """Reuse WDA's current session (one per WDA run), else create one."""
        async with self._session_lock:
            if self._session is None:
                sid = (await self._json("GET", "/status")).get("sessionId")
                if not sid:
                    created = await self._json("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
                    sid = created.get("sessionId") or (created.get("value") or {}).get("sessionId")
                if not sid:
                    raise WdaError("WebDriverAgent không tạo được session")
                self._session = sid
            return self._session

    async def _session_call(self, method: str, path: str, body: dict | None = None) -> Any:
        """``/session/<id><path>``; a stale session (WDA restarted) is recreated once."""
        sid = await self.session_id()
        try:
            return await self._request(method, f"/session/{sid}{path}", body)
        except WdaError as e:
            if "session" not in str(e).lower():
                raise
            self._session = None
            sid = await self.session_id()
            return await self._request(method, f"/session/{sid}{path}", body)

    # -- reading ------------------------------------------------------------------
    async def source(self) -> str:
        xml = await self._request("GET", "/source")
        if not isinstance(xml, str) or "<" not in xml:
            raise WdaError("WDA /source không trả về XML")
        return xml

    async def screenshot(self) -> bytes:
        png = base64.b64decode(await self._request("GET", "/screenshot") or "")
        if not png.startswith(b"\x89PNG"):
            raise WdaError("WDA /screenshot không trả về ảnh PNG")
        return png

    async def window_size(self) -> tuple[int, int]:
        v = await self._session_call("GET", "/window/size")
        return int(v["width"]), int(v["height"])

    # -- acting -------------------------------------------------------------------
    async def tap(self, x: float, y: float) -> None:
        await self._session_call("POST", "/wda/tap", {"x": x, "y": y})

    async def drag(self, x1: float, y1: float, x2: float, y2: float, duration_s: float = 0.3) -> None:
        await self._session_call("POST", "/wda/dragfromtoforduration",
                                 {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": duration_s})

    async def press_button(self, name: str) -> None:
        """``home`` | ``volumeUp`` | ``volumeDown``."""
        await self._session_call("POST", "/wda/pressButton", {"name": name})

    async def keys(self, text: str) -> None:
        """Type into the focused field (Unicode, so Vietnamese diacritics work)."""
        await self._session_call("POST", "/wda/keys", {"value": list(text)})

    async def home(self) -> None:
        await self._request("POST", "/wda/homescreen")

    async def launch(self, bundle_id: str) -> None:
        await self._session_call("POST", "/wda/apps/launch", {"bundleId": bundle_id})
