# AegisVision — Production Plan (v2 → v3.0)

Companion to: `AGENTS.md` (repo conventions) · `backend/app/config.py` (config) · `backend/app/db/models.py` (schema)

## 1. North-star vision

A **plug-and-play, multi-camera AI surveillance + behavioral monitoring platform** for offices,
schools, colleges and work sites:

- Enroll anyone by dropping `<person_id>_<Name>/info.json + photos` into `data/known_persons/` (or via the enrollment API).
- Stream from **CCTV / IP cameras / webcams / central server** feeds; identify **many people at once**, fast and accurately.
- Tag **UNKNOWN** faces clearly on-frame with **zero files written to disk** (optional, gated snapshot for later review).
- Track per-person and per-floor: attendance, live occupancy, active/idle-lazy/bunking time, phone-addiction windows, teaching/productive time.
- **Auto update the live dashboard** (metrics, camera grid, incident feed) pushed over WebSocket.
- Monitor **health & safety** (drowsiness, fatigue, posture, fall risk).
- **Remember spatial facts** — knows if something (asset/laptop/bag) is displaced, and whether an unauthorized/UNKNOWN person is near it.
- **Theft-proof alerting** — severity-ranked alerts with acknowledgment, WebSocket + Telegram/webhook push.
- **Generative-AI decision support** — natural-language copilot over live DB context.

---

## 2. Current state (audit, v2.0.0)

### ✅ Working
- FastAPI shell: lifespan init → SQLite tables → roster sync → directory watcher
- ChromaDB cosine face match + SQLite relational store
- Plug-and-play roster (folder + `info.json`) with live watchdog
- `face_engine.process_frame()` — detect → liveness check → embed → match → tag (**no file writes for UNKNOWN**)
- Gate attendance logging with 30 s/person cooldown; UNKNOWN_FACE incident rows
- Productivity/health engines write `ProductivityLog` / `HealthLog`
- Gemini copilot (flash + rule-based fallback) via `/api/copilot/query`
- React dashboard: 5s poll, WebSocket connect, tabs for Live/Personnel/Productivity/Health/Assets/Copilot
- `/api/personnel/enroll` saves photo+JSON to roster folder

### ❌ Gaps blocking production (each is a Phase task)
1. **Camera logic dead** — `config.CAMERA_STREAMS` (3 cams) unused; `stream.py` hardcodes `source=0`; no RTSP; every client reopens camera 0.
2. **Multi-photo embedding bug** — vector `add_person_embedding` upserts by `person_id`, so several photos per person **overwrite each other**; only one encoding survives.
3. **Real-time alerts not wired** — `alert_dispatcher.broadcast_alert()` never called; WS only PONG; browser incident feed never sees CRITICAL events.
4. **Spatial memory dead** — no asset-registration API; no object/displacement detection; `spatial_memory.process_asset_surveillance` only fires on UNKNOWN guess.
5. **No occupancy/line-crossing** — no in/out zone logic, counts, concurrent people, or per-person daily aggregates.
6. **Health = heuristics** — eye-std/Lagrange stand-in; no 68-landmark EAR from shoulders, no real fatigue/fall.
7. **Analytics shallow** — returns raw ORM rows (no Pydantic), no time-series, no per-person daily summary.
8. **Copilot single-shot** — no RAG over history, no function/tool calls, one provider.
9. **Frontend hardcodes `localhost:8000`**; no API base env; `VideoStream.jsx` uses dead `/video/*` legacy; data tables untyped.
10. **No auth** — `/api/*` fully open.
11. **Legacy cruft** — `app/functions`, `app/admin`, `app/models`, `app/settings/connectdb.py` (Firebase), pickle encodings, `videoapp.py` reference legacy stack. Confusing.
12. **Deployability** — no `requirements` (only `cmake`), no Docker, no CI, no tests, no NGINX/TLS.

---

## 3. Target architecture

```
┌─────────────── Edge/CCTV sources (RTSP / MJPEG / WebRTC) ───────────────┐
│ cam_entrance · cam_workspace · cam_restricted (config.CAMERA_STREAMS)   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
                    Background Camera Workers (pool)
                 pull frames → share-latest-frame to clients
                               ▼
                    ┌────────────────────────────┐
                    │        Frame Pipeline      │
                    │ detect(face) → track(IOU/  │
                    │ ByteTrack) → embed →       │
                    │ liveness(CNN) → vector     │
                    │ match(top-N) → label       │
                    └────────────────────────────┘
                        │        │        │        │
       AttendanceLog  AttendanceLog  ProductivityLog  HealthLog
       (in/out zone)  (occupancy)      (active/lazy/  (EAR/posture/
                   (spatial/asset)     bunk/phone)     fatigue/fall)
                        │        │        │        │
                        ▼        ▼        ▼        ▼
              ┌───────────── VectorDB(Chroma) + SQLite ─────────────┐
              │  face_embeddings | personnel | attendance |          │
              │  productivity | health | assets | incidents          │
              └───────────────────────┬──────────────────────────────┘
                                      ▼
                    ┌───────────────────────────────┐
                    │   API (FastAPI /api/*)         │
                    │   WebSocket /api/stream/ws     │
                    │   Alert dispatcher → push      │
                    └──────────────┬────────────────┘
                                   ▼
                           React Dashboard
              (Live grid · Metrics · Personnel · Productivity ·
               Health · Spatial · Copilot)
```

