from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.sqlite_db import get_db
from app.db.models import AssetLog
from app.services.spatial_memory import spatial_memory
from app.routes.auth import require_admin
from app.schemas.api import AssetListOut, AssetOut

router = APIRouter(prefix="/api/assets", tags=["Spatial Memory & Anti-Theft"])


class AssetRegisterRequest(BaseModel):
    asset_name: str
    owner_person_id: str
    bbox: List[int] = None  # [x1, y1, x2, y2]
    camera_id: str = "cam_workspace"


@router.get("/", response_model=AssetListOut)
def list_assets(db: Session = Depends(get_db)):
    assets = db.query(AssetLog).all()
    return AssetListOut(count=len(assets), data=[AssetOut.model_validate(a) for a in assets])


@router.post("/", response_model=AssetOut)
def register_asset(req: AssetRegisterRequest, db: Session = Depends(get_db), auth: dict = Depends(require_admin)):
    if not req.bbox or len(req.bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox must be [x1, y1, x2, y2]")
    spatial_memory.register_or_update_asset(
        asset_name=req.asset_name,
        owner_id=req.owner_person_id,
        bbox=[int(v) for v in req.bbox],
        camera_id=req.camera_id,
    )
    asset = db.query(AssetLog).filter(AssetLog.asset_name == req.asset_name).first()
    if not asset:
        raise HTTPException(status_code=500, detail="Failed to register asset")
    return AssetOut.model_validate(asset)


@router.delete("/{asset_name}")
def delete_asset(asset_name: str, auth: dict = Depends(require_admin)):
    if not spatial_memory.delete_asset(asset_name):
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"status": "success", "message": f"Deleted asset {asset_name}"}