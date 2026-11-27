# AegisVision — Unified Console (UI Plan)

Pure-HTML + Tailwind replacement for the React dashboard, plus the analysis of what makes
this an "ultimate" surveillance command center. Served directly by FastAPI (no build step).

---

## 1. Why rebuild

- React app duplicated views, hardcoded the API host, and carried orphaned MUI/Firebase pages.
- A monitored (no-build) HTML + Tailwind console is simpler to deploy (served by the same
  FastAPI process), theme-consistent, and instantly hackable.
- Backend now exposes a typed API (11 route groups) plus WS alerts — the UI just needs to
  consume it well.

## 2. Feature analysis — what makes the "ultimate" console

### Must-have (already in API, needs first-class UI)
- **Live multi-camera grid** — per-cam MJPEG feed, camera selector, online/offline badges, snapshot.
- **Live occupancy** (gate): currently-inside, peak, today entries/exits.
- **Incident feed** — severity badges, live WS push (ALERT / ALERT_RESOLVED), toast + sound, resolve.
- **Personnel roster** — Enroll via photo upload, delete; search.
- **Productivity / Health tables** — per-person state, drowsiness/posture badges.
- **Spatial assets** — register asset with **visual bbox picker** (click-drag on the camera still),
  owner, live status badges.
- **Copilot** — chat UI w/ quick-prompt chips.
- **Analytics** — Chart.js time-series (attendance/productivity/alerts) + per-person daily summary.

### New "ultimate" additions in this build
- **Auth + admin panel**: login page, JWT session, admin-only actions (enroll/delete, asset CRUD,
  alert resolve, system logs). Operator read-only view.
- **System health**: camera worker status, uptime, DB + vector counts, live log tail, config summary.
- **Occupancy trend chart** + alert severity breakdown on the dashboard.
- **Global search** across personnel + incidents.
- **Responsive dark "command-center" theme**; keyboard shortcuts (1–0 to switch views, `/` search).

### Next (post-MVP, in PLAN.md phases)
- Export CSV of any table · multi-site health · watchlist/biometry · retention policy UI ·
  real estate/floor heatmaps · PWA offline · i18n.

---

## 3. UI architecture (pure HTML + Tailwind, no framework)

```
frontend/
  login.html                  # admin/operator sign-in
  index.html                  # console shell: sidebar + topbar + <main id="view">
  css/app.css                 # small custom layer (scrollbars, animations) on top of Tailwind CDN
  js/api.js                   # fetch wrapper (Authorization header, 401→login), WS helper
  js/main.js                  # router (hash-based), sidebar/state, toast, clock, logout
  js/views/dashboard.js       # KPIs, occupancy, occupancy trend + alert chart
  js/views/live.js            # MJPEG grid, snapshot, asset bbox picker overlay
  js/views/attendance.js      # in/out table + per-person day summary modal
  js/views/productivity.js    # per-person state table
  js/views/health.js          # drowsiness/posture/fatigue table
  js/views/assets.js          # register/list/delete assets (uses bbox picker)
  js/views/incidents.js       # alert feed, filter, resolve
  js/views/copilot.js         # chat
  js/views/analytics.js       # Chart.js hourly series (multi-metric)
  js/views/personnel.js       # enroll modal + table + delete (ADMIN)
  js/views/system.js          # system health / logs / config (ADMIN)
```

- **Tailwind**: Play CDN (`<script src="https://cdn.tailwindcss.com">`) + inline `tailwind.config`.
- **Charts**: Chart.js via CDN. **WS**: `/api/stream/ws` (alert push + PONG keepalive).
- **State**: `localStorage` holds the session token; every API call retries with token and
  redirects to `login.html` on 401.

## 4. Views / routes map

| View key | Nav label | Backend feeds |
|---|---|---|
| `dashboard` | Command Center | `/api/analytics/dashboard`, `/occupancy`, `/timeseries`, WS |
| `live` | Live Cameras | `/api/stream/video_feed`, `/cameras`, `/snapshot`, WS |
| `attendance` | Attendance | `/api/analytics/attendance`, `/person/{id}/{day}` |
| `productivity` | Productivity | `/api/analytics/productivity` |
| `health` | Health Sentinel | `/api/analytics/health` |
| `assets` | Asset Memory | `/api/assets`, `/api/analytics/assets`, `/api/stream/snapshot` |
| `incidents` | Incident Feed | `/api/alerts`, `/resolve/{id}`, `/types`, WS |
| `copilot` | AI Copilot | `/api/copilot/query` |
| `analytics` | Analytics | `/api/analytics/timeseries` |
| `personnel` | Personnel (ADMIN) | `/api/personnel`, `/enroll`, `/{id}` DELETE |
| `system` | Admin / System (ADMIN) | `/api/system/health`, `/logs`, `/api/auth/me` |

## 5. Auth model (backed by the new `/api/auth/*`)

- `POST /api/auth/login` `{username,password}` → `{token, role}` against env `ADMIN_USERNAME`/`ADMIN_PASSWORD`.
- Token is a dependency-free HMAC-SHA256 signed payload (`sub`,`role`,`exp`), `JWT_SECRET` keyed.
- Mutating/admin routes carry `Depends(require_admin)` → 401/403 otherwise.
- Frontend stores token, sends `Authorization: Bearer…`, drops to `login.html` on 401.

## 6. Definition of done

- `localhost:8000/login.html` signs in; console opens; every nav view renders real API data.
- Camera tiles stream MJPEG; offline cams show placeholder.
- New alert → WS toast/sound + incident feed rows immediately; admin can resolve.
- bbox picker lets one register an asset by dragging over the snapshot.
- Tests green (existing 19 + auth/system-health).