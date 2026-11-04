# SAS Reserve — Smart Facility & Resource Reservation System

A web-based facility and resource reservation system for NORSU-BSC, built with Django REST Framework and React.

## Technology Stack

- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4
- **Backend:** Django, Django REST Framework, SimpleJWT
- **Database:** SQLite for local development; PostgreSQL-ready configuration
- **Containerization:** Docker and Docker Compose
- **Local frontend:** `http://localhost:5173`
- **Local backend:** `http://127.0.0.1:8000`
- **Remote server:** `103.68.157.45`
- **Planned remote application port:** `4816`

## Features

- Facility and equipment reservations
- Reservation availability and conflict detection
- Smart resource recommendations
- Reservation approval and change-request workflows
- QR-based reservation check-in and check-out
- Calendar views and reservation management
- Equipment inventory and maintenance reporting
- Analytics and report exports
- Role-based access control

---

## 1. Local Development Setup

### Backend

Open a terminal at the project root:

```powershell
cd backend
```

Activate your virtual environment if you use one, install the dependencies, and configure `backend/.env`.

Install from the project's requirements file:

```powershell
pip install -r requirements.txt
```

Run database migrations:

```powershell
python manage.py migrate
```

Start Django:

```powershell
python manage.py runserver
```

The backend should be available at `http://127.0.0.1:8000`.

### Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend should be available at `http://localhost:5173`.

The Vite development server proxies `/api` and `/media` requests to Django. Both services must be running for the complete application to work.

> **Run one workflow at a time.** The Docker Compose stack below publishes the
> same ports (`8000` and `5173`). While it is running, Docker keeps those ports
> and the browser reaches the containers instead of the processes started above;
> Vite then answers `502 Bad Gateway` for `/api/...` and the app shows its
> offline banner. Stop it with `docker compose down` before using this workflow.

---

## 2. Docker Development Setup

Docker was installed and tested locally on Windows using Docker Desktop.

### Prerequisites

- Docker Desktop
- Docker Compose
- A valid `backend/.env` file
- The project's Dockerfiles and root `compose.yaml`

### Verify Docker

```powershell
docker --version
docker compose version
docker run hello-world
```

The `hello-world` container ran successfully, confirming that Docker was operational locally.

### Validate the Compose configuration

Run these commands from the project root:

```powershell
docker compose config --quiet
```

If the configuration is valid, the command normally completes without output.

### Build and start the application

```powershell
docker compose build
docker compose up
```

Access the local application at:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

### Useful Docker commands

```powershell
# Rebuild and start containers
docker compose up --build

# Start containers in the background
docker compose up -d

# Check container status
docker compose ps

# View logs
docker compose logs -f

# View backend logs
docker compose logs -f backend

# View frontend logs
docker compose logs -f frontend

# Stop the Compose application
docker compose down
```

**Important:** The current Dockerfiles use development servers. Do not expose this configuration directly to the public internet as a production deployment without preparing the appropriate production configuration.

---

## 3. Remote Ubuntu Server Deployment

### Deployment target

| Setting | Value |
|---|---|
| Server IP | `103.68.157.45` |
| SSH username | `sas` |
| SSH port | `22` |
| Intended application port | `4816` |
| Operating system | Ubuntu 26.04.1 LTS |
| Container runtime | Docker |
| Compose version | Docker Compose v5.6.0 |

The intended goal is to deploy SAS Reserve on the remote Ubuntu server and make the application accessible through port `4816`.

### Step 1: Check network connectivity

On the Windows computer, open PowerShell:

```powershell
ping 103.68.157.45
```

**Result encountered:** The server responded to all four ping requests, with approximately 57 ms latency and no packet loss.

This confirmed basic network reachability, but did not establish that the application ports were accessible.

### Step 2: Check the server's ports

Run these commands in PowerShell:

```powershell
Test-NetConnection 103.68.157.45 -Port 22
Test-NetConnection 103.68.157.45 -Port 8000
Test-NetConnection 103.68.157.45 -Port 4816
```

**Results encountered:**

- **Port 22:** `TcpTestSucceeded: True` — SSH was reachable.
- **Port 8000:** `TcpTestSucceeded: False` — no successful TCP connection from the Windows computer.
- **Port 4816:** `TcpTestSucceeded: False` — no successful TCP connection from the Windows computer.

