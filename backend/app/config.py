import os
from pathlib import Path
from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Runtime configuration for AegisVision. Overridable via environment variables or a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Core ----
    PROJECT_NAME: str = "AegisVision - AI Enterprise Surveillance Platform"
    VERSION: str = "3.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True
    LOG_LEVEL: str = "INFO"

    # ---- Paths (project layout) ----
    BASE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    @property
    def DATA_DIR(self) -> Path:
        return self.BASE_DIR / "data"

    @property
    def VECTOR_DB_DIR(self) -> Path:
        return self.DATA_DIR / "vector_db"

    @property
    def KNOWN_PERSONS_DIR(self) -> Path:
        return self.DATA_DIR / "known_persons"

    @property
    def LOGS_DIR(self) -> Path:
        return self.DATA_DIR / "logs"

    @property
    def SNAPSHOTS_DIR(self) -> Path:
        return self.DATA_DIR / "snapshots"

    @property
    def CLIP_DIR(self) -> Path:
        return self.DATA_DIR / "clips"

    @property
    def SQLITE_URL(self) -> str:
        return os.getenv("SQLITE_URL", f"sqlite:///{self.DATA_DIR / 'surveillance.db'}")

    # ---- Face matching thresholds ----
    FACE_DISTANCE_THRESHOLD: float = 0.60
    FACE_CONFIDENCE_MIN: float = 0.65
    ANTI_SPOOF_THRESHOLD: float = 0.70
    # Seconds a track must be held before its label is trusted at the gate.
    GATE_TRACK_CONFIRM_SEC: float = 1.5
    # ---- Recognition backend (lightweight + high accuracy) ----
    # auto = prefer the insightface/ONNX pipeline (SCRFD detect + ArcFace embed),
    # silently falling back to the legacy dlib `face_recognition` path when the
    # package or model is unavailable; `insightface` or `legacy` force a choice.
    FACE_BACKEND: str = "auto"
    # Model zoo name: "buffalo_sc" (light: SCRFD-500M + w600k_mbf) is the default;
    # "buffalo_l" (SCRFD-10G + w600k_r50) trades a little speed for accuracy.
    FACE_INSIGHTFACE_MODEL: str = "buffalo_sc"
    FACE_DET_SIZE: int = 320
    FACE_USE_GPU: bool = False

    # ---- Analytics thresholds ----
    IDLE_TIMEOUT_SECONDS: int = 300
    PHONE_USAGE_THRESHOLD_SEC: int = 10
    EAR_DROWSINESS_THRESHOLD: float = 0.20
    POSTURE_SLOUCH_RATIO: float = 1.2
    # A face not seen at the gate for this long is considered to have left.
    GATE_EXIT_TIMEOUT_SECONDS: int = 60

    # ---- Spatial memory / anti-theft ----
    ASSET_MOTION_DIFF_THRESHOLD: float = 18.0  # mean grayscale diff (0-255) that counts as movement
    ASSET_MOTION_CONFIRM_FRAMES: int = 6       # frames of sustained motion before alerting
    ASSET_ALERT_COOLDOWN_SECONDS: int = 120    # min gap between alerts for the same asset

    # ---- Rule-based escalation (alert dedup + severity bump) ----
    RULE_SWEEP_INTERVAL_SEC: int = 30          # how often the rule engine sweeps recent logs
    RULE_WINDOW_MIN: int = 30                  # look-back window for rule evaluation
    UNKNOWN_GATE_COUNT: int = 3                # >= N UNKNOWN gate passes in window -> CRITICAL
    PHONE_OVERUSE_COUNT: int = 3               # >= N phone-distraction episodes in window -> WARNING
    DROWSINESS_REPEAT_COUNT: int = 3           # >= N drowsiness detections in window -> WARNING
    ESCALATION_DEDUPE_SEC: int = 600           # don't re-emit same escalation within this window

    # ---- External push providers (config-gated; disabled when empty) ----
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    NOTIFY_WEBHOOK_URL: str = ""               # generic POST webhook; body is the alert JSON
    NOTIFY_MIN_SEVERITY: str = "WARNING"       # INFO/WARNING/CRITICAL minimum severity to push

    # ---- Camera & streaming ----
    # `source` may be an int (webcam index) or an RTSP/MJPEG url string.
    CAMERA_STREAMS: Dict[str, dict] = {
        "cam_entrance": {"name": "Main Entrance Gate", "source": 0, "type": "gate"},
    }
    CAMERA_TYPES: tuple = ("gate", "productivity", "security")
    CAMERA_RESOLUTION: str = "640x480"
    CAMERA_FPS_LIMIT: int = 25
    CAMERA_RECONNECT_SECONDS: int = 3
    STREAM_BROADCAST_INTERVAL_MS: int = 33

    # ---- Low-compute surveillance pipeline ----
    # The pricey face pipeline (detect → embed → vector match) does NOT run on
    # every frame of every camera. Per camera it runs at most once per
    # CAMERA_ANALYZE_INTERVAL_SEC, and only when a cheap grayscale frame-diff
    # exceeds CAMERA_MOTION_THRESHOLD — unless CAMERA_ANALYZE_MAX_GAP_SEC has
    # elapsed, which forces a re-analysis so gate/occupancy stays truthful even
    # in a completely still scene.
    CAMERA_ANALYZE_INTERVAL_SEC: float = 0.5
    CAMERA_MOTION_GATE: bool = True
    CAMERA_MOTION_THRESHOLD: int = 12      # mean abs-diff (0-255) that counts as motion
    CAMERA_MOTION_EMA_ALPHA: float = 0.20
    CAMERA_ANALYZE_MAX_GAP_SEC: float = 3.0
    # To keep the live view alive without encoding every captured frame, JPEG is
    # re-encoded at most this often per camera (annotations force an immediate
    # publish when the face pipeline does run).
    CAMERA_JPEG_PUBLISH_INTERVAL_SEC: float = 0.20
    # ---- Shared analysis budget (corporate multi-camera CPU control) ----
    # The heavy detect→embed→match pipeline is executed on a bounded thread
    # pool (so simultaneous busy cameras parallelise across cores instead of
    # serialising) and is globally rate-limited: across ALL cameras the face
    # pipeline runs at most CAMERA_GLOBAL_ANALYZE_FPS times per second. This is
    # the hard ceiling that stops one crowded camera from starving the rest.
    CAMERA_ANALYSIS_POOL_SIZE: int = 4
    CAMERA_GLOBAL_ANALYZE_FPS: float = 6.0
    CAMERA_ANALYSIS_TIMEOUT_SEC: float = 2.0

    # ---- Fleet ops: offline alerting, activity persistence, evidence ----
    # A worker that has produced no frame for this long (feed dead / stream
    # unreadable) triggers a CAMERA_OFFLINE incident alert for that camera.
    CAMERA_OFFLINE_GRACE_SEC: float = 15.0
    # Min gap before the same camera can be alerted offline again (prevents
    # alert spam across flapping feeds).
    CAMERA_OFFLINE_COOLDOWN_SEC: float = 300.0
    # How often the fleet housekeeper flushes per-camera activity to SQLite and
    # re-checks feed health (seconds).
    CAMERA_OPS_SWEEP_SEC: float = 20.0
    # How many days of per-minute camera activity to keep in SQLite.
    CAMERA_ACTIVITY_RETENTION_DAYS: int = 30
    # When scene is CROWDED or people >= this, the worker keeps evidence frames.
    CAMERA_CROWD_ALERT_AT: int = 5
    # ---- Evidence clips ----
    CLIP_ENABLED: bool = True
    CLIP_SECONDS: int = 120
    CLIP_FPS: float = 2.0
    CLIP_COOLDOWN_SEC: float = 300.0
    CLIP_RETENTION_HOURS: int = 72
    # ---- Adaptive capture FPS ----
    # When the shared analysis pool is saturated, capture drops to no lower than
    # this FPS so feeds stay live but the CPU wall is respected.
    CAMERA_MIN_FPS: int = 8

    # ---- Tracking ----
    # How often (seconds) a stable track is re-embedded + matched against the vector DB.
    TRACK_REEMBED_INTERVAL_SEC: float = 1.5
    TRACK_KEEP_SECONDS: float = 4.0
    TRACK_IOU_MIN: float = 0.35

    # ---- Privacy / retention ----
    # When True, low-res UNKNOWN face crops are stored under data/snapshots (config-gated).
    ENABLE_UNKNOWN_SNAPSHOTS: bool = False
    SNAPSHOT_MAX_PER_UNKNOWN: int = 3

    # ---- AI copilot ----
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # ---- API (matches frontend VITE_API_BASE) ----
    API_BASE_URL: str = "http://localhost:8000"

    # ---- Auth (Phase 6; change in production) ----
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # ---- Frontend serving (v3) ----
    # The no-build HTML console (frontend/index.html, login.html) is served by
    # the same FastAPI process at the site root when SERVE_FRONTEND is enabled.
    SERVE_FRONTEND: bool = True
    FRONTEND_DIST: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "frontend")


config = Config()

# Ensure runtime directories exist.
for path in [config.DATA_DIR, config.VECTOR_DB_DIR, config.KNOWN_PERSONS_DIR, config.LOGS_DIR, config.SNAPSHOTS_DIR, config.CLIP_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# ---- Derive camera sources from env overrides (JSON) ----
def _source_value(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value

for _cam_id, _cfg in config.CAMERA_STREAMS.items():
    if isinstance(_cfg.get("source"), (str, int)):
        if isinstance(_cfg["source"], str):
            _cfg["source"] = _source_value(_cfg["source"])