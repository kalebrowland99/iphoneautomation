"""Per-device action queue."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from imouse_farm.config.models import ActionRequest
from imouse_farm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueuedAction:
    """Action waiting in queue."""

    request: ActionRequest
    future: asyncio.Future[bool] | None = None


class ActionQueue:
    """FIFO action queue for a single device."""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._queue: asyncio.Queue[QueuedAction] = asyncio.Queue()
        self._processing = False

    async def enqueue(self, request: ActionRequest) -> bool:
        """Add action to queue and wait for result."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        queued = QueuedAction(request=request, future=future)
        await self._queue.put(queued)
        logger.debug("action_queued", device_id=self.device_id, action=request.action_type.value)
        return await future

    async def dequeue(self) -> QueuedAction:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_processing(self) -> bool:
        return self._processing

    @is_processing.setter
    def is_processing(self, value: bool) -> None:
        self._processing = value