The unsuccessful checks do not, by themselves, prove that the ports are permanently blocked. A service may not yet be listening, or a firewall or network rule may prevent access.

Port `8000` is the local Django development port. Port `4816` is the intended remote application port. Neither should be assumed to be available until verified with the server administrator.

### Step 3: Connect to the Ubuntu server

Use PowerShell:

```powershell
ssh sas@103.68.157.45
```

Enter the password when prompted.

**Problem encountered:** An earlier attempt to log in using `mis@103.68.157.45` did not succeed. The successful account used for the later SSH session was `sas`.

The server presented an SSH host-key fingerprint during the initial connection. For a production or shared server, verify the fingerprint with the server administrator before trusting it.

After a successful connection, the prompt appeared similar to:

```text
sas@misserver:~$
```

### Step 4: Verify the remote operating system and Docker

Run these commands inside the SSH session:

```bash
whoami
lsb_release -a
docker --version
docker compose version
docker ps
```

**Results encountered:**

- The logged-in account was `sas`.
- The server was running Ubuntu 26.04.1 LTS.
- Docker reported version `29.8.2`.
- Docker Compose reported version `v5.6.0`.
- The `docker ps` command failed with a Docker daemon permission error.

The important distinction is that **Docker was installed, but the `sas` account could not access the Docker daemon**.

### Step 5: Diagnose the Docker permission problem

The command:

```bash
docker ps
```

returned an error similar to:

```text
permission denied while trying to connect to the Docker API
at unix:///var/run/docker.sock
```

Checking administrative permissions with:

```bash
sudo -l
```

returned:

```text
sudo: Sorry, user sas may not run sudo on misserver.
```

**Root cause identified:** The `sas` account did not have permission to use the Docker daemon and was not authorized to run commands through `sudo`.

Installing Docker is not sufficient. The deployment account must also be authorized to manage containers.

**Required resolution:**

Contact the server administrator and request an approved deployment method. The administrator should confirm whether the `sas` account can be granted Docker access under the server's security policy, or whether deployments must be performed by another authorized account or process.

Do not attempt to bypass this restriction, change Docker socket permissions, or modify other users' containers without authorization. Docker access can provide extensive control over the host.

### Step 6: Resolve access before deployment

Before proceeding, confirm the following with the administrator:

1. The authorized account or deployment process that will manage the SAS Reserve containers.
2. Whether Docker Compose deployment is permitted on this server.
3. Whether port `4816` is assigned to SAS Reserve.
4. Whether the relevant firewall and network rules permit access to that port.
5. Which production database and persistent storage should be used.
6. Whether an existing service already uses the intended port.

Do not proceed with container deployment until the permission issue and port assignment are resolved.

### Step 7: Prepare the project for production

Once authorized Docker access is available, transfer or clone the project onto the server using the approved method.

For example, if the administrator permits cloning the repository:

```bash
git clone https://github.com/chan2s/sas-smart-reservation-system.git
cd sas-smart-reservation-system
```

This clones the repository's default branch. If the deployment must use a particular release or commit, check out that version explicitly.

Before starting the containers:

- Create the production environment configuration on the server.
- Set `DJANGO_DEBUG=False`.
- Configure `DJANGO_SECRET_KEY` securely.
- Configure `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.
- Configure the production database and credentials.
- Configure persistent storage for uploaded media and database data.
- Review Django static-file handling and production application-server settings.
- Ensure secrets are not committed to Git.
- Configure HTTPS if the application will be publicly accessible.

Do not copy a local development `.env` file to a public repository or expose its contents in logs.

### Step 8: Configure and deploy the application

The current development configuration uses the frontend development server on port `5173` and Django's development server on port `8000`.

For production, create or verify a production-specific Docker Compose configuration before exposing the application. The intended public port is `4816`, but the final port mapping depends on the approved architecture.

A possible architecture is:

```text
Browser
   |
   v
103.68.157.45:4816
   |
   v
Production frontend / reverse proxy
   |
   +----> React frontend
   |
   +----> Django API (internal service)
                |
                v
          Production database
```

The diagram describes the intended architecture, not a deployment that has already been completed.

After the administrator resolves access and the production configuration is ready, validate and build the Compose project:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f
```

