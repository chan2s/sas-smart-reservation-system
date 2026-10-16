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

## 4. Current Deployment Status

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

### Current blocker

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
| `GET /api/reservations/checkin/{code}/` | QR scan lookup |
| `POST /api/availability/check/` | Check availability and conflicts |
| `POST /api/availability/resources/` | Smart resource recommendations |
| `GET /api/calendar/events/` | Calendar events |
| `/api/analytics/` | Analytics |
| `/api/reports/` | Reports and supported exports |

Verify endpoint paths against the current Django URL configuration before relying on them in integrations.

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
- Pushing to GitHub only triggers a remote deployment if an appropriate deployment pipeline is configured.
