from __future__ import annotations

from fastapi import APIRouter, Body

from api.state import get_controller

router = APIRouter()


@router.get("/history")
def get_history(limit: int = 200):
    return get_controller().get_history(limit)


@router.post("/history/{event_id}/mark-as-school")
def mark_as_school(event_id: int, body: dict = Body(...)):
    subject = body.get("subject", "")
    dest = get_controller().handle_mark_as_school(event_id, subject)
    return {"ok": dest is not None, "destination": dest}


@router.post("/history/{event_id}/undo")
def undo(event_id: int):
    ok = get_controller().undo_move(event_id)
    return {"ok": ok}
