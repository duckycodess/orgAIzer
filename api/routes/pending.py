from __future__ import annotations

from fastapi import APIRouter, Body

from api.state import get_controller

router = APIRouter()


@router.get("/pending")
def get_pending():
    return get_controller().get_pending()


@router.post("/pending/{event_id}/decide")
def decide(event_id: int, body: dict = Body(...)):
    action = body.get("action", "skipped")
    subject = body.get("subject", "")
    dest = get_controller().handle_user_decision(event_id, subject, action)
    return {"ok": True, "destination": dest}