Layering:
- **Run-time config**: `app/config.py` (or `.env`).
- **Services** hold domain logic; **routes** serialize via Pydantic schemas (step under construction).
- **DB** is the single source of truth; **VectorDB** is the embedding index kept in sync.

---

## 4. Delivery plan by phase

> Priorities: P0 = must ship in the v3.0 MVP.

### Phase 0 — Foundation & hygiene (P0)
- [x] Pin deps: `requirements.txt`/`pyproject.toml` (fastapi, uvicorn, sqlalchemy, chromadb, opencv-python, face_recognition/dlib, watchdog, httpx, google-genai, pydantic, python-multipart, websockets).
- [x] Remove legacy dead modules: `backend/app/functions/`, `backend/app/admin/`, `backend/app/models/`, `backend/app/settings/`, `backend/app/tools/`, `backend/funnytest.py`, old `frontend/face_app/src/components/VideoStream.jsx` (point to new MJPEG), legacy `frontend/package.json` stub.
- [x] `.env` + `backend/app/config.py` moves all paths/URLs/cameras/thresholds to env-aware config; keep defaults.
- [x] Pydantic repositories: add `app/schemas/*.py` (Personnel, Attendance, Productivity, Health, Asset, Incident, Dashboard) and serialize all routes.
- [x] Error-handling/exception handlers; structured logging to `data/logs/` (rotating file + console).
- [x] Baseline tests: `tests/test_api.py` (TestClient smoke), `tests/test_ingestion.py`, `tests/test_vectors.py`.
- [x] Dockerfile + docker-compose (backend + frontend) + `Makefile` targets (`dev`, `test`, `build-frontend`, `docker-up/down`).
- **Done-when:** `uvicorn` boots cleanly with no legacy imports; API returns typed JSON; `pytest -q` green.

### Phase 1 — Multi-camera streaming & crowd identity engine (P0)
- [x] **Camera pool:** from `config.CAMERA_STREAMS` build one background capture worker per source (webcam, RTSP URL, or stream ID); share latest frame; back-pressure; auto-reconnect.
- [x] `/api/stream/video_feed?camera_id=…` serves the pushed frame instead of owning the capture.
- [x] **Tracker**: connect detections frame-to-frame (IOU) so embed+match runs every N frames, not every frame → crowd-capable.
- [ ] Split detection/embedding into optional ONNX/GPU path (e.g. `face_detection` / dlib-CNN / `onnxruntime`).
- [x] Fix multi-photo embeddings: store one vector per photo (`person_id__k`), dedupe on match via best distance.
- [ ] Liveness v2: replace Laplacian heuristic with a lightweight CNN anti-spoof model (Silent-Face-Anti-Spoofing ONNX) scaled by confidence; keep fallback.
- **`-spoof/unknown showcase`:** UNKNOWN still never saved; on-screen label `UNKNOWN FACE` + optional gated low-res snapshot in DB (flag, off by default).
- **Done-when:** 3 configured cameras stream independently; crowd scene at 10+ faces stays > 15 FPS; per-person weekly accuracy ≥ 95 P0 on a labeled clip.

### Phase 2 — Occupancy, gate zone, and behavioral analytics (P0)
- [x] **Zone/line-crossing**: gate camera computes per-person entry/exit timestamps, live occupancy, max concurrent, today/today counters.
- [x] **Person-level daily summary** — daily aggregates (active_time, idle_time, bunk_time, phone_time, productive_score) via `/api/analytics/person/{id}/{day}`.
- [x] **Analytics endpoints**: `/api/analytics/dashboard` (typed), `/api/analytics/occupancy`, `/api/analytics/person/{id}/{day}`, `/api/analytics/timeseries` (hourly grouped).
- [ ] Productivity state machine hardening (handle skips/debondes, cooldowns, multiple cameras per person).
- **Done-when:** dashboard fails show gates in/out + each person's day breakdown driven by real DB aggregates.

