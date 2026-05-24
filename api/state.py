"""Shared app state — imported by routes to avoid circular imports."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.api_controller import APIController

controller: "APIController | None" = None
event_queue: asyncio.Queue | None = None
loop: asyncio.AbstractEventLoop | None = None


def get_controller() -> "APIController":
    assert controller is not None, "Controller not initialized"
    return controller


def get_event_queue() -> asyncio.Queue:
    assert event_queue is not None, "Event queue not initialized"
    return event_queue
