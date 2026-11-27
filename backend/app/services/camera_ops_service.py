"""Fleet housekeeper: offline alerting, activity persistence, retention.

Runs once per `CAMERA_OPS_SWEEP_SEC` in a daemon thread:
- detects cameras whose feed has been dead for `CAMERA_OFFLINE_GRACE_SEC`
  and raises a `CAMERA_OFFLINE` incident alert (deduped + cooldown-gated),
  auto-resolving it when the feed comes back;
- drains each worker's per-minute activity into `CameraActivityLog`;
- prunes activity rows and evidence clip files beyond their retention windows.
"""

import threading
import time
from datetime import timedelta

from app.config import config
from app.db.sqlite_db import SessionLocal
from app.db.models import CameraActivityLog
from app.services.alert_service import emit_alert, resolve_camera_alerts, has_pending_alert
from app.utils.timeutil import utcnow


class CameraOpsService:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_offline_alert: dict[str, float] = {}

    # ---- lifecycle ----
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera-ops", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop.wait(config.CAMERA_OPS_SWEEP_SEC):
            try:
                self.sweep_once()
            except Exception as e:
                print(f"[CameraOps] sweep error: {e}")

    # ---- per-sweep work ----
    def sweep_once(self):
        now = time.time()
        for cam in self._workers():
            self._check_feed_health(cam, now)
        entries = []
        for cam in self._workers():
            entries.extend(cam.drain_activity())
        if entries:
            self.save_activity(entries)
        self.prune_activity()
        self.prune_clips()

    def _workers(self):
        from app.services.camera_manager import camera_manager

        return [w for w in camera_manager.workers.values() if getattr(w, "camera_id", None)]

    # ---- offline alerting ----
    def _check_feed_health(self, worker, now: float):
        offline = worker.is_offline(now)
        if offline and not self._offline_alerted(worker.camera_id, now):
            if not has_pending_alert(worker.camera_id, "CAMERA_OFFLINE"):
                emit_alert(
                    alert_type="CAMERA_OFFLINE",
                    severity="CRITICAL",
                    description=f"Camera {worker.camera_id} ({worker.cam_label}) feed is down or unreadable.",
                    camera_id=worker.camera_id,
                )
            self._last_offline_alert[worker.camera_id] = now
        elif not offline and self._offline_alerted(worker.camera_id, now):
            resolved = resolve_camera_alerts(worker.camera_id, "CAMERA_OFFLINE")
            if resolved:
                print(f"[CameraOps] camera {worker.camera_id} recovered — resolved {resolved} alert(s)")
            self._last_offline_alert.pop(worker.camera_id, None)

    def _offline_alerted(self, camera_id: str, now: float) -> bool:
        last = self._last_offline_alert.get(camera_id)
        return last is not None and (now - last) < config.CAMERA_OFFLINE_COOLDOWN_SEC

    # ---- activity persistence ----
    @staticmethod
    def save_activity(entries: list):
        if not entries:
            return
        db = SessionLocal()
        try:
            for e in entries:
                row = (
                    db.query(CameraActivityLog)
                    .filter_by(camera_id=e["camera_id"], bucket=e["bucket"])
                    .first()
                )
                if row is None:
                    db.add(CameraActivityLog(**e))
                    continue
                total = row.samples + e["samples"]
                if total:
                    row.avg_motion = round(
                        (row.avg_motion * row.samples + e["avg_motion"] * e["samples"]) / total, 1
                    )
                row.samples = total
                row.peak_motion = max(row.peak_motion, e["peak_motion"])
                row.crowd_seconds += e["crowd_seconds"]
                row.people_seen = max(row.people_seen, e["people_seen"])
                row.analyzed_count += e["analyzed_count"]
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[CameraOps] activity flush error: {e}")
        finally:
            db.close()

    def prune_activity(self):
        cutoff = utcnow() - timedelta(days=config.CAMERA_ACTIVITY_RETENTION_DAYS)
        db = SessionLocal()
        try:
            deleted = (
                db.query(CameraActivityLog).filter(CameraActivityLog.bucket < cutoff).delete()
            )
            db.commit()
            if deleted:
                print(f"[CameraOps] pruned {deleted} stale activity buckets")
        except Exception as e:
            db.rollback()
            print(f"[CameraOps] activity prune error: {e}")
        finally:
            db.close()

    def prune_clips(self):
        if not config.CLIP_ENABLED or not config.CLIP_DIR.exists():
            return
        cutoff = time.time() - config.CLIP_RETENTION_HOURS * 3600
        removed = 0
        for p in config.CLIP_DIR.glob("*.mp4"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        if removed:
            print(f"[CameraOps] pruned {removed} stale evidence clips")


camera_ops_service = CameraOpsService()
