from __future__ import annotations

from fastapi import APIRouter, Body

from api.state import get_controller

router = APIRouter()


@router.get("/settings")
def get_settings():
    s = get_controller().settings
    return {
        "downloads_path": s.downloads_path,
        "school_root": s.school_root,
        "watch_folder_override": s.watch_folder_override,
        "threshold_high": s.threshold_high,
        "threshold_medium": s.threshold_medium,
        "warmup_active": s.warmup_active,
        "warmup_labeled_count": s.warmup_labeled_count,
        "effective_watch_folder": s.effective_watch_folder,
    }


@router.put("/settings")
def update_settings(body: dict = Body(...)):
    ctrl = get_controller()
    s = ctrl.settings
    if "downloads_path" in body:
        s.downloads_path = body["downloads_path"]
    if "school_root" in body:
        s.school_root = body["school_root"]
    if "watch_folder_override" in body:
        s.watch_folder_override = body["watch_folder_override"]
    if "threshold_high" in body:
        s.threshold_high = float(body["threshold_high"])
    if "threshold_medium" in body:
        s.threshold_medium = float(body["threshold_medium"])
    if "warmup_active" in body:
        s.warmup_active = bool(body["warmup_active"])
    ctrl.save_settings()
    return {"ok": True}


@router.get("/subjects")
def get_subjects():
    return get_controller().get_subject_names()


@router.post("/scan-subjects")
def scan_subjects(body: dict = Body(...)):
    path = body.get("path", "")
    count = get_controller().scan_subject_folders(path)
    return {"count": count}


@router.post("/seed")
def seed(body: dict = Body(...)):
    folder = body.get("folder", "")
    count = get_controller().seed_from_folder(folder)
    return {"count": count}


@router.get("/warmup-status")
def warmup_status():
    labeled, required = get_controller().get_warmup_status()
    return {"labeled": labeled, "required": required}


@router.post("/retrain")
def retrain():
    get_controller().trigger_retrain()
    return {"ok": True}


@router.post("/clear-training")
def clear_training():
    get_controller().clear_training_samples()
    return {"ok": True}