Run these commands from the directory containing the approved production Compose file, using an account authorized to manage the Docker daemon.

**Do not assume these commands will work with the existing development Compose configuration without reviewing its environment variables, ports, database, volumes, and server settings first.**

### Step 9: Verify the deployment

After deployment, check the service locally on the server and from the Windows computer.

From the server, inspect the containers:

```bash
docker compose ps
docker compose logs --tail=100
```

From Windows PowerShell, test the intended application port:

```powershell
Test-NetConnection 103.68.157.45 -Port 4816
```

When the service is configured to listen on the port and network rules permit access, open:

`http://103.68.157.45:4816`

This HTTP address is for initial connectivity testing only. Production access should use HTTPS when configured.

Verify that:

- The frontend loads.
- The backend API responds.
- Authentication works.
- Database migrations have been applied.
- Reservation and equipment data persist correctly.
- Media uploads and static assets work.
- The application does not expose debugging pages or secrets.

Do not consider deployment complete until these checks pass.

---

## 4. Previous Deployment Status (Before Server Reset)

The checks below describe the old server and are historical only. The Ubuntu
server has since been reset; none of its former Docker access, files, database,
ports, certificates, or running services should be assumed to exist. Use the
Web Push production checklist in Section 9 to verify the rebuilt host.

| Item | Status |
|---|---|
| Local Docker installation | Verified working |
| Local `hello-world` container | Successful |
| Remote server network reachability | Verified by ping |
| Remote SSH connectivity on port 22 | Successful |
| Remote Ubuntu access using `sas` | Successful |
| Remote Docker installation | Verified |
| Remote Docker daemon access for `sas` | Blocked by permissions |
| `sudo` access for `sas` | Not permitted |
| Remote application on port 4816 | Not verified as available |
| SAS Reserve deployed remotely | Not completed |
| Production configuration | Requires preparation and verification |

### Historical blocker

The immediate blocker is **remote Docker permissions**. The server is reachable over SSH and Docker is installed, but the `sas` account cannot manage containers and has no `sudo` privileges.

The next action is to obtain an approved deployment method from the server administrator. After that, prepare the production configuration, verify the port allocation, deploy, and test the application.

---

## 5. Verification

Run the following checks from the project root as applicable.

### Backend tests

```bash
cd backend
python manage.py test
```

### Frontend type checking

```bash
cd frontend
npm run typecheck
```

### Frontend production build

```bash
cd frontend
npm run build
```

### Docker configuration validation

```bash
docker compose config --quiet
```

The actual test count and results should be taken from the current project rather than assumed from older documentation.

### Automatic reservation reminder emails

The Django backend checks for upcoming approved reservations **automatically**:
the scheduler starts with the backend process, runs an immediate catch-up sweep,
then checks every hour. It sends the branded reminder email plus the existing
in-app notification for reservations scheduled within the next three days. No
administrator action and no browser tab are required.

Relevant `.env` keys (see `backend/.env.example`):

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_HOST_USER=your-address@gmail.com
EMAIL_HOST_PASSWORD=your-google-app-password
DEFAULT_FROM_EMAIL=SAS RESERVE <your-address@gmail.com>
```

Delivery is recorded on the reservation (`reminder_email_sent_at`), so a
restart, an hourly repeat, or two overlapping workers never email the same
reservation twice. Failed sends release their claim and are retried on the next
check. A short database lease elects one active scheduler even when gunicorn or
Docker runs several backend workers.

Operational commands (run from `backend/` with the same environment and
virtualenv as the web process):

```bash
# One manual sweep (safe and idempotent; useful for verification).
python manage.py send_reservation_reminders

# Report how many reminders are due without sending anything.
python manage.py send_reservation_reminders --dry-run

