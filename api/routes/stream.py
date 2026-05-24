"""SSE endpoint — streams real-time file events to the frontend."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.state import get_event_queue

router = APIRouter()


async def _event_generator(queue: asyncio.Queue):
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            yield ": ping\n\n"


@router.get("/events")
async def events():
    queue = get_event_queue()

    async def gen():
        async for chunk in _event_generator(queue):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
