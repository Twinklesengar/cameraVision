from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.sqlite_db import Base
from app.utils.timeutil import utcnow

class CameraStream(Base):
    __tablename__ = "camera_streams"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)  # int index or RTSP/HTTP URL
    type = Column(String, default="gate")    # gate, productivity, security
    resolution = Column(String, nullable=True)
    fps_limit = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Personnel(Base):
    __tablename__ = "personnel"

    person_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, default="Employee") # Employee, Student, Teacher, Visitor, Admin
    department = Column(String, default="General")
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    enrolled_at = Column(DateTime, default=utcnow)
    metadata_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)

    attendance_logs = relationship("AttendanceLog", back_populates="personnel")
    productivity_logs = relationship("ProductivityLog", back_populates="personnel")
    health_logs = relationship("HealthLog", back_populates="personnel")
    assets = relationship("AssetLog", back_populates="owner")

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, ForeignKey("personnel.person_id"), index=True, nullable=True)
    name = Column(String, default="UNKNOWN")
    timestamp = Column(DateTime, default=utcnow, index=True)
    event_type = Column(String, default="ENTRY") # ENTRY, EXIT, GATE_PASS
    camera_id = Column(String, default="cam_entrance")
    confidence = Column(Float, default=0.0)
    is_spoof = Column(Boolean, default=False)

    personnel = relationship("Personnel", back_populates="attendance_logs")

class ProductivityLog(Base):
    __tablename__ = "productivity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, ForeignKey("personnel.person_id"), index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    status = Column(String, default="PRODUCTIVE") # PRODUCTIVE, LAZY_IDLE, BUNKING, PHONE_DISTRACTED
    duration_seconds = Column(Integer, default=0)
    camera_id = Column(String, default="cam_workspace")
    notes = Column(String, nullable=True)

    personnel = relationship("Personnel", back_populates="productivity_logs")

class HealthLog(Base):
    __tablename__ = "health_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, ForeignKey("personnel.person_id"), index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    drowsiness_detected = Column(Boolean, default=False)
    eye_aspect_ratio = Column(Float, default=0.30)
    posture_status = Column(String, default="GOOD") # GOOD, SLOUCHING, FALL_RISK
    fatigue_score = Column(Float, default=0.0)
    camera_id = Column(String, default="cam_workspace")

    personnel = relationship("Personnel", back_populates="health_logs")

class AssetLog(Base):
    __tablename__ = "asset_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_name = Column(String, nullable=False, index=True)
    owner_person_id = Column(String, ForeignKey("personnel.person_id"), nullable=True)
    last_seen_bbox = Column(String, default="[]") # "[x1, y1, x2, y2]"
    camera_id = Column(String, default="cam_workspace")
    status = Column(String, default="NORMAL") # NORMAL, MOVED, DISPLACED_MISSING, THEFT_SUSPECTED
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("Personnel", back_populates="assets")

class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    alert_type = Column(String, nullable=False) # UNKNOWN_FACE, THEFT_ATTEMPT, BUNKING_EXCEEDED, PHONE_OVERUSE, DROWSINESS_WARNING
    severity = Column(String, default="WARNING") # INFO, WARNING, CRITICAL
    description = Column(Text, nullable=False)
    camera_id = Column(String, default="cam_main")
    person_id = Column(String, nullable=True)
    is_resolved = Column(Boolean, default=False)


class CameraActivityLog(Base):
    __tablename__ = "camera_activity_log"
    __table_args__ = (UniqueConstraint("camera_id", "bucket", name="uq_camera_activity_bucket"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, nullable=False, index=True)
    bucket = Column(DateTime, index=True, nullable=False)  # minute start (UTC, naive)
    samples = Column(Integer, default=0)
    avg_motion = Column(Float, default=0.0)
    peak_motion = Column(Float, default=0.0)
    crowd_seconds = Column(Integer, default=0)
    people_seen = Column(Integer, default=0)
    analyzed_count = Column(Integer, default=0)
