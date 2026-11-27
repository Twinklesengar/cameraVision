# AGENTS.md

Guidelines for AI agents (and contributors) working in this repository.

## Project purpose

**AegisVision — AI Enterprise Surveillance Platform** (a.k.a. `AegisVision`).

A production-grade, plug-and-play face-recognition monitoring system for offices,
schools, colleges and workplaces. It streams CCTV/webcam feeds, identifies people
in real time against an enrolled roster, tags UNKNOWN faces (never saving new files),
and derives behavioral analytics:

- Attendance (in/out at gates), live occupancy counts
- Productivity: active / idle-lazy / bunking / phone-distraction times
- Health: drowsiness, fatigue, posture
- Spatial anti-theft and asset-displacement memory
- Real-time incident alerts + a Generative-AI decision copilot

## Tech stack & architecture

- **Backend:** Python 3.12+, FastAPI, Uvicorn, SQLAlchemy + SQLite, ChromaDB (cosine vector index), OpenCV, `insightface`/ONNX (SCRFD+ArcFace, default) with `face_recognition`/dlib fallback, watchdog, Google GenAI (`gemini-2.5-flash`). Dependencies are listed in `backend/requirements.txt` and installed from the root `requirements.txt`.
- **Frontend:** vanilla-JS + Tailwind CSS, static SPA served by FastAPI itself (no bundler/build step); fetch wrapper + WebSocket alert feed in `frontend/js/`.
- **Data dirs (runtime, git-ignored):** `data/known_persons/` (plug-and-play roster), `data/vector_db/` (ChromaDB), `data/surveillance.db` (SQLite), `data/logs/`.

Directory map (the *v2* architecture — see PLAN Phase 0 re: legacy cleanup):

```
backend/
  main.py                       FastAPI entry (lifespan: init DB, sync roster, start watcher)
  app/
    config.py                   Central config/constants/thresholds & camera map
    db/
      sqlite_db.py              Engine/session/init
      models.py                 Personnel, AttendanceLog, ProductivityLog, HealthLog, AssetLog, IncidentAlert
      vector_db.py              ChromaDB face-embedding upsert/query/delete (+ dim self-heal)
    services/
      face_backend.py           Recognition backend (insightface/ONNX 512-d or dlib 128-d, auto-fallback)
      face_engine.py            Detect → liveness → embed → VectorDB match → UNKNOWN tagging + HUD draw
      ingestion_service.py      Plug-and-play folder/photo/JSON rostering + directory watcher
      productivity_engine.py    active/lazy/bunk/phone-status state machine
      health_sentinel.py        drowsiness/posture/fatigue telemetry
      spatial_memory.py         Asset-region displacement / anti-theft rules
      genai_engine.py           Gemini Copilot Q&A (+ rule-based fallback)
      alert_dispatcher.py       WebSocket fan-out for live alerts
      alert_service.py          Persist + WS broadcast + external push on new IncidentAlert
      notify.py                 Config-gated push: Telegram bot + JSON webhook (best-effort)
      rule_engine.py            Background rule-escalation sweep (UNKNOWN×3, phone-overuse, drowsiness)
      logging_service.py        Rotating file + console logging under data/logs
    routes/
      stream.py                 MJPEG video_feed + WS endpoint
      personnel.py              enroll/delete personnel
      analytics.py              dashboard + attendance/productivity/health/assets
      alerts.py                 list/resolve alerts
      copilot.py                POST /api/copilot/query
      assets.py                 register/list/delete tracked assets (spatial anti-theft)
      auth.py · system.py · metrics.py
frontend/
  index.html                    Tailwind dashboard shell (served by FastAPI at site root)
  js/{api,main}.js              fetch wrapper + WS helper, tab router
  js/views/*.js                 live · personnel · analytics · productivity · health · incidents · assets · copilot · system
  css/app.css · login.html
docs/diagrams/*.svg              architecture, recognition pipeline, data model, deployment
legacy: backend/functions/ admin/ models/ settings/ tools/  ← Phase 0 cleanup (pickle + Firebase). Do not extend.
```

## Non-negotiables (do not break)

1. **UNKNOWN faces must never be written to disk** and must be visibly labeled on-frame (`UNKNOWN FACE`).
2. **Plug-and-play roster:** dropping `<person_id>_<Name>/` with `info.json` + photos into
   `data/known_persons/` must auto-register (startup sync + live watchdog).
3. **VectorDB + SQLite must stay in sync** on enroll/delete.
4. Entrance/attendance logs are cooldown-throttled (30 s per person) per camera.
5. Frontend never hardcodes a production host — same-origin requests through
   `frontend/js/api.js` (relative `/api` paths + WebSocket to `location.host`).

## Conventions

- Python: typed signatures, one service per file, route files stay thin (logic → services), SQLAlchemy sessions opened/closed in `try/finally`, Pydantic schemas for API responses.
- Frontend: views are plain JS modules (`frontend/js/views/*.js`) with Tailwind utility classes; native `fetch`/`WebSocket`; DOM rendering, no framework bundler.
- **Do NOT add code comments.** Self-documenting names and minimal docstrings only.
- Add tests for any new service logic under `tests/` (pytest + httpx TestClient).
- Match existing naming (snake_case Python, PascalCase components).

## How to run

```bash
# From the repository root; on Windows, use Visual Studio Developer PowerShell.
python -m venv .venv
# Activate .venv, then install CMake and a C++ compiler before pip installing on Windows.
python -m pip install -r requirements.txt
cp backend/.env.example backend/.env

# Run from backend/ with the environment activated.
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend is served by FastAPI itself (SERVE_FRONTEND=true) — open the site root.
# API docs
open http://localhost:8000/docs
```

## Verify before finishing any change

- `python -m pytest tests/ -q` — add tests alongside new logic (suite lives under `tests/`).
- Backend: `python -m compileall backend/app` or run uvicorn and hit `/`, `/docs`, `/api/analytics/dashboard`.
- Frontend: a UI change is verified by loading the served app at `/` (and `/login.html`) in a browser — no build step. `make build-frontend` checks `frontend/index.html` exists.
- TODO: lint/typecheck commands are not yet configured (frontend `eslint` script exists but is not enforced).