# Dedicated scheduler process for deployments that prefer a worker service.
python manage.py run_reminder_scheduler
```

To run the scheduler in a dedicated process instead of web workers, set
`REMINDER_SCHEDULER_ENABLED=false` on the web service and run
`python manage.py run_reminder_scheduler` as a separate always-on service. The
in-process default is safe with multiple workers because of the database lease,
but a dedicated worker avoids idle scheduler threads.

The unrelated expiration sweep remains an idempotent management command and can
still be scheduled with the host's cron (or a Render cron job):

```cron
# Move unapproved reservations to EXPIRED once their event starts.
*/10 * * * * cd /path/to/backend && /path/to/python manage.py expire_reservations >> /var/log/sas-expire.log 2>&1
```

---

## 6. API Overview

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login/` | Authentication |
| `POST /api/auth/refresh/` | Refresh JWT |
| `GET /api/auth/me/` | Current user information |
| `GET/POST /api/facilities/` | Facility discovery and management |
| `GET /api/equipment/` | Equipment inventory |
| `POST /api/equipment/{id}/report_issue/` | Report an equipment issue |
| `GET/POST /api/reservations/` | List or create reservations |
| `/api/reservations/{id}/approve/` | Approve a reservation |
| `/api/reservations/{id}/reject/` | Reject a reservation |
| `/api/reservations/{id}/request_changes/` | Request reservation changes |
| `/api/reservations/{id}/cancel/` | Cancel a reservation |
| `/api/reservations/{id}/check_in/` | Check in |
| `/api/reservations/{id}/check_out/` | Check out |
| `POST /api/reservations/{id}/mark-no-show/` | Staff-only: mark an approved reservation as a no-show from the day after its event date |
| `GET /api/reservations/checkin/{code}/` | QR scan lookup |
| `POST /api/availability/check/` | Check availability and conflicts |
| `POST /api/availability/resources/` | Smart resource recommendations |
| `GET /api/calendar/events/` | Calendar events |
| `/api/analytics/` | Analytics |
| `/api/reports/` | Reports and supported exports |

Verify endpoint paths against the current Django URL configuration before relying on them in integrations.

---

## 9. Web Push notifications

Push delivery extends the existing in-app notification events. The push payload
contains a generic message and an authenticated route; reservation details and
personal information remain in the application. Notifications require a working
internet connection and browser and operating-system notification permission.
There is no Firebase, Redis, or Celery requirement.

### Generate VAPID keys for local development

Run from `backend/` after installing the requirements. The `vapid` command
creates PEM files in the current directory; both filenames are ignored by Git.
The private key must remain private. Do not regenerate a key after devices have
subscribed unless those devices will subscribe again with the new public key.

```powershell
cd backend
python -m pip install -r requirements.txt
vapid --gen
vapid --applicationServerKey
```

Copy the output of `vapid --applicationServerKey` into `VAPID_PUBLIC_KEY` in
`backend/.env`. Set `VAPID_PRIVATE_KEY=private_key.pem` and set
`VAPID_CLAIMS_EMAIL` to a monitored `mailto:` address. The private key value is
a file path, not the PEM contents. Restart Django after changing `.env`.

### Local setup

```powershell
cd backend
python manage.py migrate
python manage.py runserver
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Sign in, open **Settings → Push Notifications**, and select **Enable
notifications**. The browser permission prompt appears only after that click.
The local development server at `localhost` is treated as a secure context by
modern browsers. A production or remote test domain must use HTTPS.

The settings control enables or disables push for the current browser/device.
It does not change in-app or email notifications, and removing a device leaves
other registered devices intact.

### API

All endpoints require the existing JWT authentication:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/push/public-key/` | Return the public VAPID key |
| `GET`, `POST` | `/api/push/subscriptions/` | List the caller's devices or register/reuse a subscription |
| `PATCH`, `DELETE` | `/api/push/subscriptions/{id}/` | Activate/deactivate or remove one caller-owned device |

Subscription endpoints and encryption keys are write-only in API responses.
The API returns a one-way endpoint fingerprint so Settings can identify the
current device without returning its push endpoint. Only known browser push
service hosts are accepted, and production subscriptions must use HTTPS.

### Browser and device support

| Platform | Setup |
|---|---|
| Windows: Google Chrome | Use a current browser version, allow site notifications, and keep Windows notifications enabled. |
| Windows: Microsoft Edge | Use a current browser version, allow site notifications, and keep Windows notifications enabled. |
| Android: Google Chrome | Allow notifications in Chrome; install SAS RESERVE as a PWA for app-like access. |
| iPhone/iPad | Requires iOS/iPadOS 16.4 or later. Add SAS RESERVE to the Home Screen, open the installed app, enable notifications there, and allow OS notifications. |

