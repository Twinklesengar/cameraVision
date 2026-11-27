import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.config import config
from app.services.camera_registry import camera_registry
from app.services.analysis_scheduler import analysis_scheduler
from app.services.face_engine import face_engine
from app.services.productivity_engine import productivity_engine
from app.services.health_sentinel import health_sentinel
from app.services.spatial_memory import spatial_memory
from app.services.alert_service import emit_alert
from app.db.sqlite_db import SessionLocal
from app.db.models import AttendanceLog


@dataclass
class CameraFrame:
    camera_id: str
    timestamp: float
    jpeg: bytes
    detections: list = field(default_factory=list)
    offline: bool = False


class CameraWorker(threading.Thread):
    """Runs the per-camera pipeline under a low-compute time budget.

    The expensive face pipeline does not run on every captured frame. Each
    frame only pays for: grab, downscale-to-grayscale, and a cheap frame-diff.
    The full detect → track → embed → label → analytics pipeline runs at most
    once per `CAMERA_ANALYZE_INTERVAL_SEC`, and only when motion is seen —
    unless the max-gap timer forces a re-analysis so gate/occupancy never goes
    stale in a perfectly still scene. JPEG publish is throttled separately, so
    idle cameras cost almost nothing beyond capture.
    """

    ATTENDANCE_COOLDOWN_SECONDS = 30

    def __init__(self, camera_id: str, camera_config: dict):
        super().__init__(name=f"cam-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.cam_label = camera_config.get("name", camera_id)
        self.source = camera_config.get("source", 0)
        self.cam_type = camera_config.get("type", "gate")
        self.resolution = camera_config.get("resolution") or config.CAMERA_RESOLUTION
        self.fps_limit = camera_config.get("fps_limit") or config.CAMERA_FPS_LIMIT

        self._latest = CameraFrame(camera_id=camera_id, timestamp=0.0, jpeg=b"", offline=True)
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._last_error: Optional[str] = "Waiting for the first frame"
        self._presence: dict = {}
        self._last_attendance: dict = {}
        self._peak = 0
        self._today_entries = 0
        self._today_exits = 0

        # Low-compute bookkeeping (worker thread only).
        self._last_analyze = 0.0
        self._last_publish = 0.0
        self._start_time = time.time()
        self._prev_gray: Optional[np.ndarray] = None
        self._analyzed_frames = 0
        self._captured_frames = 0
        self._motion_level = 0.0
        self._scene_state = "IDLE"
        self._people_count = 0
        self._history: deque = deque(maxlen=720)
        self._last_history_ts = 0.0

        # Feed health + fleet ops.
        self._last_frame_time = 0.0
        self._offline_since: Optional[float] = None

        # Per-minute activity accumulator, drained by the fleet housekeeper.
        self._activity_minutes: Dict[str, dict] = {}

        # Evidence clip buffer (bounded ring of (ts, jpeg) at CLIP_FPS).
        self._clip_buf: deque = deque(maxlen=int(config.CLIP_SECONDS * config.CLIP_FPS))
        self._last_clip_frame = 0.0
        self._last_clip_save = 0.0
        self._clip_lock = threading.Lock()

        # Analysis telemetry + adaptive capture pacing.
        self._analysis_latency_ms: deque = deque(maxlen=50)
        self._defer_stamps: deque = deque(maxlen=64)
        self._adaptive_fps = int(self.fps_limit or 0)

    # ---- lifecycle ----
    def run(self):
        while not self._shutdown.is_set():
            self._capture_loop()
            if self._shutdown.wait(config.CAMERA_RECONNECT_SECONDS):
                break

    def stop(self):
        self._shutdown.set()

    def _capture_loop(self):
        cap = cv2.VideoCapture(self.source)
        try:
            if not cap.isOpened():
                raise RuntimeError(f"unable to open source {self.source!r}")
            width, height = (int(v) for v in self.resolution.split("x"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            last_frame_time = 0.0

            while not self._shutdown.is_set():
                frame_interval = self._frame_interval()
                ok, frame = cap.read()
                if not ok:
                    break
                now = time.time()
                if frame_interval and (now - last_frame_time) < frame_interval:
                    time.sleep(max(0.0, frame_interval - (now - last_frame_time)))
                last_frame_time = time.time()
                self._process_frame(frame, now)
                self._update_adaptive_fps(now)

            self._publish_offline("Stream not readable")
            self._save_clip("feed-lost")
        except Exception as e:
            self._publish_offline(str(e))
            print(f"[Camera {self.camera_id}] {e}")
        finally:
            cap.release()

    def _frame_interval(self) -> float:
        fps = self._adaptive_fps
        return 1.0 / fps if fps > 0 else 0.0

    def _update_adaptive_fps(self, now: float):
        """Halve capture FPS while the shared analysis budget is starved, then
        restore it once the pool breathes. Keeps feeds live under load."""
        cap = max(1, int(self.fps_limit or config.CAMERA_FPS_LIMIT))
        if len(self._defer_stamps) >= 3 and (now - self._defer_stamps[-3]) < 10.0:
            target = max(config.CAMERA_MIN_FPS, cap // 2)
            if 0 < target < self._adaptive_fps:
                self._adaptive_fps = target
        elif self._adaptive_fps != cap and self._defer_stamps and (now - self._defer_stamps[-1]) > 30.0:
            self._adaptive_fps = cap

    # ---- low-compute decisioning ----
    @staticmethod
    def _motion_diff(gray: np.ndarray, prev: Optional[np.ndarray]) -> float:
        if prev is None or prev.shape != gray.shape:
            return 0.0
        return float(cv2.absdiff(gray, prev).mean())

    def _should_analyze(self, motion: float, now: float) -> tuple:
        """Return (should_run, force). `force` bypasses the global rate bucket."""
        if not config.CAMERA_MOTION_GATE:
            return (now - self._last_analyze >= config.CAMERA_ANALYZE_INTERVAL_SEC, False)
        elapsed = now - self._last_analyze
        if elapsed < config.CAMERA_ANALYZE_INTERVAL_SEC:
            return (False, False)
        active = motion >= config.CAMERA_MOTION_THRESHOLD
        stale = elapsed >= config.CAMERA_ANALYZE_MAX_GAP_SEC
        return (active or stale, stale)

    def _resolve_scene(self, motion: float):
        if motion >= 0.35:
            self._scene_state = "CROWDED"
        elif motion >= 0.15:
            self._scene_state = "BUSY"
        elif motion >= 0.05:
            self._scene_state = "ACTIVE"
        else:
            self._scene_state = "IDLE"

    # ---- pipeline ----
    def _process_frame(self, frame: np.ndarray, now: float):
        self._captured_frames += 1
        self._last_frame_time = now
        self._offline_since = None

        gray_small = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
        motion = self._motion_diff(gray_small, self._prev_gray)
        self._prev_gray = gray_small

        alpha = config.CAMERA_MOTION_EMA_ALPHA
        self._motion_level = alpha * motion + (1 - alpha) * self._motion_level
        self._resolve_scene(self._motion_level)

        should_run, force = self._should_analyze(motion, now)
        analyzed = False
        if should_run and (force or analysis_scheduler.try_acquire()):
            self._last_analyze = now
            self._analyzed_frames += 1
            analyzed = True
            annotated, detections = self._run_face_pipeline(frame)
            self._people_count = len(detections)
            self._consume_detections(detections, annotated, now)
            self._publish_frame(annotated, now, force=True)
            self._maybe_trigger_clip(now)
        else:
            if should_run:
                self._defer_stamps.append(now)
            self._publish_frame(frame, now, force=False)
        self._maybe_capture_clip(frame, now)
        self._record_history(now, analyzed)

    def _run_face_pipeline(self, frame: np.ndarray):
        """Offload the expensive detection to the shared, bounded pool."""
        t0 = time.perf_counter()
        try:
            future = analysis_scheduler.run(lambda f=frame: face_engine.process_frame(f))
            result = future.result(timeout=config.CAMERA_ANALYSIS_TIMEOUT_SEC)
        except Exception:
            result = (frame, [])
        self._analysis_latency_ms.append((time.perf_counter() - t0) * 1000.0)
        return result

    # ---- fleet ops: evidence clips + minute-level activity ----
    def _maybe_capture_clip(self, frame: np.ndarray, now: float):
        if not config.CLIP_ENABLED:
            return
        if now - self._last_clip_frame < (1.0 / config.CLIP_FPS):
            return
        self._last_clip_frame = now
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            self._clip_buf.append((now, buf.tobytes()))

    def _maybe_trigger_clip(self, now: float):
        if (now - self._last_clip_save) < config.CLIP_COOLDOWN_SEC:
            return None
        if self._scene_state == "CROWDED" or self._people_count >= config.CAMERA_CROWD_ALERT_AT:
            self._last_clip_save = now
            return self._save_clip("crowd")
        return None

    def _save_clip(self, reason: str):
        if not config.CLIP_ENABLED:
            return None
        with self._clip_lock:
            frames = list(self._clip_buf)
        if len(frames) < 4:
            return None
        safe = "".join(ch for ch in reason if ch.isalnum() or ch in ("-", "_")) or "event"
        config.CLIP_DIR.mkdir(parents=True, exist_ok=True)
        path = config.CLIP_DIR / f"{self.camera_id}_{int(time.time())}_{safe}.mp4"
        first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
        h, w = first.shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), config.CLIP_FPS, (w, h))
        if not writer.isOpened():
            print(f"[Camera {self.camera_id}] no MP4 codec; evidence clip skipped")
            return None
        with self._clip_lock:
            frames_now = list(self._clip_buf)
        try:
            for _, jpeg in frames_now:
                frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    writer.write(frame)
        finally:
            writer.release()
        return str(path)

    def _accumulate_activity(self, now: float, analyzed: bool):
        key = datetime.fromtimestamp(now, tz=timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
        agg = self._activity_minutes.get(key)
        if agg is None:
            agg = {
                "bucket": key, "motion_sum": 0.0, "motion_n": 0, "peak_motion": 0.0,
                "crowd_seconds": 0, "people_seen": 0, "analyzed_count": 0,
            }
            self._activity_minutes[key] = agg
        agg["motion_sum"] += float(self._motion_level) * 100.0
        agg["motion_n"] += 1
        agg["peak_motion"] = max(agg["peak_motion"], float(self._motion_level) * 100.0)
        if self._scene_state in ("BUSY", "CROWDED"):
            agg["crowd_seconds"] += 1
        agg["people_seen"] = max(agg["people_seen"], self._people_count)
        if analyzed:
            agg["analyzed_count"] += 1

    def drain_activity(self) -> list:
        """Return the accumulated minute-buckets and clear them. Housekeeper."""
        with self._lock:
            minutes = list(self._activity_minutes.values())
            self._activity_minutes.clear()
        entries = []
        for agg in minutes:
            n = max(1, agg["motion_n"])
            entries.append({
                "camera_id": self.camera_id,
                "bucket": agg["bucket"],
                "samples": n,
                "avg_motion": round(agg["motion_sum"] / n, 1),
                "peak_motion": round(agg["peak_motion"], 1),
                "crowd_seconds": agg["crowd_seconds"],
                "people_seen": agg["people_seen"],
                "analyzed_count": agg["analyzed_count"],
            })
        return entries

    def is_offline(self, now: float) -> bool:
        with self._lock:
            if self._offline_since is not None:
                return (now - self._offline_since) >= config.CAMERA_OFFLINE_GRACE_SEC
            if self._last_frame_time and (now - self._last_frame_time) >= config.CAMERA_OFFLINE_GRACE_SEC:
                return True
            return False

    def list_clips(self) -> list:
        if not config.CLIP_DIR.exists():
            return []
        clips = []
        for p in sorted(config.CLIP_DIR.glob(f"{self.camera_id}_*.mp4"), reverse=True):
            clips.append({
                "camera_id": self.camera_id,
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "timestamp": p.stat().st_mtime,
            })
        return clips

    def _record_history(self, now: float, analyzed: bool):
        if now - self._last_history_ts < 1.0:
            return
        self._last_history_ts = now
        with self._lock:
            self._history.append({
                "t": round(now, 1),
                "motion_score": round(self._motion_level * 100.0, 1),
                "scene_state": self._scene_state,
                "people_seen": self._people_count,
                "analyzed": analyzed,
            })
            self._accumulate_activity(now, analyzed)

    def get_history(self, limit: int = 60) -> list:
        with self._lock:
            return list(self._history)[-limit:]

    def _consume_detections(self, detections: List[Dict[str, Any]], annotated: np.ndarray, now: float):
        for det in detections:
            if self.cam_type == "gate":
                self._handle_gate_detection(det, now)
            else:
                person_id = det["person_id"]
                productivity_engine.update_presence(
                    person_id, True, self.camera_id, frame=annotated, face_bbox=det["bbox"]
                )
                health_sentinel.analyze_health_and_posture(
                    person_id, annotated, det["bbox"], camera_id=self.camera_id
                )
        if self.cam_type != "gate":
            spatial_memory.monitor(self.camera_id, annotated, detections)
        else:
            self._evict_gone_persons(now)

    def _publish_frame(self, frame: np.ndarray, now: float, force: bool):
        if not force and (now - self._last_publish) < config.CAMERA_JPEG_PUBLISH_INTERVAL_SEC:
            return
        self._last_publish = now
        ok, buffer = cv2.imencode(".jpg", frame)
        jpeg = buffer.tobytes() if ok else b""
        with self._lock:
            self._latest = CameraFrame(
                camera_id=self.camera_id,
                timestamp=now,
                jpeg=jpeg,
                detections=[],
            )
            self._offline_since = None
            self._last_error = None

    # ---- gate occupancy (in/out, live count, peak, totals) ----
    def _handle_gate_detection(self, det: dict, now: float):
        person_id = det["person_id"]
        if person_id == "UNKNOWN":
            if person_id in self._last_attendance and (now - self._last_attendance[person_id]) < 30:
                return
            self._last_attendance[person_id] = now
            self._log_attendance(det, now)
            emit_alert(
                alert_type="UNKNOWN_FACE",
                severity="WARNING",
                description=f"Unregistered/Unknown individual detected at {self.camera_id}.",
                camera_id=self.camera_id,
                person_id="UNKNOWN",
            )
            return

        if person_id not in self._presence:
            self._presence[person_id] = now
            self._today_entries += 1
            self._peak = max(self._peak, len(self._presence))
            self._log_attendance(det, now)
        else:
            self._presence[person_id] = now

    def _evict_gone_persons(self, now: float):
        timeout = config.GATE_EXIT_TIMEOUT_SECONDS
        for person_id in list(self._presence.keys()):
            if now - self._presence[person_id] > timeout:
                del self._presence[person_id]
                self._today_exits += 1
                db = SessionLocal()
                try:
                    db.add(AttendanceLog(
                        person_id=person_id,
                        name=person_id,
                        confidence=0.0,
                        camera_id=self.camera_id,
                        event_type="EXIT",
                    ))
                    db.commit()
                except Exception as e:
                    db.rollback()
                    print(f"[Camera {self.camera_id} EXIT Error] {e}")
                finally:
                    db.close()

    def get_occupancy(self) -> dict:
        with self._lock:
            return {
                "camera_id": self.camera_id,
                "currently_inside": len(self._presence),
                "peak_inside": self._peak,
                "today_entries": self._today_entries,
                "today_exits": self._today_exits,
            }

    def _log_attendance(self, det: dict, now: float):
        person_id = det["person_id"]
        db = SessionLocal()
        try:
            db.add(AttendanceLog(
                person_id=person_id if person_id != "UNKNOWN" else None,
                name=det["name"],
                confidence=det["confidence"],
                camera_id=self.camera_id,
                event_type="ENTRY",
            ))
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[Camera {self.camera_id} Attendance Error] {e}")
        finally:
            db.close()

    def _publish_offline(self, message: str):
        source = str(self.source)
        if "://" in source:
            message = message.replace(source, camera_registry.redact_source(source))
        blank = np.zeros((480, 640, 3), np.uint8)
        cv2.putText(blank, f"Camera Offline ({self.cam_label})", (90, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(blank, message, (150, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 90, 90), 1)
        ok, buffer = cv2.imencode(".jpg", blank)
        with self._lock:
            if self._offline_since is None:
                self._offline_since = time.time()
            self._last_frame_time = 0.0
            self._last_error = message
            self._latest = CameraFrame(
                camera_id=self.camera_id,
                timestamp=time.time(),
                jpeg=buffer.tobytes() if ok else b"",
                offline=True,
            )

    # ---- read ----
    def get_latest(self) -> CameraFrame:
        with self._lock:
            return self._latest

    def get_status(self) -> dict:
        uptime = max(1.0, time.time() - self._start_time)
        latency = round(float(np.mean(self._analysis_latency_ms)), 1) if self._analysis_latency_ms else 0.0
        with self._lock:
            return {
                "motion_score": round(self._motion_level * 100.0, 1),
                "scene_state": self._scene_state,
                "people_seen": self._people_count,
                "analyzed_frames": self._analyzed_frames,
                "captured_frames": self._captured_frames,
                "analysis_rate": round(self._analyzed_frames / uptime, 2),
                "captured_per_analysis": round(self._captured_frames / max(1, self._analyzed_frames), 1),
                "analysis_latency_ms": latency,
                "adaptive_fps": self._adaptive_fps,
                "scheduler_deferred": len(self._defer_stamps),
                "offline_since": round(time.time() - self._offline_since, 1) if self._offline_since else None,
                "last_error": self._last_error,
                "clip_buffered_frames": len(self._clip_buf),
                "occupancy": (
                    {
                        "camera_id": self.camera_id,
                        "currently_inside": len(self._presence),
                        "peak_inside": self._peak,
                        "today_entries": self._today_entries,
                        "today_exits": self._today_exits,
                    }
                    if self.cam_type == "gate"
                    else None
                ),
            }


class CameraManager:
    """Owns one CameraWorker per active camera from the runtime registry."""

    def __init__(self):
        self.workers: dict = {}
        self._lock = threading.Lock()
        self._monitoring_enabled = False

    # ---- lifecycle ----
    def start_all(self):
        self.start_monitoring()

    def start_monitoring(self) -> dict:
        with self._lock:
            self._monitoring_enabled = True
        for cam_id, cfg in camera_registry.configs().items():
            if cfg["active"]:
                self.start(cam_id, cfg)
        return self.monitoring_status()

    def stop_monitoring(self) -> dict:
        self.stop_all()
        return self.monitoring_status()

    def monitoring_status(self) -> dict:
        with self._lock:
            return {
                "running": self._monitoring_enabled,
                "worker_count": len(self.workers),
            }

    def start(self, camera_id: str, cam_config: Optional[dict] = None):
        with self._lock:
            if not self._monitoring_enabled or camera_id in self.workers:
                return
            cam_config = cam_config or camera_registry.get(camera_id)
            if cam_config is None or not cam_config["active"]:
                return
            worker = CameraWorker(camera_id, cam_config)
            worker.start()
            self.workers[camera_id] = worker

    def stop(self, camera_id: str):
        with self._lock:
            worker = self.workers.pop(camera_id, None)
        if worker is not None:
            worker.stop()
            worker.join(timeout=5)

    def stop_all(self):
        with self._lock:
            self._monitoring_enabled = False
            workers = list(self.workers.values())
            self.workers.clear()
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=5)

    def restart(self, camera_id: str):
        self.stop(camera_id)
        cfg = camera_registry.get(camera_id)
        if cfg and cfg["active"]:
            self.start(camera_id, cfg)
        else:
            self.stop(camera_id)

    # ---- runtime CRUD (delegates to the registry, then applies) ----
    def add_camera(self, camera_id: str, name: str, source: Any, cam_type: str,
                   resolution: Optional[str] = None, fps_limit: Optional[int] = None) -> dict:
        cfg = camera_registry.add(camera_id, name, source, cam_type, resolution, fps_limit)
        self.start(camera_id, cfg)
        return cfg

    def update_camera(self, camera_id: str, **fields) -> Optional[dict]:
        cfg = camera_registry.update(camera_id, **fields)
        if cfg is None:
            return None
        if cfg["active"]:
            if camera_id in self.workers:
                self.restart(camera_id)
            else:
                self.start(camera_id, cfg)
        else:
            self.stop(camera_id)
        return cfg

    def set_active(self, camera_id: str, active: bool) -> Optional[dict]:
        cfg = camera_registry.set_active(camera_id, active)
        if cfg is None:
            return None
        if active:
            self.start(camera_id, cfg)
        else:
            self.stop(camera_id)
        return cfg

    def remove_camera(self, camera_id: str) -> bool:
        self.stop(camera_id)
        if camera_registry.delete(camera_id):
            return True
        if camera_registry.get(camera_id) is not None:
            camera_registry.set_active(camera_id, False)
            return True
        return False

    # ---- read ----
    def get_latest(self, camera_id: str) -> CameraFrame:
        worker = self.workers.get(camera_id)
        if worker is not None:
            return worker.get_latest()
        return self._static_offline(camera_id)

    def get_camera(self, camera_id: str) -> Optional[dict]:
        cfg = camera_registry.get(camera_id)
        if cfg is None:
            return None
        return self._serialize(cfg)

    def list_cameras(self) -> List[dict]:
        cameras = []
        for cam_id, cfg in camera_registry.configs().items():
            cameras.append(self._serialize(cfg))
        return cameras

    def _serialize(self, cfg: dict) -> dict:
        cam_id = cfg["camera_id"]
        worker = self.workers.get(cam_id)
        if worker is not None:
            frame = worker.get_latest()
            cam = {
                "camera_id": cam_id,
                "name": cfg["name"],
                "source": cfg["source"],
                "type": cfg.get("type", "gate"),
                "active": bool(cfg.get("active", True)),
                "resolution": cfg.get("resolution"),
                "fps_limit": cfg.get("fps_limit"),
                "online": bool(frame.timestamp and frame.jpeg and not frame.offline),
                "last_frame_age": round(float(time.time() - frame.timestamp), 1) if frame.timestamp else None,
            }
            cam.update(worker.get_status())
            cam["history"] = worker.get_history(limit=60)
            return cam
        return {
            "camera_id": cam_id,
            "name": cfg["name"],
            "source": cfg["source"],
            "type": cfg.get("type", "gate"),
            "active": bool(cfg.get("active", True)),
            "resolution": cfg.get("resolution"),
            "fps_limit": cfg.get("fps_limit"),
            "online": False,
            "last_frame_age": None,
            "motion_score": 0.0,
            "scene_state": "OFFLINE",
            "people_seen": 0,
            "captured_per_analysis": 0.0,
            "analysis_latency_ms": 0.0,
            "adaptive_fps": cfg.get("fps_limit") or 0,
            "scheduler_deferred": 0,
            "offline_since": None,
            "last_error": "Camera is disabled" if not cfg.get("active", True) else "Camera worker is not running",
            "clip_buffered_frames": 0,
            "occupancy": None,
            "history": [],
        }

    @staticmethod
    def _static_offline(camera_id: str) -> CameraFrame:
        blank = np.zeros((480, 640, 3), np.uint8)
        cv2.putText(blank, f"Camera Offline ({camera_id})", (90, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        ok, buffer = cv2.imencode(".jpg", blank)
        return CameraFrame(camera_id=camera_id, timestamp=time.time(), jpeg=buffer.tobytes() if ok else b"", offline=True)


camera_manager = CameraManager()