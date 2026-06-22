"""DeviceController — dedicated abstraction over the iMouseXP Python SDK (imouse_xp)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from imouse_farm.config.models import IMouseConfig
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeviceStatus:
    """Normalized device status from the iMouseXP SDK."""

    device_id: str
    device_name: str = ""  # custom alias from iMouse (often empty)
    phone_name: str = ""  # hardware name e.g. iPhone 7
    user_name: str = ""  # farm slot label e.g. 9, 8, 7
    model: str = ""
    ios_version: str = ""
    screen_width: int = 0
    screen_height: int = 0
    is_connected: bool = False
    is_online: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def display_label(self) -> str:
        """Human-friendly label combining slot number and phone model."""
        parts: list[str] = []
        if self.user_name:
            parts.append(f"Phone {self.user_name}")
        if self.phone_name:
            parts.append(self.phone_name)
        elif self.device_name and self.device_name != self.device_id:
            parts.append(self.device_name)
        if self.device_name and self.phone_name and self.device_name != self.phone_name:
            parts.append(f"({self.device_name})")
        return " · ".join(parts) if parts else self.device_id


class DeviceController:
    """Primary communication layer using the official ``imouse_xp`` package."""

    def __init__(self, config: IMouseConfig) -> None:
        self._config = config
        self._api: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._api is not None and self._api.is_connected()

    async def connect(self) -> None:
        await self._run_sync(self._connect_sync)
        self._connected = True
        logger.info("sdk_connected", host=self._config.host, port=9911)

    def _connect_sync(self) -> None:
        from imouse_xp.api import IMouseApi

        self._api = IMouseApi(host=self._config.host, timeout=30)
        self._api.start()

    async def disconnect(self) -> None:
        if self._api:
            await self._run_sync(self._api.stop)
        self._api = None
        self._connected = False
        logger.info("sdk_disconnected")

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    async def _run_sync(self, func: Any) -> Any:
        return await asyncio.to_thread(func)

    @staticmethod
    def _ok(response: Any) -> bool:
        if response is None:
            return False
        try:
            from imouse_xp.api import is_success
            return bool(is_success(response))
        except Exception:
            return getattr(getattr(response, "data", None), "code", -1) == 0

    @staticmethod
    def _error_message(response: Any) -> str:
        if response is None:
            return "No response from iMouse"
        data = getattr(response, "data", None)
        if data is not None:
            msg = getattr(data, "message", None)
            if msg:
                return str(msg)
        msg = getattr(response, "message", None)
        return str(msg) if msg else "iMouse request failed"

    def _ids(self, device_id: str) -> list[str]:
        return [device_id]

    def _normalize_device(self, raw: Any) -> DeviceStatus | None:
        if hasattr(raw, "model_dump"):
            data = raw.model_dump()
        elif isinstance(raw, dict):
            data = raw
        else:
            return None

        device_id = data.get("deviceid") or data.get("device_id") or data.get("id") or ""
        if not device_id:
            return None

        width = data.get("width") or data.get("imgw") or 0
        height = data.get("height") or data.get("imgh") or 0

        return DeviceStatus(
            device_id=device_id,
            device_name=data.get("name", ""),
            phone_name=data.get("device_name", ""),
            user_name=str(data.get("user_name", "") or ""),
            model=data.get("model", ""),
            ios_version=data.get("version", ""),
            screen_width=int(width or 0),
            screen_height=int(height or 0),
            is_connected=True,
            is_online=int(data.get("state", 0) or 0) == 1,
            raw=data,
        )

    async def enumerate_devices(self) -> list[DeviceStatus]:
        raw_list = await self._run_sync(self._enumerate_sync)
        devices: list[DeviceStatus] = []
        for raw in raw_list:
            status = self._normalize_device(raw)
            if status:
                devices.append(status)
        logger.info("devices_enumerated", count=len(devices))
        return devices

    def _enumerate_sync(self) -> list[Any]:
        if self._api is None:
            return []
        try:
            response = self._api.device_get()
            if response and self._ok(response):
                return list(response.data.list)
        except Exception as exc:
            logger.warning("device_enumeration_failed", error=str(exc))
        return []

    async def connect_device(self, device_id: str) -> bool:
        def _connect() -> bool:
            try:
                return self._ok(self._api.device_airplay_connect(self._ids(device_id)))
            except Exception as exc:
                logger.warning("device_connect_failed", device_id=device_id, error=str(exc))
                return False
        return await self._run_sync(_connect)

    async def disconnect_device(self, device_id: str) -> bool:
        def _disconnect() -> bool:
            try:
                return self._ok(self._api.device_airplay_disconnect(self._ids(device_id)))
            except Exception as exc:
                logger.warning("device_disconnect_failed", device_id=device_id, error=str(exc))
                return False
        return await self._run_sync(_disconnect)

    async def connect_all_airplay(self) -> bool:
        def _connect_all() -> bool:
            try:
                return self._ok(self._api.device_airplay_connect_all())
            except Exception as exc:
                logger.warning("airplay_connect_all_failed", error=str(exc))
                return False

        logger.info("airplay_connect_all")
        return await self._run_sync(_connect_all)

    async def get_status(self, device_id: str) -> DeviceStatus | None:
        for device in await self.enumerate_devices():
            if device.device_id == device_id:
                return device
        return None

    @staticmethod
    def _decode_image_field(image: str) -> bytes | None:
        if not image:
            return None
        path = Path(image)
        if path.is_file():
            return path.read_bytes()
        payload = image.split(",", 1)[1] if image.startswith("data:") else image
        try:
            return base64.b64decode(payload, validate=False)
        except Exception:
            return None

    def _ensure_airplay_sync(self, device_id: str) -> None:
        try:
            response = self._api.device_get()
            if not response or not self._ok(response):
                return
            for device in response.data.list:
                if device.deviceid != device_id:
                    continue
                if int(getattr(device, "state", 0) or 0) != 1 or not getattr(device, "air_handle", 0):
                    logger.info("airplay_connect_before_screenshot", device_id=device_id)
                    self._api.device_airplay_connect(self._ids(device_id))
                    time.sleep(2)
                return
        except Exception as exc:
            logger.warning("airplay_precheck_failed", device_id=device_id, error=str(exc))

    async def capture_screenshot(self, device_id: str) -> bytes | None:
        def _capture() -> bytes | None:
            self._ensure_airplay_sync(device_id)

            result = self._api.pic_screenshot(device_id, binary=True)
            if isinstance(result, bytes) and len(result) > 0:
                logger.info("screenshot_captured", device_id=device_id, bytes=len(result))
                return result

            result = self._api.pic_screenshot(device_id, binary=False)
            if result and self._ok(result):
                image = getattr(result.data, "image", None) or getattr(result.data, "img", None)
                decoded = self._decode_image_field(image) if isinstance(image, str) else None
                if decoded:
                    logger.info("screenshot_captured", device_id=device_id, bytes=len(decoded), source="base64")
                    return decoded

            message = ""
            code = -1
            if result and getattr(result, "data", None):
                message = getattr(result.data, "message", "") or ""
                code = getattr(result.data, "code", -1)
            logger.warning("screenshot_failed", device_id=device_id, code=code, message=message)
            return None

        return await self._run_sync(_capture)

    async def tap(self, device_id: str, x: int, y: int) -> bool:
        logger.info("action_tap", device_id=device_id, x=x, y=y)
        return await self._run_sync(
            lambda: self._ok(self._api.mouse_click(self._ids(device_id), x, y))
        )

    async def swipe(
        self,
        device_id: str,
        *,
        direction: str = "up",
        length: float = 0.9,
        sx: int | None = None,
        sy: int | None = None,
        ex: int | None = None,
        ey: int | None = None,
    ) -> bool:
        def _swipe() -> bool:
            ids = self._ids(device_id)
            if None not in (sx, sy, ex, ey):
                return self._ok(
                    self._api.mouse_swipe(ids, direction, sx=sx, sy=sy, ex=ex, ey=ey)
                )
            return self._ok(self._api.mouse_swipe(ids, direction, len=length))

        logger.info(
            "action_swipe",
            device_id=device_id,
            direction=direction,
            sx=sx,
            sy=sy,
            ex=ex,
            ey=ey,
        )
        return await self._run_sync(_swipe)

    async def long_press(self, device_id: str, x: int, y: int, duration_ms: int = 1000) -> bool:
        logger.info("action_long_press", device_id=device_id, x=x, y=y)
        return await self._run_sync(
            lambda: self._ok(
                self._api.mouse_click(self._ids(device_id), x, y, time=duration_ms)
            )
        )

    async def send_text(self, device_id: str, text: str) -> bool:
        logger.info("action_text_input", device_id=device_id, length=len(text))
        return await self._run_sync(
            lambda: self._ok(self._api.key_sendkey(self._ids(device_id), key=text))
        )

    async def send_fn_key(self, device_id: str, fn_key: str) -> bool:
        logger.info("action_fn_key", device_id=device_id, fn_key=fn_key)
        return await self._run_sync(
            lambda: self._ok(self._api.key_sendkey(self._ids(device_id), fn_key=fn_key))
        )

    async def send_key(self, device_id: str, key: str) -> bool:
        logger.info("action_key", device_id=device_id, key=key)
        return await self._run_sync(
            lambda: self._ok(self._api.key_sendkey(self._ids(device_id), key=key))
        )

    async def clear_text_field(self, device_id: str) -> bool:
        """Select all text in the focused field, then delete (Spotlight / search)."""
        for fn_key in ("selectall", "selectAll"):
            if await self.send_fn_key(device_id, fn_key):
                break
        else:
            await self.send_key(device_id, "ctrl+a")
        for fn_key in ("delete", "backspace", "del"):
            if await self.send_fn_key(device_id, fn_key):
                return True
        return await self.send_key(device_id, "\b")

    async def press_home(self, device_id: str) -> bool:
        def _home() -> bool:
            response = self._api.key_sendkey(self._ids(device_id), fn_key="home")
            if self._ok(response):
                return True
            logger.error(
                "home_failed",
                device_id=device_id,
                message=self._error_message(response),
            )
            return False

        logger.info("action_home", device_id=device_id)
        return await self._run_sync(_home)

    async def press_lock(self, device_id: str) -> bool:
        logger.info("action_lock", device_id=device_id)
        return await self._run_sync(
            lambda: self._ok(self._api.key_sendkey(self._ids(device_id), fn_key="lock"))
        )

    async def press_unlock(self, device_id: str) -> bool:
        logger.info("action_unlock", device_id=device_id)
        return await self._run_sync(
            lambda: self._ok(self._api.key_sendkey(self._ids(device_id), fn_key="unlock"))
        )

    async def launch_app(self, device_id: str, app_name: str) -> bool:
        logger.info("action_launch_app", device_id=device_id, app=app_name)
        url = app_name if "://" in app_name else f"{app_name}://"
        return await self._run_sync(
            lambda: self._ok(self._api.shortcut_exec_url(self._ids(device_id), url=url))
        )

    async def close_app(self, device_id: str) -> bool:
        logger.info("action_close_app", device_id=device_id)
        return await self.press_home(device_id)

    def _album_list_sync(
        self,
        device_id: str,
        album_name: str | None = None,
        *,
        num: int = 60,
    ) -> list[dict[str, str]]:
        """Return items in the album as {album_name, name, ext} dicts."""
        response = self._api.shortcut_album_get(
            device_id,
            album_name=album_name or "",
            num=num,
            outtime=60000,
        )
        if not self._ok(response):
            return []
        return [
            {"album_name": item.album_name, "name": item.name, "ext": item.ext}
            for item in (getattr(response.data, "list", None) or [])
        ]

    async def album_list(
        self,
        device_id: str,
        album_name: str | None = None,
        *,
        num: int = 60,
    ) -> list[dict[str, str]]:
        return await self._run_sync(
            lambda: self._album_list_sync(device_id, album_name=album_name, num=num)
        )

    async def album_clear(
        self,
        device_id: str,
        album_name: str | None = None,
        timeout_ms: int = 120000,
        *,
        post_grace_seconds: float = 45.0,
    ) -> bool:
        """Clear the album via shortcut_album_clear, tapping the iOS delete dialog.

        The "Delete N Items" confirmation typically appears AFTER the
        shortcut_album_clear call returns, so we keep scanning and tapping
        Delete for a grace window once the API completes (and also during it).

        Note: we deliberately do NOT pre-check with album_get — the shortcut's
        get can report 0 items even when the library is full, which would skip
        the clear entirely.
        """
        from imouse_farm.actions.permission_prompts import DELETE_CONFIRM_TEXTS

        label = album_name or "recents"
        error_message = ""
        stop = asyncio.Event()
        tap_count = 0

        def _clear() -> bool:
            nonlocal error_message
            response = self._api.shortcut_album_clear(
                self._ids(device_id), album_name=album_name, outtime=timeout_ms
            )
            if self._ok(response):
                return True
            error_message = self._error_message(response)
            logger.error("album_clear_failed", device_id=device_id, album=label, message=error_message)
            return False

        # "Delete" is a partial match, so it also hits the negative button
        # ("Don't Delete" / "Cancel" / "Keep"). Never tap those.
        negative_words = ("don't", "dont", "cancel", "keep", "stop", "not now")

        async def _tap_delete_once() -> bool:
            """Scan the live screen for the affirmative Delete button and tap it once."""
            matches = await self.find_text_on_device(device_id, list(DELETE_CONFIRM_TEXTS))
            candidates = [
                m
                for m in matches
                if not any(neg in str(m.get("text", "")).lower() for neg in negative_words)
            ]
            if not candidates:
                if matches:
                    logger.info(
                        "album_clear_skip_negative",
                        device_id=device_id,
                        texts=[m.get("text", "") for m in matches],
                    )
                return False
            best = max(candidates, key=lambda m: m.get("confidence", 0))
            await self.tap(device_id, int(best["x"]), int(best["y"]))
            logger.info(
                "album_clear_delete_tap",
                device_id=device_id,
                text=best.get("text", ""),
                x=int(best["x"]),
                y=int(best["y"]),
            )
            return True

        async def _watch_and_tap() -> None:
            """Constantly look for the Delete confirmation and tap it, for the whole run."""
            nonlocal tap_count
            while not stop.is_set():
                if await _tap_delete_once():
                    tap_count += 1
                    # Let the popup dismiss so the next scan doesn't tap empty space.
                    await asyncio.sleep(1.5)
                else:
                    await asyncio.sleep(0.4)

        logger.info("album_clear", device_id=device_id, album=label)
        watcher = asyncio.create_task(_watch_and_tap())
        try:
            ok = await self._run_sync(_clear)
            if not ok:
                raise RuntimeError(error_message or "album clear failed")
            # The popup commonly appears AFTER the API returns (and may reappear
            # in batches), so keep the watcher scanning for a grace window.
            await asyncio.sleep(post_grace_seconds)
        finally:
            stop.set()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

        logger.info("album_clear_done", device_id=device_id, album=label, delete_taps=tap_count)
        return True

    async def album_upload(
        self,
        device_id: str,
        files: list[str],
        album_name: str | None = None,
        timeout_ms: int = 300000,
        zip_files: bool = False,
    ) -> bool:
        abs_files = [str(Path(f).resolve()) for f in files]

        def _upload() -> bool:
            response = self._api.shortcut_album_upload(
                self._ids(device_id),
                files=abs_files,
                album_name=album_name,
                zip=1 if zip_files else 0,
                outtime=timeout_ms,
            )
            if not self._ok(response):
                message = self._error_message(response)
                logger.error(
                    "album_upload_failed",
                    device_id=device_id,
                    message=message,
                    files=abs_files,
                )
                raise RuntimeError(message)
            return True

        logger.info("album_upload", device_id=device_id, file_count=len(abs_files))
        return await self._run_sync(_upload)

    async def find_image_on_device(
        self, device_id: str, template_base64: str, threshold: float = 0.8
    ) -> list[dict[str, Any]]:
        def _find() -> list[dict[str, Any]]:
            response = self._api.pic_find_image_cv(
                device_id, [template_base64], similarity=threshold
            )
            if not response or not self._ok(response):
                return []
            matches: list[dict[str, Any]] = []
            for item in getattr(response.data, "list", []) or []:
                centre = getattr(item, "centre", [0, 0])
                matches.append({
                    "x": centre[0] if len(centre) > 0 else 0,
                    "y": centre[1] if len(centre) > 1 else 0,
                    "confidence": float(getattr(item, "similarity", threshold)),
                })
            return matches
        return await self._run_sync(_find)

    async def find_template_on_device(
        self,
        device_id: str,
        template_path: Path,
        threshold: float = 0.42,
    ) -> dict[str, Any] | None:
        import base64

        if not template_path.is_file():
            logger.warning("template_file_missing", path=str(template_path))
            return None
        path_str = str(template_path.resolve())
        matches = await self.find_image_on_device(device_id, path_str, threshold)
        if not matches:
            b64 = base64.b64encode(template_path.read_bytes()).decode()
            matches = await self.find_image_on_device(device_id, b64, threshold)
        if not matches:
            return None
        return max(matches, key=lambda m: m["confidence"])

    async def find_text_on_device(
        self,
        device_id: str,
        texts: list[str],
        *,
        threshold: float = 0.75,
        contain: bool = True,
    ) -> list[dict[str, Any]]:
        def _find() -> list[dict[str, Any]]:
            response = self._api.pic_find_text(
                device_id, texts, similarity=threshold, contain=contain
            )
            if not response or not self._ok(response):
                return []
            matches: list[dict[str, Any]] = []
            for item in getattr(response.data, "list", []) or []:
                centre = getattr(item, "centre", [0, 0])
                matches.append({
                    "text": getattr(item, "text", ""),
                    "x": centre[0] if len(centre) > 0 else 0,
                    "y": centre[1] if len(centre) > 1 else 0,
                    "confidence": float(getattr(item, "similarity", threshold)),
                })
            return matches

        return await self._run_sync(_find)

    async def ocr_on_device(self, device_id: str) -> str:
        def _ocr() -> str:
            response = self._api.pic_ocr(device_id)
            if not response or not self._ok(response):
                return ""
            items = getattr(response.data, "list", []) or []
            return " ".join(getattr(i, "text", str(i)) for i in items)
        return await self._run_sync(_ocr)