Browser, push-service, and OS policies can limit delivery or background activity.
Push cannot arrive while the device has no internet connection or when browser
or OS notification permission is blocked. Verify each target browser and OS with
a real device before announcing support to users; automated tests mock push
services and do not verify platform delivery.

### Production secrets and deployment

The production Compose service reads the private key from the Docker secret
`/run/secrets/vapid_private_key`, sourced from
`backend/private_key.pem`. Provision that file securely on the Ubuntu server;
it is intentionally ignored by Git. Configure `VAPID_PUBLIC_KEY` and
`VAPID_CLAIMS_EMAIL` in the server-only `backend/.env`, set restrictive file
permissions on both secret and `.env`, and ensure the backend container can make
outbound HTTPS connections to browser push services. Keep the public application
on HTTPS so browsers can register the service worker and use Push APIs.

The production server was reset. Before deployment, the server administrator
must restore/verify Ubuntu access, Docker and Compose, the approved deployment
account's Docker permissions, persistent PostgreSQL storage, the public HTTPS
reverse proxy, DNS/certificate, firewall rules, and an outbound HTTPS route.
The compose service listens on loopback port `4817`; retain the separately
managed production Nginx configuration and verify its public proxy route (the
existing deployment targets port `4816`). No deployment is run by this feature
change.

From an authorized workstation, after obtaining the server's pinned SSH host
key and approved account, provision the server-only `.env` and private key using
the approved secret-transfer process. Configure these VAPID values there:

```dotenv
VAPID_PUBLIC_KEY=<generated applicationServerKey>
VAPID_CLAIMS_EMAIL=mailto:<monitored-address>
```

The production Compose file supplies `VAPID_PRIVATE_KEY` as
`/run/secrets/vapid_private_key`; the PEM secret file itself must be present at
`backend/private_key.pem` on the server before Compose starts. Keep production
`DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, `PUBLIC_FRONTEND_URL`, database
credentials, and HTTPS settings aligned with the real domain and TLS proxy.

After an authorized deployment checkout is prepared and the database/storage
target has been confirmed, run these commands from the repository directory on
the server. Back up any database that must be retained before the migration.
These commands migrate schema and start services; they do not configure the
server, create credentials, open firewall ports, or restore lost production
data.

```bash
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.prod.yaml build backend frontend
docker compose -f compose.prod.yaml up -d db
docker compose -f compose.prod.yaml run --rm backend python manage.py migrate --noinput
docker compose -f compose.prod.yaml up -d backend frontend
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs --tail=100 backend frontend
```

The deployment workflow runs the same migration before replacing the live
backend. Configure its existing GitHub Actions secrets only after the rebuilt
server administrator confirms access: `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_PATH`, `DEPLOY_KNOWN_HOSTS`, and `DEPLOY_SSH_KEY`. Do not trust a newly
reset server host key without independently verifying it. The workflow refuses
to deploy if the account lacks Docker access or the server checkout has diverged.
After startup, verify the public HTTPS site, `/api/health/`, the worker file at
`/push-handler.js`, Settings subscription, and an end-to-end notification on
each target platform.

### Local verification commands

```powershell
cd backend
python manage.py check
python manage.py test notifications.tests_push
python manage.py test
cd ..\frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

## 7. Design System

The frontend defines its design tokens in `frontend/src/index.css` using Tailwind CSS v4's `@theme` configuration.

The design uses a neutral palette, semantic status colors, Inter typography, soft shadows, and shared radius values. Reusable UI components are located in `frontend/src/components/ui/`, with shared layout handled by `AppShell`.

## 8. Additional Notes

- `PENDING`, `APPROVED`, and `ACTIVE` reservations are treated as resource-holding by the availability engine.
- Development media uploads are stored under `backend/media/`.
- The PDF export flow uses the browser's print functionality.
- Development seed credentials must never be used for a public production deployment.
- Local Docker development and remote production deployment are separate configurations.
- Changes to local Docker files do not deploy the application to the remote server automatically.
- The existing `.github/workflows/deploy.yml` runs CI for pushes and deploys `master` only when its deployment secrets and remote Docker access are configured. This feature work has not been deployed.
