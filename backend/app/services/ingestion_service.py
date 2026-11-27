import os
import json
import cv2
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.config import config
from app.db.vector_db import vector_db
from app.db.sqlite_db import SessionLocal
from app.db.models import Personnel
from app.services.face_backend import get_backend

class PlugAndPlayIngestionService:
    def __init__(self):
        self.known_persons_dir = config.KNOWN_PERSONS_DIR

    def register_person_from_folder(self, person_folder_path: str, raise_errors: bool = False) -> bool:
        """Processes a single person's directory containing photo(s) and metadata info.json."""
        if not os.path.isdir(person_folder_path):
            return False

        folder_name = os.path.basename(person_folder_path)
        person_id = folder_name.split("_")[0] if "_" in folder_name else folder_name

        metadata = {
            "name": folder_name.replace("_", " ").title(),
            "role": "Employee",
            "department": "General",
            "email": f"{person_id.lower()}@organization.com",
            "phone": ""
        }

        # Check for info.json inside folder
        info_json_path = os.path.join(person_folder_path, "info.json")
        if os.path.exists(info_json_path):
            try:
                with open(info_json_path, "r") as f:
                    user_json = json.load(f)
                    metadata.update(user_json)
            except Exception as e:
                print(f"[Ingestion] Error reading info.json in {folder_name}: {e}")

        # Scan for image files (.jpg, .png, .jpeg)
        image_files = [
            f for f in os.listdir(person_folder_path)
            if f.lower().endswith((".jpg", ".png", ".jpeg"))
        ]

        if not image_files:
            return False

        registered = False
        for img_name in image_files:
            img_path = os.path.join(person_folder_path, img_name)
            registered = self._process_single_image(person_id, img_path, metadata, raise_errors) or registered
        return registered

    def register_single_file(self, file_path: str):
        """Registers a person directly from a file like 'EMP102_Alice.jpg'."""
        if not os.path.isfile(file_path) or not file_path.lower().endswith((".jpg", ".png", ".jpeg")):
            return

        filename = os.path.splitext(os.path.basename(file_path))[0]
        person_id = filename.split("_")[0] if "_" in filename else filename
        name = filename.replace("_", " ").title()

        metadata = {
            "name": name,
            "role": "Employee",
            "department": "General",
            "email": f"{person_id.lower()}@organization.com",
            "phone": ""
        }

        self._process_single_image(person_id, file_path, metadata)

    def _process_single_image(self, person_id: str, img_path: str, metadata: dict, raise_errors: bool = False) -> bool:
        try:
            backend = get_backend()
            image = cv2.imread(img_path)
            if image is None:
                print(f"[Ingestion Warning] Could not read image {img_path}")
                return False
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            embedding = backend.embed_photo(rgb)

            if not embedding:
                print(f"[Ingestion Warning] No face detected in {img_path}")
                return False

            embedding_id = f"{person_id}::{os.path.basename(img_path)}"

            # 1. Upsert into ChromaDB Vector Index (one vector per photo, so
            #    multiple photos of the same person coexist instead of overwriting).
            vector_db.add_face_embedding(embedding_id, person_id, embedding, metadata)

            # 2. Upsert into SQLite Relational Database
            db = SessionLocal()
            try:
                person = db.query(Personnel).filter(Personnel.person_id == person_id).first()
                if not person:
                    person = Personnel(
                        person_id=person_id,
                        name=metadata.get("name", person_id),
                        role=metadata.get("role", "Employee"),
                        department=metadata.get("department", "General"),
                        email=metadata.get("email"),
                        phone=metadata.get("phone"),
                        metadata_json=json.dumps(metadata)
                    )
                    db.add(person)
                else:
                    person.name = metadata.get("name", person.name)
                    person.role = metadata.get("role", person.role)
                    person.department = metadata.get("department", person.department)
                    person.metadata_json = json.dumps(metadata)

                db.commit()
                print(f"[Ingestion Success] Registered/Updated {person_id} ({metadata.get('name')}) into VectorDB & SQLite")
            finally:
                db.close()
            return True

        except Exception as e:
            print(f"[Ingestion Error] Failed to process {img_path}: {e}")
            if raise_errors:
                raise
            return False

    def sync_all(self):
        """Scans the entire known_persons folder for plug-and-play enrollment."""
        if not os.path.exists(self.known_persons_dir):
            os.makedirs(self.known_persons_dir, exist_ok=True)
            return

        items = os.listdir(self.known_persons_dir)
        for item in items:
            full_path = os.path.join(self.known_persons_dir, item)
            if os.path.isdir(full_path):
                self.register_person_from_folder(full_path)
            elif os.path.isfile(full_path):
                self.register_single_file(full_path)

class DirectoryWatchHandler(FileSystemEventHandler):
    def __init__(self, service: PlugAndPlayIngestionService):
        self.service = service

    def on_created(self, event):
        if event.is_directory:
            self.service.register_person_from_folder(event.src_path)
        else:
            self.service.register_single_file(event.src_path)

ingestion_service = PlugAndPlayIngestionService()

def start_directory_watcher():
    event_handler = DirectoryWatchHandler(ingestion_service)
    observer = Observer()
    observer.schedule(event_handler, path=config.KNOWN_PERSONS_DIR, recursive=True)
    observer.start()
    print(f"[PlugAndPlay Watcher] Monitoring {config.KNOWN_PERSONS_DIR} for instant folder/JSON ingestion...")
    return observer
