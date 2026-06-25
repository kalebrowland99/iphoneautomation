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

            if callable(is_success):
                return bool(is_success(response))
        except Exception:
            pass
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

    async def drag(
        self,
        device_id: str,
        x1: int,
        y1: int,
        *,
        x2: int | None = None,
        y2: int | None = None,
        direction: str | None = None,
        distance: int | None = None,
        duration_ms: int = 1000,
        move_ms: int = 10,
        hold_ms: int = 0,
    ) -> bool:
        """Press at (x1,y1), drag to end over move_ms, release after duration_ms total."""
        ex, ey = x2, y2
        if ex is None or ey is None:
            if not direction:
                raise ValueError("drag requires x2/y2 or direction")
            dist = int(distance if distance is not None else 172)
            match direction.lower():
                case "left":
                    ex, ey = x1 - dist, y1
                case "right":
                    ex, ey = x1 + dist, y1
                case "up":
                    ex, ey = x1, y1 - dist
                case "down":
                    ex, ey = x1, y1 + dist
                case _:
                    raise ValueError(f"unsupported drag direction: {direction}")

        def _drag() -> bool:
            ids = self._ids(device_id)
            if not self._ok(self._api.mouse_move(ids, x1, y1)):
                return False
            if not self._ok(self._api.mouse_down(ids)):
                return False
            down_at = time.monotonic()
            if hold_ms > 0:
                time.sleep(hold_ms / 1000.0)
            travel_ms = max(1, move_ms)
            if travel_ms <= 50:
                steps = 2
            else:
                steps = max(8, min(40, travel_ms // 25))
            step_delay = travel_ms / 1000.0 / steps if steps > 1 else 0
            for i in range(1, steps + 1):
                t = i / steps
                cx = int(round(x1 + (ex - x1) * t))
                cy = int(round(y1 + (ey - y1) * t))
                if not self._ok(self._api.mouse_move(ids, cx, cy)):
                    self._api.mouse_up(ids)
                    return False
                if i < steps and step_delay > 0:
                    time.sleep(step_delay)
            elapsed_ms = (time.monotonic() - down_at) * 1000
            remaining_ms = duration_ms - elapsed_ms
            if remaining_ms > 0:
                time.sleep(remaining_ms / 1000.0)
            self._api.mouse_up(ids)
            return True

        logger.info(
            "action_drag",
            device_id=device_id,
            x1=x1,
            y1=y1,
            x2=ex,
            y2=ey,
            direction=direction,
            distance=distance,
            duration_ms=duration_ms,
            move_ms=move_ms,
            hold_ms=hold_ms,
        )
        return await self._run_sync(_drag)

    async def long_press(self, device_id: str, x: int, y: int, duration_ms: int = 1000) -> bool:
        logger.info("action_long_press", device_id=device_id, x=x, y=y)
        return await self._run_sync(
            lambda: self._ok(
                self._api.mouse_click(self._ids(device_id), x, y, time=duration_ms)
            )
        )

    async def send_text(self, device_id: str, text: str, *, single_line: bool = False) -> bool:
        from imouse_farm.utils.text_input import (
            prepare_single_line_typing_segments,
            prepare_typing_segments,
        )

        if not self._api:
            raise RuntimeError("iMouse SDK not connected — cannot type text")

        if single_line:
            segments: list[str | None] = prepare_single_line_typing_segments(text)
        else:
            segments = prepare_typing_segments(text)
        logger.info(
            "action_text_input",
            device_id=device_id,
            length=len(text),
            segments=len(segments),
            single_line=single_line,
            multiline=any(seg is None for seg in segments),
        )
        for segment in segments:
            if segment is None:
                if not await self._send_line_break(device_id):
                    return False
            else:
                ok = await self._run_sync(
                    lambda s=segment: self._ok(
                        self._api.key_sendkey(self._ids(device_id), key=s)
                    )
                )
                if not ok:
                    return False
            await asyncio.sleep(0.12)
        return True

    async def _send_line_break(self, device_id: str) -> bool:
        from imouse_farm.utils.text_input import LINE_BREAK_FN_KEYS

        for fn_key in LINE_BREAK_FN_KEYS:
            if await self.send_fn_key(device_id, fn_key):
                return True
        logger.warning("line_break_fn_key_failed", device_id=device_id)
        return False

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

    async def reset_cursor(self, device_id: str) -> bool:
        def _reset() -> bool:
            response = self._api.mouse_reset(self._ids(device_id))
            if self._ok(response):
                return True
            logger.error(
                "mouse_reset_failed",
                device_id=device_id,
                message=self._error_message(response),
            )
            return False

        logger.info("action_mouse_reset", device_id=device_id)
        return await self._run_sync(_reset)

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

    async def open_app_switcher(self, device_id: str) -> bool:
        """Open iOS app switcher (iMouseXP App button → key_sendkey fn_key AppSwitch)."""
        logger.info("action_app_switcher", device_id=device_id)
        return await self.send_fn_key(device_id, "AppSwitch")

    async def kill_app(self, device_id: str) -> bool:
        """Force-quit apps: iMouse App button (app switcher), then swipe up five times."""
        def _kill() -> bool:
            ids = self._ids(device_id)
            for attempt in range(2):
                response = self._api.key_sendkey(ids, fn_key="AppSwitch")
                if not self._ok(response):
                    logger.error(
                        "kill_app_switcher_failed",
                        device_id=device_id,
                        attempt=attempt + 1,
                        message=self._error_message(response),
                    )
                    if attempt == 0:
                        time.sleep(0.75)
                        continue
                    return False
                time.sleep(1.5)
                swipes_ok = 0
                for i in range(5):
                    swipe_resp = self._api.mouse_swipe(
                        ids, "up", sx=203, sy=500, ex=203, ey=100
                    )
                    if self._ok(swipe_resp):
                        swipes_ok += 1
                    else:
                        logger.warning(
                            "kill_app_swipe_failed",
                            device_id=device_id,
                            swipe=i + 1,
                            attempt=attempt + 1,
                            message=self._error_message(swipe_resp),
                        )
                    time.sleep(0.5)
                logger.info(
                    "kill_app_swipes",
                    device_id=device_id,
                    swipes_ok=swipes_ok,
                    attempt=attempt + 1,
                )
                if swipes_ok > 0:
                    return True
                if attempt == 0:
                    time.sleep(0.75)
            return False

        logger.info("action_kill_app", device_id=device_id)
        return await self._run_sync(_kill)

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
        settle_after_delete: float = 3.0,
        no_delete_timeout: float = 30.0,
        max_rounds: int = 12,
        list_check_num: int = 100,
    ) -> bool:
        """Clear the album via shortcut_album_clear, tapping the iOS delete dialog.

        iOS may show multiple confirmation sheets in one pass, and the shortcut
        can leave items behind when Recents holds more than a single batch. We
        keep tapping while sheets are visible, then repeat clear rounds until
        ``album_list`` reports zero items (or ``max_rounds``).

        Note: we do not pre-check with album_get — the shortcut's get can report
        0 items even when the library is full, which would skip the clear.
        """
        from imouse_farm.actions.permission_prompts import (
            DELETE_CONFIRM_TEXTS,
            DELETE_SHEET_DISTRACTOR_TEXTS,
            DELETE_SHEET_MIN_Y,
            delete_sheet_is_visible,
            is_delete_confirm_label,
            resolve_delete_tap,
        )

        loop = asyncio.get_event_loop()
        label = album_name or "recents"
        delete_rect = [0, 250, 406, 720]
        delete_settle_after_tap = 2.0
        total_taps = 0
        last_error = ""

        def _clear() -> bool:
            nonlocal last_error
            response = self._api.shortcut_album_clear(
                self._ids(device_id), album_name=album_name, outtime=timeout_ms
            )
            if self._ok(response):
                return True
            last_error = self._error_message(response)
            logger.error("album_clear_failed", device_id=device_id, album=label, message=last_error)
            return False

        async def _scan_delete_sheet() -> list[dict]:
            """OCR the bottom sheet for delete labels and distractors like Show All."""
            specific = [t for t in DELETE_CONFIRM_TEXTS if t != "Delete"]
            matches = await self.find_text_on_device(
                device_id,
                specific + list(DELETE_SHEET_DISTRACTOR_TEXTS),
                threshold=0.62,
                contain=True,
                rect=delete_rect,
            )
            if not any(is_delete_confirm_label(str(m.get("text", ""))) for m in matches):
                bare = await self.find_text_on_device(
                    device_id,
                    ["Delete"],
                    threshold=0.72,
                    contain=False,
                    rect=delete_rect,
                )
                matches.extend(bare)
            return matches

        async def _tap_delete_once(sheet_visible: list[bool]) -> bool:
            """Tap delete once (OCR or fallback). Never taps Show All."""
            from imouse_farm.actions.pre_touch_reset import pre_touch_mouse_reset

            await pre_touch_mouse_reset(
                self,
                device_id,
                step_name="album_clear_delete",
            )
            matches = await _scan_delete_sheet()
            if delete_sheet_is_visible(matches):
                sheet_visible[0] = True
            target = resolve_delete_tap(matches, min_y=DELETE_SHEET_MIN_Y)
            if target is None:
                if matches:
                    logger.debug(
                        "album_clear_delete_scan_miss",
                        device_id=device_id,
                        raw_texts=[m.get("text", "") for m in matches[:8]],
                    )
                return False
            if isinstance(target, tuple) and target[0] == "fallback":
                x, y = target[1]
                await self.tap(device_id, x, y)
                logger.info(
                    "album_clear_delete_fallback_tap",
                    device_id=device_id,
                    x=x,
                    y=y,
                )
                return True
            await self.tap(device_id, int(target["x"]), int(target["y"]))
            logger.info(
                "album_clear_delete_tap",
                device_id=device_id,
                text=target.get("text", ""),
                x=int(target["x"]),
                y=int(target["y"]),
            )
            return True

        async def _run_clear_round(round_num: int) -> tuple[bool, int, bool]:
            """One shortcut_album_clear plus delete-sheet watcher. Returns (api_ok, taps, delete_pressed)."""
            stop = asyncio.Event()
            delete_pressed = asyncio.Event()
            tap_count = 0
            last_tap_time = 0.0
            sheet_visible = [False]
            api_ok = False

            async def _watch_and_tap() -> None:
                nonlocal tap_count, last_tap_time
                await asyncio.sleep(0.25)
                while not stop.is_set():
                    if await _tap_delete_once(sheet_visible):
                        tap_count += 1
                        last_tap_time = loop.time()
                        delete_pressed.set()
                        await asyncio.sleep(delete_settle_after_tap)
                    else:
                        await asyncio.sleep(0.3)

            logger.info("album_clear_round", device_id=device_id, album=label, round=round_num)
            watcher = asyncio.create_task(_watch_and_tap())
            try:
                api_ok = await self._run_sync(_clear)
                if not api_ok:
                    logger.warning(
                        "album_clear_api_error",
                        device_id=device_id,
                        album=label,
                        round=round_num,
                        message=last_error,
                    )
                clear_done = loop.time()
                deadline = clear_done + post_grace_seconds
                while loop.time() < deadline:
                    if delete_pressed.is_set():
                        idle = loop.time() - last_tap_time
                        if idle >= settle_after_delete:
                            matches = await _scan_delete_sheet()
                            if not delete_sheet_is_visible(matches):
                                break
                    elif (
                        (loop.time() - clear_done) >= no_delete_timeout
                        and not sheet_visible[0]
                        and api_ok
                    ):
                        break
                    await asyncio.sleep(0.2)
            finally:
                stop.set()
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

            return api_ok, tap_count, delete_pressed.is_set()

        logger.info("album_clear", device_id=device_id, album=label)
        remaining_count = -1
        for round_num in range(1, max_rounds + 1):
            api_ok, round_taps, delete_pressed = await _run_clear_round(round_num)
            total_taps += round_taps

            if not api_ok and not delete_pressed and round_num == 1:
                raise RuntimeError(last_error or "album clear failed")

            await asyncio.sleep(1.5)
            remaining = await self.album_list(
                device_id, album_name=album_name, num=list_check_num
            )
            remaining_count = len(remaining)
            logger.info(
                "album_clear_round_done",
                device_id=device_id,
                album=label,
                round=round_num,
                round_taps=round_taps,
                remaining=remaining_count,
            )
            if remaining_count == 0:
                break
            if round_taps == 0:
                break

        success = remaining_count == 0
        logger.info(
            "album_clear_done",
            device_id=device_id,
            album=label,
            delete_taps=total_taps,
            remaining=remaining_count,
            success=success,
        )
        return success

    async def album_upload(
        self,
        device_id: str,
        files: list[str],
        album_name: str | None = None,
        timeout_ms: int = 300000,
        zip_files: bool = False,
        *,
        verify: bool = True,
        post_grace_seconds: float = 8.0,
    ) -> bool:
        """Upload files to the album and confirm they actually landed.

        On success ``shortcut_album_upload`` returns the album's latest items
        (up to 10). Because the workflow clears the album immediately before
        uploading, that returned list is our uploaded files, so we confirm the
        reported count matches what we sent before letting the caller proceed.
        If the response doesn't include the list, we fall back to a fresh
        ``album_list`` ("refresh") to double-check. Returns ``False`` when the
        upload can't be confirmed so the caller can pause/retry.

        A background watcher taps "Always Allow" / "Allow" (and related labels
        on newer iOS) while the upload runs so a permission dialog can't block
        the shortcut until timeout.
        """
        from imouse_farm.actions.permission_prompts import UPLOAD_PERMISSION_TEXTS

        abs_files = [str(Path(f).resolve()) for f in files]
        expected = len(abs_files)
        stop = asyncio.Event()
        allow_tap_count = 0
        # Never tap deny/cancel variants — "Allow" is a partial match on those.
        negative_words = ("don't", "dont", "cancel", "deny", "not now", "don't allow")

        def _upload_batch(batch: list[str]) -> int:
            response = self._api.shortcut_album_upload(
                self._ids(device_id),
                files=batch,
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
                    files=batch,
                )
                raise RuntimeError(message)
            items = getattr(getattr(response, "data", None), "list", None) or []
            return len(items)

        async def _tap_allow_once() -> bool:
            """Prefer specific labels first (Always Allow before bare Allow)."""
            for text in UPLOAD_PERMISSION_TEXTS:
                matches = await self.find_text_on_device(device_id, [text])
                candidates = [
                    m
                    for m in matches
                    if not any(neg in str(m.get("text", "")).lower() for neg in negative_words)
                ]
                if not candidates:
                    continue
                best = max(candidates, key=lambda m: m.get("confidence", 0))
                await self.tap(device_id, int(best["x"]), int(best["y"]))
                logger.info(
                    "album_upload_permission_tap",
                    device_id=device_id,
                    text=best.get("text") or text,
                    x=int(best["x"]),
                    y=int(best["y"]),
                )
                return True
            return False

        async def _watch_and_tap() -> None:
            nonlocal allow_tap_count
            while not stop.is_set():
                if await _tap_allow_once():
                    allow_tap_count += 1
                    await asyncio.sleep(1.5)
                else:
                    await asyncio.sleep(0.4)

        logger.info(
            "album_upload",
            device_id=device_id,
            file_count=expected,
            upload_sequence=[Path(f).name for f in abs_files],
        )
        watcher = asyncio.create_task(_watch_and_tap())
        reported = 0
        try:
            # One file at a time, in caller order (engine passes Recents-ready sequence).
            for i, path in enumerate(abs_files):
                batch_reported = await self._run_sync(lambda p=path: _upload_batch([p]))
                reported = max(reported, batch_reported)
                if i + 1 < len(abs_files):
                    await asyncio.sleep(1.5)
            # Permission dialogs can appear just after the API returns too.
            await asyncio.sleep(post_grace_seconds)
        finally:
            stop.set()
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

        if allow_tap_count:
            logger.info(
                "album_upload_permissions_tapped",
                device_id=device_id,
                tap_count=allow_tap_count,
            )

        if not verify:
            return True

        # The shortcut returns up to 10 latest items; on a freshly-cleared
        # album that means our uploads, so this many confirms success.
        needed = min(expected, 10)
        confirmed = reported

        # If the upload response didn't echo the list, refresh via album_list.
        if confirmed < needed:
            try:
                items = await self.album_list(device_id, album_name=album_name)
                confirmed = max(confirmed, len(items))
            except Exception as exc:  # noqa: BLE001 — verification best-effort
                logger.warning("album_upload_verify_list_failed", device_id=device_id, error=str(exc))

        if confirmed < needed:
            logger.warning(
                "album_upload_unconfirmed",
                device_id=device_id,
                expected=expected,
                confirmed=confirmed,
            )
            return False

        logger.info(
            "album_upload_done",
            device_id=device_id,
            expected=expected,
            confirmed=confirmed,
        )
        return True

    async def find_image_on_device(
        self, device_id: str, template_base64: str, threshold: float = 0.8,
        rect: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        def _find() -> list[dict[str, Any]]:
            response = self._api.pic_find_image_cv(
                device_id, [template_base64], similarity=threshold, rect=rect
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
        rect: list[int] | None = None,
    ) -> dict[str, Any] | None:
        import base64

        if not template_path.is_file():
            logger.warning("template_file_missing", path=str(template_path))
            return None
        path_str = str(template_path.resolve())
        matches = await self.find_image_on_device(device_id, path_str, threshold, rect=rect)
        if not matches:
            b64 = base64.b64encode(template_path.read_bytes()).decode()
            matches = await self.find_image_on_device(device_id, b64, threshold, rect=rect)
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
        rect: list[int] | None = None,
        is_ex: bool = False,
    ) -> list[dict[str, Any]]:
        def _find() -> list[dict[str, Any]]:
            response = self._api.pic_find_text(
                device_id,
                texts,
                similarity=threshold,
                contain=contain,
                rect=rect,
                is_ex=is_ex,
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
