# SAS Reserve — Smart Facility & Resource Reservation System

A premium web platform for institutional facility and resource reservations:
gymnasium, cafeteria, audio-visual room, accreditation resources, tables,
chairs, sound systems, microphones, projectors, and other event equipment.

The system pairs a **Django + Django REST Framework** API (PostgreSQL-ready)
with a **Vite + React + TypeScript + Tailwind CSS** frontend.

```
/frontend   Vite + React 19 + TypeScript + Tailwind CSS v4
/backend    Django 6 + Django REST Framework + SimpleJWT
```

## Features

- **Reservation wizard** — 5 steps (facility → schedule → resources → event
  details → review) with live availability checking, conflict detection,
  smart resource recommendations, and proposed alternative schedules.
- **Approval workflow** — pending → approved/active/completed with reject,
  request-changes, and cancel flows, full activity timeline, and
  notifications for every transition.
- **QR check-in / check-out** — per-reservation QR codes, a staff scanning
  interface (camera + manual entry), and a post-event inspection checklist
  with photo upload and damage reporting.
- **Calendar** — month / week / day views with facility, equipment, and
  status filters.
- **Equipment inventory** — availability computed live from reservations and
  open maintenance records, plus per-item maintenance history.
- **Analytics & reports** — utilization, trends, peak periods, cancellation
  and no-show rates, with CSV / Excel (XLSX) / PDF exports.
- **Roles** — Administrator, SAS Staff, and Requester with permission-based
  access to every endpoint and screen.

## Quick start

### 1. Backend (Django)

```bash
cd backend
pipenv install            # or: pip install -r equivalent from Pipfile
python manage.py migrate
python manage.py seed     # reference data: users, facilities, equipment
python manage.py runserver
```

The seed creates three accounts (all passwords are dev-only):

| Username     | Password        | Role            |
| ------------ | --------------- | --------------- |
| `admin`      | `admin1234`     | Administrator   |
| `staff`      | `staff1234`     | SAS Staff       |
| `requester`  | `requester1234` | Requester       |

`python manage.py seed --with-demo-reservations` additionally creates a few
clearly-labelled `[DEMO]` reservations for previewing the UI. Demo data is
always opt-in — the default seed contains only reference data.

**PostgreSQL (target architecture).** The app falls back to SQLite for
zero-config local development. To use PostgreSQL, set `DATABASE_URL`:

```bash
export DATABASE_URL="postgres://USER:PASSWORD@localhost:5432/sas_reserve"
python manage.py migrate
```

Other env vars: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
`CORS_ALLOWED_ORIGINS`.

### 2. Frontend (Vite)

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173
```

The Vite dev server proxies `/api` and `/media` to `http://127.0.0.1:8000`,
so both servers must be running. Sign in with one of the seeded accounts.

## Verification

```bash
cd backend && python manage.py test   # 22 tests: availability, conflicts, API workflow
cd frontend && npm run typecheck      # strict TypeScript
cd frontend && npm run build          # production bundle (code-split)
```

## API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /api/auth/login/` · `POST /api/auth/refresh/` · `GET /api/auth/me/` | JWT auth |
| `GET/POST /api/facilities/` | Facility discovery |
| `GET /api/equipment/` · `POST /api/equipment/{id}/report_issue/` | Inventory + maintenance |
| `GET/POST /api/reservations/` | Reservation list/create (conflicts → `409` with a structured report) |
| `POST /api/reservations/{id}/approve|reject|request_changes|cancel|check_in|check_out/` | Workflow actions |
| `GET /api/reservations/checkin/{code}/` | Staff QR scan lookup |
| `POST /api/availability/check/` | Conflict analysis + alternative schedules |
| `POST /api/availability/resources/` | Smart resource recommendations |
| `GET /api/calendar/events/` | Calendar event feed |
| `GET /api/analytics/*` · `GET /api/reports/*` | Analytics + exports (`csv`, `xlsx`) |

## Design system

The frontend defines its tokens once in `frontend/src/index.css`
(Tailwind v4 `@theme`): a calm neutral palette with pastel semantic status
colors, Inter typography, soft shadows, and a shared radius scale. All pages
are composed from the primitives in `frontend/src/components/ui/` and share
the same layout shell (`AppShell`), so every screen belongs to one product.

## Notes

- The availability engine counts `PENDING`, `APPROVED`, and `ACTIVE`
  reservations as resource-holding, so pending requests block their slots
  (and are immediately visible to other users as conflicts).
- Photo uploads are stored under `backend/media/` during development.
- The PDF export path uses the browser's print flow (`window.print()`), which
  produces a clean, print-styled report from the preview table.