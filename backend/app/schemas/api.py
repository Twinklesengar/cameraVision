"""Pydantic response schemas for AegisVision API. `from_attributes` maps SQLAlchemy rows."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Personnel ----
class PersonnelOut(ORMModel):
    person_id: str
    name: str
    role: str
    department: str
    email: Optional[str] = None
    phone: Optional[str] = None
    enrolled_at: Optional[datetime] = None
    is_active: bool = True
    metadata_json: str = "{}"


class PersonnelListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[PersonnelOut] = []


# ---- Attendance ----
class AttendanceOut(ORMModel):
    id: int
    person_id: Optional[str] = None
    name: str = "UNKNOWN"
    timestamp: Optional[datetime] = None
    event_type: str = "ENTRY"
    camera_id: str = "cam_entrance"
    confidence: float = 0.0
    is_spoof: bool = False


class AttendanceListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[AttendanceOut] = []


# ---- Productivity ----
class ProductivityOut(ORMModel):
    id: int
    person_id: str
    timestamp: Optional[datetime] = None
    status: str = "PRODUCTIVE"
    duration_seconds: int = 0
    camera_id: Optional[str] = None
    notes: Optional[str] = None


class ProductivityListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[ProductivityOut] = []


# ---- Health ----
class HealthOut(ORMModel):
    id: int
    person_id: str
    timestamp: Optional[datetime] = None
    drowsiness_detected: bool = False
    eye_aspect_ratio: float = 0.30
    posture_status: str = "GOOD"
    fatigue_score: float = 0.0
    camera_id: Optional[str] = None


class HealthListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[HealthOut] = []


# ---- Assets ----
class AssetOut(ORMModel):
    id: int
    asset_name: str
    owner_person_id: Optional[str] = None
    last_seen_bbox: str = "[]"
    camera_id: str = "cam_workspace"
    status: str = "NORMAL"
    updated_at: Optional[datetime] = None


class AssetListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[AssetOut] = []


# ---- Incidents ----
class IncidentOut(ORMModel):
    id: int
    timestamp: Optional[datetime] = None
    alert_type: str
    severity: str = "WARNING"
    description: str
    camera_id: Optional[str] = None
    person_id: Optional[str] = None
    is_resolved: bool = False


class IncidentListOut(BaseModel):
    status: str = "success"
    count: int = 0
    data: List[IncidentOut] = []


# ---- Dashboard ----
class DashboardSummary(BaseModel):
    total_personnel: int = 0
    today_attendance: int = 0
    unresolved_alerts: int = 0
    total_assets: int = 0
    theft_threats: int = 0
    productive_sessions: int = 0
    phone_distractions: int = 0
    bunking_incidents: int = 0
    health_warnings: int = 0


class DashboardOut(BaseModel):
    status: str = "success"
    timestamp: str
    summary: DashboardSummary


# ---- Occupancy & person daily summary (Phase 2) ----
class OccupancyOut(BaseModel):
    camera_id: str
    currently_inside: int = 0
    peak_inside: int = 0
    total_entries: int = 0
    total_exits: int = 0


class PersonDailyOut(BaseModel):
    person_id: str
    date: str
    active_seconds: int = 0
    idle_seconds: int = 0
    bunk_seconds: int = 0
    phone_seconds: int = 0
    productive_score: float = 0.0
    entries: int = 0
    exits: int = 0


# ---- Copilot ----
class CopilotQueryRequest(BaseModel):
    query: str


class CopilotQueryOut(BaseModel):
    status: str = "success"
    query: str
    response: str