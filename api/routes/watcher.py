from __future__ import annotations

from fastapi import APIRouter

from api.state import get_controller

router = APIRouter()


@router.get("/watcher/status")
def watcher_status():
    return {"running": get_controller().is_watching()}


@router.post("/watcher/start")
def watcher_start():
    get_controller().start_watching()
    return {"ok": True}


@router.post("/watcher/stop")
def watcher_stop():
    get_controller().stop_watching()
    return {"ok": True}
