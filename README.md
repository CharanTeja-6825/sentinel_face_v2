# SentinelFace

SentinelFace is a Docker Compose prototype for classroom attendance from uploaded
video. Students register through a guided five-angle webcam flow; faculty select a
timetable block, upload a classroom video, and review roster-scoped attendance
results with evidence crops.

The repository contains a React/Vite frontend, a FastAPI backend, an RQ video
worker, PostgreSQL with pgvector, Redis, and local storage for videos, crops, and
the InsightFace model. The system is CPU-only by default and is a prototype, not a
production authentication or liveness system.

## Requirements

- Git
- Docker Desktop (Windows/macOS) or Docker Engine plus the Compose plugin (Linux)
- At least **4 CPU cores and 8 GB RAM** available to Docker
- Recommended for smooth model builds and video processing: **6 CPU cores, 12 GB
  RAM, and 20 GB free disk space**
- A webcam for registration and a classroom video for attendance testing

The first backend build compiles/install packages and the first model load downloads
the InsightFace `antelopev2` model into `./storage/models`. Keep that directory
available between runs.

## Pull and run

```bash
git clone https://github.com/CharanTeja-6825/sentinel_face_v2.git
cd sentinel_face_v2
cp .env.example .env
docker compose up --build
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`. The
repository also includes launchers:

```bash
# Linux/macOS
./run-docker.sh

# Windows Command Prompt or PowerShell
run-docker.bat
```

The launchers create `.env` from `.env.example` only when `.env` does not already
exist, build all Docker images, and then start the Compose services. Pass Compose
run options to the launcher, for example `./run-docker.sh -d` or
`run-docker.bat -d`.

Open:

- Frontend: http://localhost:5173
- API documentation: http://localhost:8000/docs
- API health: http://localhost:8000/health

The API is exposed on host port `8000`, PostgreSQL on `5433`, and Redis on `6380`.
Stop the stack with `Ctrl+C`. To remove containers while keeping database data:

```bash
docker compose down
```

To remove the database volume as well (destructive):

```bash
docker compose down -v
```

## First-time setup

1. Open the frontend and go to **Admin**.
2. In **Admin → Setup**, click **Seed timetable**. Seeding is idempotent and is
   required before timetable blocks appear in the session workflow.
3. Add students and add their roll numbers to the section roster.
4. Use **Register** to capture each student's five-angle face templates.
5. Use **Sessions** to choose a timetable block and upload a classroom video.
6. Open the session detail page to follow the worker and review attendance evidence.

## Docker CPU and RAM settings

The compose file intentionally does not hard-code container limits: the face model
and video pipeline need room to use the resources available to the Docker VM.
Verify the resources currently visible to Docker:

```bash
docker info --format 'CPUs={{.NCPU}} Memory={{.MemTotal}}'
docker compose ps
```

### Docker Desktop

Docker Desktop controls the Linux VM resources. Set **Settings → Resources →
Advanced → CPUs** to at least `4` and **Memory** to at least `8 GB`; use `6 CPUs`
and `12 GB` for smoother processing. Docker Desktop does not provide a portable
cross-version CLI command for changing this VM allocation, so use the settings UI
and the `docker info` command above to verify it. Restart Docker Desktop after
changing the allocation if requested.

Individual one-off containers can still be capped from the command line, for
example:

```bash
docker compose run --rm --memory=4g --cpus=3 backend python -c "print('resource check')"
```

Do not cap the backend/worker below 4 GB each when loading InsightFace.

### Colima

Colima users must allocate the resources to the VM before starting Compose:

```bash
colima stop
colima start --cpu 6 --memory 12 --disk 80
docker info --format 'CPUs={{.NCPU}} Memory={{.MemTotal}}'
./run-docker.sh
```

Use `colima status` to inspect the current allocation. The `--memory` value is in
GB. If Docker reports too little memory, stop Colima and restart it with a larger
value; changing Compose commands alone cannot increase the Colima VM allocation.

### Linux Docker Engine

On Linux, Docker uses host resources directly. Ensure the host has at least 8 GB
RAM (12 GB recommended), then verify with `docker info`. If you need per-container
limits for a constrained machine, use Compose's command-line flags for one-off
commands or configure service limits in a local Compose override; leave enough
memory for PostgreSQL, Redis, the backend, worker, and frontend together.

## Useful commands

```bash
# Rebuild after dependency or Dockerfile changes
docker compose build --no-cache

# Run backend tests in the backend image
docker compose run --rm backend pytest -q

# Follow worker logs while a video is processing
docker compose logs -f worker

# Run the stack in the background
docker compose up --build -d
docker compose logs -f
```

## Configuration and project context

- `ARCHITECTURE.md` describes runtime topology, data flow, invariants, and module
  boundaries.
- `INIT.md` is the master build specification and API reference.
- `DECISIONS.md` records implementation decisions and calibration findings.
- `frontend/DECISIONS.md` records the guided enrolment stage and pose-direction
  behaviour.
- `config/thresholds.yaml`, `config/periods.yaml`, and
  `config/timetable_seed.yaml` provide runtime configuration and seed data.

The timetable period clock mapping in `config/periods.yaml` is marked for human
verification before relying on it operationally.
