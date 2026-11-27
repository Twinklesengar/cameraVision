import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import config
from app.db.sqlite_db import init_sqlite_db
from app.services.logging_service import setup_logging
from app.errors import add_exception_handlers
from app.services.ingestion_service import ingestion_service, start_directory_watcher
from app.services.camera_manager import camera_manager
from app.services.camera_ops_service import camera_ops_service
from app.services.alert_dispatcher import alert_dispatcher
from app.services.rule_engine import rule_engine
from app.routes.stream import router as stream_router
from app.routes.personnel import router as personnel_router
from app.routes.analytics import router as analytics_router
from app.routes.alerts import router as alerts_router
from app.routes.copilot import router as copilot_router
from app.routes.assets import router as assets_router
from app.routes.auth import router as auth_router
from app.routes.system import router as system_router
from app.routes.metrics import router as metrics_router

logger = logging.getLogger("aegisvision.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Structured logging (rotating file + console).
    setup_logging()

    # 1. Capture the main event loop for threadsafe WS alert broadcast.
    alert_dispatcher.bind_loop(asyncio.get_running_loop())

    # 2. Initialize SQLite Database Tables
    logger.info("Initializing SQLite Relational Database...")
    init_sqlite_db()

    # 3. Sync Plug-and-Play folder/JSON enrolments
    logger.info("Syncing plug-and-play enrolments from data/known_persons...")
    ingestion_service.sync_all()

    # 4. Start directory watcher
    observer = start_directory_watcher()

    # 5. Camera workers are started explicitly by an administrator in the dashboard.
    logger.info("Camera monitoring is stopped; start it from the dashboard when ready.")

    # 5b. Start the fleet housekeeper (feed health, activity flush, retention).
    camera_ops_service.start()

    # 6. Start the rule-escalation background sweep.
    rule_task = asyncio.create_task(rule_engine.run())

    yield

    # Cleanup on shutdown
    logger.info("Stopping fleet housekeeper...")
    camera_ops_service.stop()
    logger.info("Stopping camera workers...")
    camera_manager.stop_all()
    logger.info("Stopping file system observer...")
    observer.stop()
    observer.join()
    rule_task.cancel()
    try:
        await rule_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title=config.PROJECT_NAME,
    version=config.VERSION,
    description="Enterprise Multi-Camera AI Surveillance, Analytics & Decision Platform",
    lifespan=lifespan
)

add_exception_handlers(app)

# CORS Configuration
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(stream_router)
app.include_router(personnel_router)
app.include_router(analytics_router)
app.include_router(alerts_router)
app.include_router(copilot_router)
app.include_router(assets_router)
app.include_router(auth_router)
app.include_router(system_router)
app.include_router(metrics_router)

@app.get("/")
async def root():
    if config.SERVE_FRONTEND and config.FRONTEND_DIST.exists():
        return FileResponse(config.FRONTEND_DIST / "index.html")
    return {
        "status": "online",
        "system": config.PROJECT_NAME,
        "version": config.VERSION,
        "documentation": "/docs"
    }

if config.SERVE_FRONTEND and config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)