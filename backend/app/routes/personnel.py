import os
import json
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.db.sqlite_db import get_db
from app.db.models import Personnel
from app.db.vector_db import vector_db
from app.services.ingestion_service import ingestion_service
from app.config import config
from app.routes.auth import require_admin
from app.schemas.api import PersonnelListOut, PersonnelOut

router = APIRouter(prefix="/api/personnel", tags=["Personnel Management"])


@router.get("/", response_model=PersonnelListOut)
@router.get("", response_model=PersonnelListOut)
def get_all_personnel(db: Session = Depends(get_db)):
    personnel = db.query(Personnel).all()
    return PersonnelListOut(count=len(personnel), data=[PersonnelOut.model_validate(p) for p in personnel])


@router.get("/{person_id}", response_model=PersonnelOut)
def get_personnel_by_id(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Personnel).filter(Personnel.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Personnel not found")
    return PersonnelOut.model_validate(person)


@router.post("/enroll")
async def enroll_personnel(
    person_id: str = Form(...),
    name: str = Form(...),
    role: str = Form("Employee"),
    department: str = Form("General"),
    email: str = Form(""),
    phone: str = Form(""),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_admin),
):
    """
    Plug-and-Play Personnel Enrollment API.
    Saves photo to data/known_persons/<person_id>_<name>/, computes vector embedding,
    upserts into ChromaDB and SQLite DB.
    """
    if not photo.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Invalid image format. Only JPG/PNG allowed.")

    folder_name = f"{person_id}_{name.replace(' ', '_')}"
    target_dir = os.path.join(config.KNOWN_PERSONS_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    img_save_path = os.path.join(target_dir, photo.filename)
    with open(img_save_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    metadata = {
        "name": name,
        "role": role,
        "department": department,
        "email": email,
        "phone": phone
    }

    info_json_path = os.path.join(target_dir, "info.json")
    with open(info_json_path, "w") as f:
        json.dump(metadata, f, indent=2)

    # Process image for VectorDB & SQLite sync
    if not ingestion_service.register_person_from_folder(target_dir, raise_errors=True):
        raise HTTPException(
            status_code=422,
            detail="No face could be indexed from this photo. Upload a clear, front-facing JPG/PNG and try again.",
        )

    return {
        "status": "success",
        "message": f"Successfully enrolled {name} ({person_id})",
        "data": metadata
    }


@router.get("/photo/{person_id}")
def get_person_photo(person_id: str, db: Session = Depends(get_db)):
    """Return path of the person's enrolled photo (if any) for avatar rendering."""
    folder = None
    for item in os.listdir(config.KNOWN_PERSONS_DIR):
        if item.startswith(person_id + "_") or item == person_id:
            folder = os.path.join(config.KNOWN_PERSONS_DIR, item)
            break
    if not folder or not os.path.isdir(folder):
        raise HTTPException(status_code=404, detail="No photo on record")
    for f in os.listdir(folder):
        if f.lower().endswith((".jpg", ".jpeg", ".png")):
            return {"status": "success", "photo_path": os.path.join(folder, f)}
    raise HTTPException(status_code=404, detail="No photo on record")


@router.delete("/{person_id}")
def delete_personnel(person_id: str, db: Session = Depends(get_db), auth: dict = Depends(require_admin)):
    person = db.query(Personnel).filter(Personnel.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Personnel not found")

    vector_db.delete_person_embeddings(person_id)
    db.delete(person)
    db.commit()

    return {"status": "success", "message": f"Deleted personnel {person_id}"}