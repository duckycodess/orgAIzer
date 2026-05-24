"""
api/main.py -- FastAPI application for OrgAIzer.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import api.state as state
from api.routes import history, pending, settings, stream, watcher
from app.api_controller import APIController

logger = logging.getLogger(__name__)


def _on_controller_event(event_type: str, data: dict) -> None:
    if state.loop and state.event_queue:
        state.loop.call_soon_threadsafe(state.event_queue.put_nowait, {"type": event_type, **data})


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.loop = asyncio.get_running_loop()
    state.event_queue = asyncio.Queue()
    state.controller = APIController()
    state.controller.add_event_callback(_on_controller_event)
    state.controller.start_watching()
    logger.info("OrgAIzer API started")

    yield

    state.controller.shutdown()
    logger.info("OrgAIzer API shut down")


app = FastAPI(title="OrgAIzer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history.router, prefix="/api")
app.include_router(pending.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(watcher.router, prefix="/api")