### Phase 3 — Spatial memory, theft & real alerting (P0)
- [x] `/api/assets` CRUD: register asset with owner + bbox; store in `AssetLog`.
- [x] Displacement detection: `spatial_memory.monitor()` per-frame region-diff → status NORMAL→DISPLACED_MISSING when owner absent; UNKNOWN near → `THEFT_SUSPECTED` → CRITICAL.
- [x] Wire `alert_dispatcher.broadcast_alert()` on every new IncidentAlert (WS push to dashboard).
- [x] Alert acknowledge/resolve broadcasts `ALERT_RESOLVED` over WS; rule-based escalation engine (`rule_engine.py`): UNKNOWN ×3 at gate → CRITICAL, phone-overuse ×3, repeated drowsiness − deduped sweep.
- [x] Push providers: Telegram bot + generic JSON webhook adapter (`notify.py`, config-gated via `TELEGRAM_BOT_TOKEN`/`NOTIFY_WEBHOOK_URL`, severity floor).
- **Done-when:** moving a laptop +1 person who is not its owner triggers CRITICAL within & offline-detectable; WS ALERT pops on dashboard instantly.

### Phase 4 — Health & safety sentinel v2 (P2)
- [ ] Add per-ring landmarks (dlib 68-point) for real EAR (drowsiness), head-pose / shoulder-line for posture (GOOD/SLOUCH/FALL).
- [ ] Fatigue emissions: evaluate consecutive EAR aboves / head-drop events into `fatigue_score` and DROWSINESS_WARNING with cooldown.
- [ ] Fall-risk: person-region aspect ratio + motion → "PERSON_DOWN" alert (school/office safety).
- [ ] Safer thresholds in config; individual baselines (per-person calibration).

### Phase 5 — Copilot & decision engine vX (P2)
- [ ] Function-calling (librarian) that run safe SQL over SQLite + returns tabular/summaries instead of static context blocks.
- [ ] Vision capability: ask "show/describe who was at gate 8am" (attachment/camera still).
- [ ] Provider abstraction: Gemini (default) / Ollama / OpenAI-compatible switch via config + env.
- [ ] RAG: index past logs/alerts (Chroma secondary collection) for long-horizon questions.
- [ ] Decision actions: suggested lock-down / notify-HR / acknowledge (surfacing action buttons).

### Phase 6 — Production hardening & deployment (P0)
- [ ] **Auth + RBAC (JWT)**: admin, security, HR, viewer scopes; protect all `/api` except `/docs`.
- [x] Env-driven API base URL; frontend builds with `VITE_API_BASE` (src/config.js).
- [ ] Testing/CI: pytest (services + routes), Playwright e2e for dashboard; GitHub Actions.
- [ ] Serve: uvicorn workers (1 = camera-writer 'main' + N=match-workers `--workers` caution with pickle state) · NGINX/TLS reverse proxy · health-check endpoints.
- [ ] Observability: structured logs, metrics endpoint (`/api/health`, `/api/stats` frames, cpu, cameras-alive).
- [ ] Docs: setup, deploy, API schema.

---

## 5. Feature roadmap (short → long term)

- **MVP (v3.0, Phases 0–3)**: multi-camera RTSP, seating tracking, UNKNOWN labeling (no files), gate occupancy + in/out, per-person day summary, spatial/theft alerts with real WS push, JWT auth, Docker, tests.
- **v3.1 (P4–6)**: health v2 (r-drowsiness, posture, fall), copilot v2 (function calling/RAG/vision), NGX + prod CI, DB indexes + partitioning for scale.
- **v4.0**: roaming multi-site central server (regional hub → central aggregation), license/site isolation, mobile app, PKI-secured edge, threat biometry (watchlists), STEM compliance, export=GDPR-style retention.

---

## 6. Acceptance criteria (Definition of Done for v3.0)

1. 3 cameras (at least one RTSP) stream concurrently on one box; dashboard shows all three.
2. Group scene: 8+ faces scene → each known face labeled at ≥90 conf (dense track) within 1 s; unknown face → `UNKNOWN FACE` in red, no file created.
3. Roster plug-and-play: dropping a new folder populates VectorDB+SQLite and appears on Personnel tab (< 2 s).
4. Gate: entry/exit, today, live occupancy, per-person in/out are computed and rendered.
5. Productivity: per-person active/idle/bunk/phone minutes update on the dashboard each poll; summaries aggregate.
6. Asset displacement → CRITICAL THEFT alert; incident live-pushed over WS; resolvable.
7. Health: DROWSINESS (above cooldown) and POSTURE/FALL events reach alerts page.
8. Copilot answers collect using function-built history (no API key → readable built-in fallback).
9. Auth: unauthenticated dashboard+API → redirect/401; admin-only routes enforced.
10. Tests green locally & CI; API fully typed; README covers setup/deploy.

---

## How to contribute against this plan

1. Start a branch per phase (or feature). Read `AGENTS.md` first — it holds the rules.
2. Implement top-down; run **backend** via `uvicorn` from `backend/`, **frontend** via `npm run dev` from `frontend/face_app`.
3. Add tests for new service logic; keep DB migrations explicit (new-scope ALTER → SQLite remap before `create_all` upgrade path).
4. Before commit: `pytest -q` + `npm run build` must pass; update `README.md` (and this plan) before finishing the phase.