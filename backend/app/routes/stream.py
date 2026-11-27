import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import config
from app.services.camera_manager import camera_manager
from app.services.camera_registry import camera_registry
from app.services.analysis_scheduler import analysis_scheduler
from app.services.alert_dispatcher import alert_dispatcher
from app.routes.auth import require_admin

router = APIRouter(prefix="/api/stream", tags=["Video Stream & Surveillance"])

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")


class CameraCreate(BaseModel):
    camera_id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1)
    type: str = "gate"
    resolution: Optional[str] = "640x480"
    fps_limit: Optional[int] = Field(default=None, ge=1, le=60)


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    source: Optional[str] = None
    type: Optional[str] = None
    resolution: Optional[str] = None
    fps_limit: Optional[int] = Field(default=None, ge=1, le=60)
    active: Optional[bool] = None


def _redact(cam: dict) -> dict:
    clone = dict(cam)
    clone["source"] = camera_registry.redact_source(str(cam.get("source")))
    return clone


def _iter_camera(camera_id: str):
    """Serve the latest annotated frame pushed by the camera worker for `camera_id`."""
    interval = config.STREAM_BROADCAST_INTERVAL_MS / 1000.0
    while True:
        frame = camera_manager.get_latest(camera_id)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame.jpeg + b'\r\n')
        time.sleep(interval)


@router.get("/video_feed")
async def video_feed(camera_id: str = "cam_entrance"):
    return StreamingResponse(
        _iter_camera(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/snapshot")
async def snapshot(camera_id: str = "cam_entrance"):
    frame = camera_manager.get_latest(camera_id)
    return Response(content=frame.jpeg, media_type="image/jpeg")


@router.get("/cameras")
async def cameras():
    joined = [_redact(c) for c in camera_manager.list_cameras()]
    return {"status": "success", "cameras": joined}


@router.get("/cameras/{camera_id}")
async def camera_detail(camera_id: str):
    cam = camera_manager.get_camera(camera_id)
    if cam is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "success", "camera": _redact(cam)}


@router.get("/cameras/{camera_id}/history")
async def camera_history(camera_id: str, limit: int = 180):
    """Per-camera situational trace (motion, scene, people) for sparklines."""
    cfg = camera_registry.get(camera_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    limit = max(1, min(720, limit))
    worker = camera_manager.workers.get(camera_id)
    history = worker.get_history(limit=limit) if worker else []
    return {"status": "success", "camera_id": camera_id, "history": history}


@router.get("/clips")
async def list_clips(camera_id: str = ""):
    """Evidence clips saved for an incident (empty = across the whole fleet)."""
    workers = camera_manager.workers
    if camera_id:
        if camera_id not in workers:
            raise HTTPException(status_code=404, detail="Camera not found or inactive")
        clips = workers[camera_id].list_clips()
    else:
        clips = []
        for cam, worker in workers.items():
            clips.extend(worker.list_clips())
    clips.sort(key=lambda c: c["timestamp"], reverse=True)
    return {"status": "success", "count": len(clips), "clips": clips[:200]}


@router.get("/clips/{filename}")
async def serve_clip(filename: str):
    """Serve a saved evidence clip (path-traversal safe)."""
    safe = Path(filename).name
    if not safe.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid clip name")
    path = config.CLIP_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="video/mp4")


@router.get("/fleet/summary")
async def fleet_summary():
    cameras = camera_manager.list_cameras()
    busy = sum(1 for c in cameras if c["online"] and c.get("scene_state") in ("BUSY", "CROWDED"))
    return {
        "status": "success",
        "total": len(cameras),
        "online": sum(1 for c in cameras if c["online"]),
        "active_cameras": sum(1 for c in cameras if c["active"]),
        "busy": busy,
        "analysis_budget_available": analysis_scheduler.available(),
        "analysis_queue": analysis_scheduler.queue_depth(),
    }


@router.get("/monitoring")
def monitoring_status():
    return {"status": "success", **camera_manager.monitoring_status()}


@router.post("/monitoring/start")
def start_monitoring(auth: dict = Depends(require_admin)):
    return {"status": "success", **camera_manager.start_monitoring()}


@router.post("/monitoring/stop")
def stop_monitoring(auth: dict = Depends(require_admin)):
    return {"status": "success", **camera_manager.stop_monitoring()}


@router.post("/cameras", status_code=201)
async def add_camera(req: CameraCreate, auth: dict = Depends(require_admin)):
    if not _ID_RE.match(req.camera_id):
        raise HTTPException(status_code=422, detail="camera_id must match ^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
    if req.type not in config.CAMERA_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {', '.join(config.CAMERA_TYPES)}")
    if req.resolution and not re.match(r"^\d{3,5}x\d{3,5}$", req.resolution):
        raise HTTPException(status_code=400, detail="resolution must look like WxH, e.g. 640x480")
    try:
        camera_registry.normalize_source(req.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if camera_registry.exists(req.camera_id):
        raise HTTPException(status_code=409, detail=f"camera {req.camera_id!r} already registered")
    try:
        cfg = camera_manager.add_camera(
            camera_id=req.camera_id,
            name=req.name,
            source=req.source,
            cam_type=req.type,
            resolution=req.resolution,
            fps_limit=req.fps_limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to start camera: {e}")
    return {"status": "success", "camera": _redact(cfg)}


@router.patch("/cameras/{camera_id}")
def update_camera(camera_id: str, req: CameraUpdate, auth: dict = Depends(require_admin)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if "type" in fields and fields["type"] not in config.CAMERA_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {', '.join(config.CAMERA_TYPES)}")
    if "resolution" in fields and fields["resolution"] and not re.match(r"^\d{3,5}x\d{3,5}$", fields["resolution"]):
        raise HTTPException(status_code=400, detail="resolution must look like WxH, e.g. 640x480")
    if "source" in fields:
        try:
            camera_registry.normalize_source(fields["source"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    cfg = camera_manager.update_camera(camera_id, **fields)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "success", "camera": _redact(cfg)}


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, auth: dict = Depends(require_admin)):
    removed = camera_manager.remove_camera(camera_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "success", "message": f"Camera {camera_id} unregistered"}


@router.post("/cameras/{camera_id}/restart")
def restart_camera(camera_id: str, auth: dict = Depends(require_admin)):
    if camera_registry.get(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera_manager.monitoring_status()["running"]:
        raise HTTPException(status_code=409, detail="Start monitoring from the dashboard before restarting a camera")
    camera_manager.restart(camera_id)
    return {"status": "success", "camera": _redact(camera_manager.get_camera(camera_id))}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await alert_dispatcher.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_text(f'{{"type": "PONG", "timestamp": "{utcnow().isoformat()}"}}')
    except WebSocketDisconnect:
        alert_dispatcher.disconnect(websocket)