# SentinelFace — Master Build Specification

**Audience:** An LLM coding agent building this system from an empty repository.
**Deliverable:** A working prototype with two capabilities — student facial registration, and attendance recognition from an uploaded classroom video.
**Version:** 1.0

---

## 0. How to use this document

You are building this from scratch. Nothing exists yet.

**Rules for the build:**

1. **Follow the phase order in §12.** Do not skip ahead. Each phase has acceptance criteria that must pass before the next begins.
2. **Do not invent requirements.** If this document does not specify something, choose the simplest thing that satisfies the acceptance criteria and record the choice in `DECISIONS.md`.
3. **Do not add features.** No authentication beyond what §6 specifies, no dashboards beyond §11, no ERP integration, no live camera streaming. Scope creep is the primary failure mode for this build.
4. **Pin every dependency.** Use the exact versions in §3.
5. **Every module gets a test.** Acceptance criteria are written as testable statements.
6. **Config over constants.** Every threshold in this document goes in `config.py` reading from environment or YAML. Never hardcode a threshold in business logic.
7. **When blocked, stop and report.** Do not stub out core logic and continue. A half-built pipeline that returns plausible-looking wrong answers is worse than an honest failure.

**Flagged for human verification before Phase 3:**
- `config/periods.yaml` — the clock times mapped to period numbers are a placeholder. See §5.2.

---

## 1. Scope

### 1.1 What this system does

**Module A — Registration Portal.** A student sits in front of a webcam and is guided through capturing their face from five angles. The system validates each frame for quality, rejects poor ones with a reason, and stores a set of face embeddings once enough good samples exist.

**Module B — Video Recognition.** A faculty member uploads a video file of a classroom. The system samples frames, detects and tracks faces across time, matches them against the roster of students expected in that class, and produces an attendance report with evidence.

**Module C — Timetable.** Defines which students are expected in which room at which time, so Module B knows who to compare against.

### 1.2 The core design idea

Recognition is scoped to a roster, not to the whole database.

A campus-wide gallery might hold 20,000 students. A single class holds 60. Matching against 60 known candidates instead of 20,000 unknown ones reduces false-match probability by roughly two orders of magnitude. **Every matching operation in Module B must be restricted to the session roster.** This is not an optimisation; it is what makes the accuracy acceptable.

The second idea: attendance from video is a **set-union problem over time**, not a per-frame problem. A student does not need to be recognisable in every frame — only in at least one frame across the whole video. Build the pipeline around accumulating evidence per tracked person, not around per-frame decisions.

### 1.3 Explicitly out of scope

- Live RTSP or camera streaming (uploaded video files only)
- ERP integration of any kind
- Liveness or anti-spoofing detection
- Mobile applications
- Multi-tenancy
- Automatic timetable parsing from images (timetable is seeded from a config file)
- Real-time processing (video jobs run asynchronously and may take minutes)

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND (Vite)                       │
│                                                                │
│   /register          Guided 5-angle webcam capture wizard      │
│   /sessions          Create session, upload video              │
│   /sessions/:id      Job progress, results, evidence review    │
│   /admin             Students, rosters, enrolment coverage     │
└───────────────────────────┬────────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼────────────────────────────────────┐
│                      FASTAPI BACKEND                           │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Enrolment   │  │  Session     │  │  Timetable           │  │
│  │  Router      │  │  Router      │  │  Router              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                     │              │
│  ┌──────▼─────────────────▼─────────────────────▼───────────┐  │
│  │                    SERVICE LAYER                         │  │
│  │  enrolment_service   session_service   roster_service    │  │
│  │  quality_service     gallery_service                     │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │              FACE ENGINE (singleton, startup)            │  │
│  │        InsightFace antelopev2 — SCRFD + glintr100        │  │
│  │        detect() → align() → embed() → 512-D normed       │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────┬─────────────────────────────────┬───────────────────┘
           │                                 │
           │ enqueue                         │
┌──────────▼──────────┐          ┌───────────▼──────────────────┐
│   REDIS + RQ        │          │   POSTGRES 16 + pgvector     │
│                     │          │                              │
│  video_jobs queue   │          │  students, sections, rosters │
└──────────┬──────────┘          │  face_templates (vector 512) │
           │                     │  sessions, tracks            │
┌──────────▼──────────┐          │  observations, decisions     │
│   RQ WORKER         │          └──────────────────────────────┘
│                     │
│  1. decode + sample │          ┌──────────────────────────────┐
│  2. detect          │          │   LOCAL FILE STORAGE         │
│  3. track           │◄────────►│   /storage/videos/           │
│  4. quality gate    │          │   /storage/crops/            │
│  5. embed           │          └──────────────────────────────┘
│  6. cluster tracks  │
│  7. assign (roster) │
│  8. write results   │
└─────────────────────┘
```

### 2.1 Why a worker rather than a request handler

A 50-minute video sampled at 2 fps produces 6,000 frames. Even at 20ms per frame this is two minutes of compute, far beyond any reasonable HTTP timeout. Video processing **must** run in a background worker with the client polling job status.

Build this boundary correctly in Phase 4 even though the prototype has one worker. It is the seam that later allows horizontal scaling.

---

## 3. Technology stack

Pin these exactly.

### Backend

```
python                3.11
fastapi               0.115.0
uvicorn[standard]     0.30.6
pydantic              2.9.2
pydantic-settings     2.5.2
sqlalchemy            2.0.35
alembic               1.13.3
psycopg[binary]       3.2.3
pgvector              0.3.5
redis                 5.1.1
rq                    1.16.2
insightface           0.7.3
onnxruntime           1.19.2        # onnxruntime-gpu 1.19.2 if CUDA available
opencv-python-headless 4.10.0.84
numpy                 1.26.4        # do NOT use 2.x, insightface 0.7.3 breaks
scipy                 1.14.1
scikit-learn          1.5.2
python-multipart      0.0.12
pyyaml                6.0.2
pytest                8.3.3
httpx                 0.27.2
```

**NumPy must stay on 1.26.x.** insightface 0.7.3 has incompatibilities with NumPy 2.x. This will waste hours if ignored.

### Frontend

```
react                 18.3.1
typescript            5.6.2
vite                  5.4.8
tailwindcss           3.4.13
react-router-dom      6.26.2
axios                 1.7.7
lucide-react          0.446.0
```

Use shadcn/ui components installed via CLI. Do not hand-roll a component library.

### Infrastructure

```
postgres              16-alpine  (with pgvector extension)
redis                 7-alpine
```

Everything runs under Docker Compose.

### Model choice

Use **`antelopev2`**, not `buffalo_l`.

| Pack | Detector | Recognition | Backbone | Training set |
|---|---|---|---|---|
| `buffalo_l` | SCRFD-10G | w600k_r50 | ResNet-50 | WebFace600K |
| `antelopev2` | SCRFD-10G | glintr100 | ResNet-100 | Glint360K |

antelopev2 has the larger backbone and stronger training set. Both packs are around 330–360 MB — antelopev2 is not meaningfully heavier. Since inference happens server-side on a batch job, accuracy matters more than speed.

**Hard constraint:** the model that produces enrolment embeddings and the model that produces recognition embeddings must be identical. Store `model_version` on every stored embedding and refuse to compare across versions. Mixing embeddings from different models produces silently wrong results with no error.

---

## 4. Repository structure

```
sentinelface/
├── docker-compose.yml
├── .env.example
├── DECISIONS.md                    # log every choice not specified here
├── README.md
│
├── config/
│   ├── periods.yaml                # VERIFY BEFORE USE — see §5.2
│   ├── thresholds.yaml
│   └── timetable_seed.yaml
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/versions/
│   └── app/
│       ├── main.py                 # FastAPI app, lifespan, CORS
│       ├── config.py               # pydantic-settings, loads YAML
│       ├── database.py             # engine, session factory
│       ├── models/                 # SQLAlchemy ORM
│       │   ├── student.py
│       │   ├── section.py
│       │   ├── template.py
│       │   ├── session.py
│       │   └── observation.py
│       ├── schemas/                # pydantic request/response
│       ├── routers/
│       │   ├── enrolment.py
│       │   ├── sessions.py
│       │   ├── timetable.py
│       │   └── admin.py
│       ├── services/
│       │   ├── face_engine.py      # InsightFace singleton
│       │   ├── quality.py          # quality gate
│       │   ├── enrolment_service.py
│       │   ├── gallery_service.py  # roster gallery load + match
│       │   ├── roster_service.py
│       │   └── session_service.py
│       ├── workers/
│       │   ├── worker.py           # RQ worker entrypoint
│       │   └── video_pipeline.py   # the Module B pipeline
│       └── utils/
│           ├── tracking.py         # IoU tracker
│           └── storage.py          # file paths, crop persistence
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── lib/api.ts
│       ├── components/
│       │   ├── ui/                 # shadcn
│       │   ├── RegistrationWizard.tsx
│       │   ├── AngleGuide.tsx
│       │   ├── VideoUpload.tsx
│       │   ├── JobProgress.tsx
│       │   └── EvidenceGrid.tsx
│       └── pages/
│           ├── RegisterPage.tsx
│           ├── SessionsPage.tsx
│           ├── SessionDetailPage.tsx
│           └── AdminPage.tsx
│
└── storage/
    ├── videos/
    ├── crops/
    └── models/                     # InsightFace downloads here
```

---

## 5. Configuration

### 5.1 `config/thresholds.yaml`

```yaml
quality:
  min_det_score: 0.60
  min_face_width_px: 60           # in source frame, pre-resize
  min_blur_variance: 40.0         # variance of Laplacian
  max_yaw_ratio: 0.35             # 5-point landmark proxy, ~40 degrees
  max_pitch_ratio: 0.40
  min_brightness: 40
  max_brightness: 215

enrolment:
  min_samples: 15
  max_samples: 40
  required_angles: [front, left, right, up, down]
  min_samples_per_angle: 2
  diversity_max_cosine: 0.97      # reject frames too similar to existing
  session_timeout_minutes: 15

video:
  sample_fps: 2.0                 # frames per second to analyse
  max_duration_minutes: 60
  max_upload_mb: 2048
  det_size: [1024, 1024]          # SCRFD input; raise for 4K sources
  track_iou_threshold: 0.30
  track_max_age_frames: 15        # frames a track survives without detection
  track_min_hits: 3               # detections before a track is confirmed

matching:
  cluster_distance: 0.50          # agglomerative cosine distance
  min_crops_per_track: 3
  t_high: 0.60                    # auto-present
  t_low: 0.45                     # below this, no match
  margin_min: 0.10                # top1 - top2 required for confidence
```

Every one of these is a starting value requiring calibration against real data. None are correct until measured. See §12 Phase 6.

### 5.2 `config/periods.yaml` — VERIFY BEFORE USE

The timetable image supplied shows period **numbers** 1 through 16. It does not contain clock times. **The values below are a placeholder and are almost certainly wrong for your institution.** A human must confirm them before Phase 3.

```yaml
# PLACEHOLDER — confirm with the university before relying on this.
timezone: "Asia/Kolkata"
period_duration_minutes: 50

periods:
  1:  { start: "08:00", end: "08:50" }
  2:  { start: "08:50", end: "09:40" }
  3:  { start: "09:40", end: "10:30" }
  4:  { start: "10:30", end: "11:20" }
  5:  { start: "11:20", end: "12:10" }
  # lunch 12:10 - 13:00
  6:  { start: "13:00", end: "13:50" }
  7:  { start: "13:50", end: "14:40" }
  8:  { start: "14:40", end: "15:30" }
  9:  { start: "15:30", end: "16:20" }
  10: { start: "16:20", end: "17:10" }
  11: { start: "17:10", end: "18:00" }
  12: { start: "18:00", end: "18:50" }
  13: { start: "18:50", end: "19:40" }
  14: { start: "19:40", end: "20:30" }
  15: { start: "20:30", end: "21:20" }
  16: { start: "21:20", end: "22:10" }

# Periods eligible for attendance recording.
# Per institutional rule, classes in later periods are not counted.
attendance_eligible_periods: [1, 2, 3, 4, 5, 6, 7, 8, 9]
```

**Behaviour required:** a session created for a period not in `attendance_eligible_periods` must be rejected with HTTP 422 and a clear message. Do not silently accept it.

### 5.3 `config/timetable_seed.yaml`

This is transcribed directly from the supplied timetable image. The entry format in the source is:

```
23IE4053A-S  -  S-67  -  RoomNo-R407A
└─ course ─┘    └sec┘     └── room ──┘
         └ component: L=lecture, P=practical, S=skill/lab
```

**Critical rule — session blocks.** Contiguous periods sharing the same `(course, component, section, room)` form **one session**, not several. On Monday, periods 3–6 are a single four-period lab, and attendance is recorded once for the block. The loader must merge contiguous identical entries into blocks.

Note the Wednesday case: periods 3–4 and 5–6 carry the same course and section but *different rooms* (R405B then R407A). These are **two separate blocks**. Room is part of the block key.

```yaml
section: S-67
entries:
  - { day: Mon, periods: [3,4,5,6], course: "23IE4053A", component: S, group: "S-67", room: "R407A" }
  - { day: Mon, periods: [12],      course: "23AVI3405", component: L, group: "S-62", room: "M123"  }
  - { day: Mon, periods: [16],      course: "23IE4053A", component: P, group: "S-74", room: "A307"  }

  - { day: Tue, periods: [3,4],     course: "22PH4102",  component: L, group: "S-57", room: "C623"  }
  - { day: Tue, periods: [5,6],     course: "22PH4102",  component: P, group: "S-57", room: "F201"  }
  - { day: Tue, periods: [7],       course: "22PH4102",  component: L, group: "S-57", room: "C624B" }
  - { day: Tue, periods: [16],      course: "23IE4053A", component: P, group: "S-74", room: "A307"  }

  - { day: Wed, periods: [1,2],     course: "OECE0003",  component: L, group: "S-51", room: "L306"  }
  - { day: Wed, periods: [3,4],     course: "23IE4053A", component: S, group: "S-67", room: "R405B" }
  - { day: Wed, periods: [5,6],     course: "23IE4053A", component: S, group: "S-67", room: "R407A" }
  - { day: Wed, periods: [8,9],     course: "23AVI3509", component: L, group: "S-79", room: "M201"  }

  - { day: Thu, periods: [1,2],     course: "OEBB0002",  component: L, group: "S-58", room: "C421A" }
  - { day: Thu, periods: [3,4,5,6], course: "23IE4053A", component: S, group: "S-67", room: "R407B" }
  - { day: Thu, periods: [8],       course: "23AVI3509", component: L, group: "S-79", room: "L502"  }

  - { day: Fri, periods: [3,4],     course: "OEVC0003",  component: L, group: "S-60", room: "R404A" }
  - { day: Fri, periods: [7],       course: "OEVC0003",  component: L, group: "S-60", room: "C221B2"}

  - { day: Sat, periods: [1],       course: "OECE0003",  component: L, group: "S-51", room: "C608"  }
  - { day: Sat, periods: [2],       course: "OEBB0002",  component: L, group: "S-58", room: "C608"  }
```

Periods 10, 11, 13, 14, 15 are empty in the source, and 12 and 16 fall outside `attendance_eligible_periods`. Entries for ineligible periods are still loaded — they simply cannot have attendance sessions created against them.

---

## 6. Data model

Enable pgvector first: `CREATE EXTENSION IF NOT EXISTS vector;`

```sql
-- ─────────────────────────── Identity ───────────────────────────

CREATE TABLE students (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    roll_no         VARCHAR(32) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    consent_given   BOOLEAN NOT NULL DEFAULT FALSE,
    consent_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(32) UNIQUE NOT NULL,   -- e.g. 'S-67'
    name            VARCHAR(200),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE section_students (
    section_id      UUID REFERENCES sections(id) ON DELETE CASCADE,
    student_id      UUID REFERENCES students(id) ON DELETE CASCADE,
    PRIMARY KEY (section_id, student_id)
);

-- ─────────────────────────── Enrolment ──────────────────────────

CREATE TABLE enrolment_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID REFERENCES students(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL,   -- active|completed|expired|abandoned
    captured_count  INT NOT NULL DEFAULT 0,
    angles_captured JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {"front":4,"left":3,...}
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE face_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID REFERENCES students(id) ON DELETE CASCADE,
    embedding       vector(512) NOT NULL,
    angle           VARCHAR(16) NOT NULL,   -- front|left|right|up|down|centroid
    quality_score   REAL NOT NULL,
    is_centroid     BOOLEAN NOT NULL DEFAULT FALSE,
    model_version   VARCHAR(64) NOT NULL,
    source          VARCHAR(20) NOT NULL,   -- enrolment|feedback
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_templates_student ON face_templates(student_id);

-- ────────────────────────── Timetable ───────────────────────────

CREATE TABLE timetable_blocks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id      UUID REFERENCES sections(id) ON DELETE CASCADE,
    day_of_week     VARCHAR(3) NOT NULL,    -- Mon..Sat
    start_period    INT NOT NULL,
    end_period      INT NOT NULL,
    course_code     VARCHAR(32) NOT NULL,
    component       CHAR(1) NOT NULL,       -- L|P|S
    group_code      VARCHAR(16) NOT NULL,
    room            VARCHAR(32) NOT NULL,
    UNIQUE (section_id, day_of_week, start_period)
);

-- ─────────────────────── Attendance sessions ────────────────────

CREATE TABLE attendance_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id        UUID REFERENCES timetable_blocks(id),
    section_id      UUID REFERENCES sections(id),
    session_date    DATE NOT NULL,
    start_period    INT NOT NULL,
    status          VARCHAR(20) NOT NULL,
        -- created|uploaded|queued|processing|completed|failed|finalized
    video_path      TEXT,
    video_duration_s REAL,
    expected_count  INT,
    detected_count  INT,
    frames_sampled  INT,
    processing_ms   INT,
    error_message   TEXT,
    model_version   VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at    TIMESTAMPTZ,
    UNIQUE (section_id, session_date, start_period)
);

-- ────────────────── Evidence (append-only) ──────────────────────

CREATE TABLE tracks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    cluster_id      INT,                    -- assigned after clustering
    first_seen_s    REAL NOT NULL,
    last_seen_s     REAL NOT NULL,
    crop_count      INT NOT NULL,
    mean_quality    REAL NOT NULL,
    best_crop_path  TEXT
);

CREATE TABLE observations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    cluster_id      INT NOT NULL,
    top1_student_id UUID REFERENCES students(id),
    top1_score      REAL,
    top2_student_id UUID REFERENCES students(id),
    top2_score      REAL,
    margin          REAL,
    band            VARCHAR(16) NOT NULL,   -- confident|uncertain|no_match
    crop_paths      JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_version   VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ───────────────────────── The ledger ───────────────────────────

CREATE TABLE attendance_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id      UUID REFERENCES students(id),
    decision        VARCHAR(10) NOT NULL,   -- present|absent
    source          VARCHAR(20) NOT NULL,   -- auto|manual_override
    score           REAL,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, student_id)         -- makes writes idempotent
);

CREATE TABLE unmatched_faces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    cluster_id      INT NOT NULL,
    crop_path       TEXT NOT NULL,
    best_score      REAL,
    resolution      VARCHAR(20) DEFAULT 'unresolved',
        -- unresolved|outsider|unenrolled|not_a_person
    resolved_at     TIMESTAMPTZ
);
```

**Two invariants the code must preserve:**

1. `observations` is **append-only**. Never update or delete a row. It is the replay buffer — when thresholds change, decisions are re-derived from stored observations rather than re-processing video. This is why threshold calibration is possible at all.

2. `attendance_decisions` has a unique constraint on `(session_id, student_id)`. All writes use `INSERT ... ON CONFLICT DO UPDATE`. Retried requests must never duplicate a row.

---

## 7. Module A — Registration Portal

### 7.1 Flow

```
Student enters roll number and gives consent
        │
        ▼
POST /enrolment/sessions          → session_id, required angles
        │
        ▼
  ┌─── For each angle prompt (front → left → right → up → down): ───┐
  │                                                                 │
  │   Browser captures a frame from webcam every ~700ms             │
  │        │                                                        │
  │        ▼                                                        │
  │   POST /enrolment/sessions/{id}/frames                          │
  │        │                                                        │
  │        ▼                                                        │
  │   Backend: detect → quality gate → pose classify →              │
  │            diversity check → embed → store in session buffer    │
  │        │                                                        │
  │        ▼                                                        │
  │   { accepted, reason, detected_angle, quality_score,            │
  │     captured_count, angle_progress }                            │
  │                                                                 │
  │   UI advances when min_samples_per_angle reached for this angle │
  └─────────────────────────────────────────────────────────────────┘
        │
        ▼
POST /enrolment/sessions/{id}/complete
        │
        ▼
Persist all embeddings + a centroid → face_templates
```

### 7.2 Face engine

Build `services/face_engine.py` as a module-level singleton initialised in the FastAPI lifespan handler. Loading InsightFace per request will make the system unusable.

```python
from insightface.app import FaceAnalysis

class FaceEngine:
    MODEL_VERSION = "antelopev2/glintr100"

    def __init__(self, det_size=(640, 640), ctx_id=-1):
        # ctx_id=-1 forces CPU, 0 selects first GPU
        self.app = FaceAnalysis(
            name="antelopev2",
            root="/storage/models",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=ctx_id, det_size=det_size)

    def detect(self, bgr_image):
        """Returns list of insightface Face objects.
        Each has .bbox, .kps (5x2), .det_score, .normed_embedding (512,)."""
        return self.app.get(bgr_image)
```

Always use `.normed_embedding` (already L2-normalised) so cosine similarity is a plain dot product. Never use `.embedding` directly.

### 7.3 Quality gate

`services/quality.py`. Every check returns a specific reason string on failure — the UI shows these to the student, and vague reasons make the wizard frustrating.

```python
def assess(face, frame) -> QualityResult:
    # 1. Detection confidence
    if face.det_score < cfg.min_det_score:
        return reject("low_detection_confidence")

    # 2. Face size in source pixels
    x1, y1, x2, y2 = face.bbox
    width = x2 - x1
    if width < cfg.min_face_width_px:
        return reject("face_too_small")     # UI: "Move closer to the camera"

    # 3. Blur — variance of Laplacian on the crop
    crop = frame[int(y1):int(y2), int(x1):int(x2)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur < cfg.min_blur_variance:
        return reject("too_blurry")         # UI: "Hold still, improve lighting"

    # 4. Brightness
    mean_v = gray.mean()
    if not (cfg.min_brightness <= mean_v <= cfg.max_brightness):
        return reject("poor_lighting")

    # 5. Pose — see 7.4
    yaw_r, pitch_r = pose_ratios(face.kps)
    ...
    quality = weighted_score(det_score, width, blur, pose)
    return accept(quality, angle)
```

### 7.4 Pose estimation from 5 landmarks

InsightFace's `kps` array is ordered: `[left_eye, right_eye, nose, left_mouth, right_mouth]` in image coordinates.

```python
def pose_ratios(kps):
    le, re, nose, lm, rm = kps

    # Yaw: horizontal asymmetry of nose between the eyes.
    # Ranges roughly -1 (turned far right) .. +1 (turned far left).
    d_left  = nose[0] - le[0]
    d_right = re[0] - nose[0]
    yaw = (d_left - d_right) / (d_left + d_right + 1e-6)

    # Pitch: nose height relative to the eye line and mouth line.
    eye_y   = (le[1] + re[1]) / 2
    mouth_y = (lm[1] + rm[1]) / 2
    span    = mouth_y - eye_y + 1e-6
    pitch = ((nose[1] - eye_y) / span - 0.5) * 2

    return yaw, pitch


def classify_angle(yaw, pitch):
    if abs(yaw) < 0.15 and abs(pitch) < 0.20:  return "front"
    if yaw >=  0.15:                            return "left"
    if yaw <= -0.15:                            return "right"
    if pitch <= -0.20:                          return "up"
    if pitch >=  0.20:                          return "down"
    return "front"
```

This is a geometric approximation, not true 3D pose estimation, and that is acceptable here — we only need to bucket into five coarse classes and reject extremes.

**Sign convention warning:** whether positive yaw means the subject's left or the viewer's left depends on mirroring. Webcam preview is typically mirrored for the user but the captured frame usually is not. Verify empirically in Phase 2 and document the result in `DECISIONS.md`. Getting this backwards produces a wizard that tells students to turn the wrong way, and it is not obvious from code review.

### 7.5 Diversity check

Reject frames nearly identical to ones already captured — twenty photos of exactly the same pose add no information and waste the sample budget.

```python
for existing in session_buffer:
    if float(np.dot(new_embedding, existing.embedding)) > cfg.diversity_max_cosine:
        return reject("too_similar")   # UI: "Move slightly, this looks the same"
```

### 7.6 Completion

Require, before allowing completion:
- `captured_count >= min_samples`
- every angle in `required_angles` has at least `min_samples_per_angle`

On completion:
1. Insert one `face_templates` row per buffered sample with its angle and quality.
2. Compute the mean of all embeddings, L2-normalise it, insert as `is_centroid = TRUE`.
3. Mark the enrolment session `completed`.
4. Delete buffered frames from memory and disk.

Store `model_version` on every row.

### 7.7 Acceptance criteria — Module A

- [ ] A session rejects frames with no face, giving reason `no_face_detected`
- [ ] A session rejects frames with more than one face, reason `multiple_faces`
- [ ] Deliberately blurred input is rejected with `too_blurry`
- [ ] A face far from the camera is rejected with `face_too_small`
- [ ] Holding perfectly still eventually yields `too_similar` rejections
- [ ] Completion is refused when any required angle is under-sampled, with a message naming the missing angle
- [ ] After completion, `face_templates` contains `captured_count + 1` rows for that student
- [ ] Exactly one row has `is_centroid = TRUE` and its vector is unit length (±1e-5)
- [ ] Sessions past `expires_at` are rejected with HTTP 410
- [ ] Enrolment is refused when `consent_given` is false

---

## 8. Module B — Video Recognition

This is the technically hard module. Read the whole section before writing any of it.

### 8.1 Pipeline

```
Video file
    │
    ▼
[1] DECODE + SAMPLE ─── take 1 frame every (fps_native / sample_fps) frames
    │                    record each frame's timestamp in seconds
    ▼
[2] DETECT ──────────── SCRFD on each sampled frame → boxes + landmarks
    │
    ▼
[3] TRACK ───────────── link boxes across frames by IoU → track_id
    │                    a track = one person's appearances over time
    ▼
[4] QUALITY GATE ────── discard crops too small / blurred / extreme pose
    │                    tracks with < min_crops_per_track are dropped
    ▼
[5] EMBED ───────────── ArcFace on surviving crops, batched
    │
    ▼
[6] TRACK AGGREGATE ─── mean embedding per track, re-normalised
    │
    ▼
[7] CLUSTER ─────────── merge fragmented tracks of the same person
    │                    agglomerative, cosine, threshold 0.50
    ▼
[8] ASSIGN ──────────── Hungarian on (clusters x roster), one-to-one
    │
    ▼
[9] BAND + PERSIST ──── confident / uncertain / no_match → observations
                        → attendance_decisions
```

### 8.2 Why steps 6 and 7 matter more than they look

**Step 6 (track aggregation)** is where most of the accuracy comes from. A single back-row frame produces a marginal embedding. Averaging thirty crops of the same person across thirty seconds of video substantially reduces noise, and the averaged embedding routinely matches when no individual frame would. This is the temporal-union principle made concrete: the student only has to be clearly visible *occasionally*.

**Step 7 (clustering)** exists because trackers fragment. A person who turns away, is briefly occluded, or leaves the frame gets a new `track_id` on return. Without merging, one student produces four tracks, and the one-to-one assignment in step 8 will match one of them and mark the other three as unknown intruders. Cluster the track-level embeddings before assigning.

### 8.3 Sampling

```python
cap = cv2.VideoCapture(video_path)
native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
stride = max(1, int(round(native_fps / cfg.sample_fps)))

idx = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    if idx % stride == 0:
        timestamp_s = idx / native_fps
        yield timestamp_s, frame
    idx += 1
```

Do not decode every frame and discard most — use `cap.grab()` for skipped frames and `cap.retrieve()` only on kept ones. On a 50-minute video this is roughly a 10× speedup on decode.

**Detector input size.** SCRFD resizes input to `det_size`. If the source is 4K and `det_size` is 640×640, a back-row face shrinks below detectability before the detector ever sees it. For 1080p sources use `(1024, 1024)`. For 4K sources either raise to `(1600, 1600)` or tile the frame into overlapping quadrants and merge detections with NMS. **Tiling is the correct answer for 4K and should be implemented if the pilot footage is 4K.**

### 8.4 Tracker

A simple IoU tracker is sufficient — do not pull in a heavyweight tracking library for this prototype.

```python
class IoUTracker:
    def __init__(self, iou_threshold, max_age, min_hits):
        self.tracks = []      # {id, bbox, age, hits, crops:[...]}
        self.next_id = 0

    def update(self, detections, timestamp_s, frame):
        # 1. Build IoU cost matrix between existing tracks and detections
        # 2. Hungarian assignment (scipy.optimize.linear_sum_assignment)
        # 3. Matched pairs above iou_threshold: update track bbox, reset age,
        #    increment hits, append crop
        # 4. Unmatched detections: create new track
        # 5. Unmatched tracks: age += 1; retire when age > max_age
        # 6. Only tracks with hits >= min_hits are ever emitted
```

`min_hits` filters spurious single-frame detections — reflections, posters, motion artefacts.

### 8.5 Matching

```python
def match_clusters_to_roster(cluster_embeddings, gallery):
    """
    cluster_embeddings : (C, 512) L2-normalised
    gallery            : dict student_id -> (T_i, 512) all their templates
    """
    student_ids = list(gallery.keys())

    # Score = MAX over that student's templates, not the centroid.
    # Multi-angle enrolment exists precisely so a side view can match
    # a side-view template. Averaging would destroy that.
    S = np.zeros((len(cluster_embeddings), len(student_ids)), dtype=np.float32)
    for j, sid in enumerate(student_ids):
        S[:, j] = (cluster_embeddings @ gallery[sid].T).max(axis=1)

    # Global one-to-one assignment. This is what makes it impossible
    # for one student to be matched by two different faces.
    rows, cols = linear_sum_assignment(-S)

    results = []
    for r, c in zip(rows, cols):
        order = np.argsort(-S[r])
        top1, top2 = order[0], (order[1] if len(order) > 1 else None)
        score  = float(S[r, top1])
        second = float(S[r, top2]) if top2 is not None else 0.0
        results.append({
            "cluster_id": r,
            "top1_student_id": student_ids[top1],
            "top1_score": score,
            "top2_student_id": student_ids[top2] if top2 is not None else None,
            "top2_score": second,
            "margin": score - second,
        })
    return results
```

**The gallery must contain only students on this session's roster.** Loading the full student table here would silently destroy accuracy while producing no error. Assert the gallery size equals the roster size before matching.

### 8.6 Banding

```python
def band(score, margin, cfg):
    if score >= cfg.t_high and margin >= cfg.margin_min:
        return "confident"          # → present, source='auto'
    if score >= cfg.t_low:
        return "uncertain"          # → shown to faculty, defaults to absent
    return "no_match"               # → unmatched_faces
```

Roster students receiving no cluster assignment are marked `absent` with `source='auto'`.

**Uncertain entries default to absent if the faculty does nothing.** A false absent is corrected in three seconds by a student sitting in the room. A false present is invisible and enables proxy attendance. Never default the other way.

### 8.7 Job management

```python
# router: POST /sessions/{id}/video
#   1. validate size and duration against config
#   2. save to /storage/videos/{session_id}.mp4
#   3. set status='queued'
#   4. queue.enqueue(process_video, session_id, job_timeout='2h')
#   5. return 202 with session_id

# worker:
def process_video(session_id):
    set_status(session_id, 'processing')
    try:
        result = run_pipeline(session_id)     # steps 1-9
        persist(result)
        set_status(session_id, 'completed')
    except Exception as e:
        set_status(session_id, 'failed', error_message=str(e))
        raise                                  # let RQ record the failure
```

The worker must write progress (`frames_sampled`, percentage) to the session row periodically so the UI can show a real progress bar. A 50-minute video is a multi-minute wait, and an unresponsive spinner is a bad experience.

Make `process_video` idempotent: if the session already has observations, delete them and reprocess. Re-running a job must never double-write.

### 8.8 Acceptance criteria — Module B

- [ ] A 5-minute 1080p test video processes end to end without error
- [ ] Sampling at 2 fps on a 5-minute video yields ~600 sampled frames
- [ ] `cap.grab()` is used for skipped frames (verify by timing against naive decode)
- [ ] One person walking in and out of frame produces **one** cluster, not several
- [ ] Two distinct people produce two clusters
- [ ] No student appears in two clusters after assignment
- [ ] Gallery size is asserted equal to roster size before matching
- [ ] A student enrolled but absent from the video is marked `absent`
- [ ] A person in the video not on the roster appears in `unmatched_faces`
- [ ] Job status transitions queued → processing → completed and is visible via API
- [ ] A deliberately corrupt video sets status `failed` with a readable message
- [ ] Re-running a completed job replaces rather than duplicates observations
- [ ] Every `observations` row carries the `model_version` used

---

## 9. Module C — Timetable

### 9.1 Block merging

The loader reads `config/timetable_seed.yaml` and creates `timetable_blocks`. Contiguous periods sharing `(course, component, group, room)` merge into one block.

```python
def merge_blocks(day_entries):
    """day_entries: list of (period, course, component, group, room)
       sorted by period. Returns merged blocks."""
    blocks, current = [], None
    for e in sorted(day_entries, key=lambda x: x.period):
        key = (e.course, e.component, e.group, e.room)
        if (current
                and current.key == key
                and e.period == current.end_period + 1):
            current.end_period = e.period          # extend
        else:
            if current: blocks.append(current)
            current = Block(key=key, start_period=e.period,
                            end_period=e.period)
    if current: blocks.append(current)
    return blocks
```

**Room is part of the key.** The supplied timetable has a Wednesday case where the same course and section run in periods 3–4 in room R405B and periods 5–6 in R407A. These must produce two blocks, not one four-period block. A merge that ignores room will silently produce wrong session boundaries.

### 9.2 Period resolution

```python
def block_time_window(block, date, periods_cfg):
    start = periods_cfg[block.start_period]["start"]
    end   = periods_cfg[block.end_period]["end"]
    tz    = ZoneInfo(periods_cfg_timezone)
    return (datetime.combine(date, parse_time(start), tz),
            datetime.combine(date, parse_time(end), tz))
```

### 9.3 Eligibility

```python
def assert_eligible(start_period, cfg):
    if start_period not in cfg.attendance_eligible_periods:
        raise HTTPException(422,
            f"Period {start_period} is not eligible for attendance recording. "
            f"Eligible periods: {cfg.attendance_eligible_periods}")
```

Enforce this at session creation, not at finalisation.

### 9.4 Acceptance criteria — Module C

- [ ] Seed load produces exactly 18 blocks from the supplied timetable
- [ ] Monday periods 3–6 merge into a single block
- [ ] Wednesday periods 3–4 and 5–6 remain **two** blocks (different rooms)
- [ ] Creating a session for period 12 or 16 returns HTTP 422
- [ ] `block_time_window` returns correct IST datetimes for a given date
- [ ] Re-running the seed loader is idempotent (no duplicate blocks)

---

## 10. API reference

```
── Enrolment ────────────────────────────────────────────────────
POST   /enrolment/sessions
         { roll_no, consent: true }
       → 201 { session_id, required_angles, min_samples, expires_at }

POST   /enrolment/sessions/{id}/frames
         { image: "data:image/jpeg;base64,..." , angle_hint }
       → 200 { accepted, reason, detected_angle, quality_score,
               captured_count, angle_progress, can_complete }

POST   /enrolment/sessions/{id}/complete
       → 200 { student_id, stored_templates, angles }
       → 422 if requirements unmet, with the specific shortfall

GET    /enrolment/sessions/{id}      → current state
DELETE /enrolment/sessions/{id}      → abandon, discard buffer

── Timetable ────────────────────────────────────────────────────
POST   /timetable/seed               → load from YAML (idempotent)
GET    /timetable/blocks?section=S-67&day=Mon
GET    /timetable/blocks/{id}

── Sessions ─────────────────────────────────────────────────────
POST   /sessions
         { block_id, session_date }
       → 201 { session_id, expected_count, roster, enrolled_pct }
       → 422 if period ineligible

POST   /sessions/{id}/video          multipart file upload
       → 202 { session_id, status: "queued" }

GET    /sessions/{id}                → status, progress, counts
GET    /sessions/{id}/results
       → { confident: [{student, score, crop_url, first_seen_s}],
           uncertain: [{student, score, margin, crop_url}],
           absent:    [{student}],
           unmatched: [{cluster_id, crop_url, best_score}],
           stats: { detected_count, expected_count, frames_sampled,
                    processing_ms, auto_resolution_rate } }

PATCH  /sessions/{id}/decisions
         [{ student_id, decision }]  → manual overrides
PATCH  /sessions/{id}/unmatched
         [{ cluster_id, resolution }]
POST   /sessions/{id}/finalize       → lock; no further edits

── Admin ────────────────────────────────────────────────────────
GET    /admin/students               → list + enrolment status
POST   /admin/students               → create
GET    /admin/sections/{code}/coverage → enrolled_pct, missing students
GET    /admin/sessions               → history + metrics
GET    /health                       → db, redis, model, version
```

---

## 11. Frontend

Four pages. Keep them plain — this is a prototype, and time spent on visual polish is time not spent on the pipeline.

### `/register` — Registration wizard

- Roll number entry, then an explicit consent checkbox with readable text about what is stored and for how long
- Webcam preview with a face-position guide overlay
- A large angle prompt: "Look straight ahead" → "Turn your head left" → and so on
- Per-angle progress: `front 4/2 ✓ · left 1/2 · right 0/2 · up 0/2 · down 0/2`
- Rejection reasons shown as friendly text, not raw codes:
  `face_too_small` → "Move a little closer"
  `too_blurry` → "Hold still — try better lighting"
  `too_similar` → "Move slightly, that looks the same as the last one"
- Auto-capture every ~700ms; do not make the student press a button 20 times
- "Complete" disabled until `can_complete` is true, with a tooltip naming what is missing

### `/sessions` — Session list and creation

- Section and date pickers, then blocks for that day
- Ineligible periods rendered greyed with the reason visible, not hidden — the user should understand why period 12 cannot be selected
- Video upload with a progress bar and client-side size validation

### `/sessions/:id` — Results

- While processing: progress bar driven by `frames_sampled`, plus elapsed time
- On completion, three collapsible groups:
  - **Confident present** — collapsed by default, count in the header
  - **Uncertain** — expanded, each row showing the crop, the candidate name, the score and margin, and Present / Absent buttons
  - **Absent** — the list, with a manual Present override
- **Unmatched faces** — crop grid with the three resolution buttons
- A stats bar: detected / expected, auto-resolution rate, processing time
- Headcount warning banner when `|detected_count - present_count| > 3`

### `/admin` — Administration

- Student list with enrolment status and template counts
- Per-section coverage bar, listing students who still need to enrol
- Session history with per-session auto-resolution rate

---

## 12. Build order

Do these in order. Do not begin a phase until the previous phase's acceptance criteria pass.

**Phase 1 — Foundation**
Docker Compose (postgres + pgvector, redis). Alembic migrations for the full §6 schema. FastAPI skeleton with `/health` reporting database, Redis, and model status. Config loading from YAML and environment.
*Done when:* `docker compose up` yields a healthy `/health` and all tables exist.

**Phase 2 — Face engine and quality gate**
FaceEngine singleton with lifespan loading. Quality module. Pose ratios and angle classification. Unit tests using a handful of committed test images.
*Done when:* a script embeds a JPEG and returns a 512-D unit vector; quality gate correctly rejects a deliberately blurred and a deliberately tiny face. **Resolve the yaw sign convention here and record it in `DECISIONS.md`.**

**Phase 3 — Timetable**
Seed loader with block merging. Period resolution. Eligibility enforcement.
*Done when:* all §9.4 criteria pass. Prompt the human to verify `config/periods.yaml` before proceeding.

**Phase 4 — Registration (backend then frontend)**
Enrolment session lifecycle, frame validation, diversity check, completion and centroid computation. Then the wizard UI.
*Done when:* all §7.7 criteria pass and a real person can enrol through the browser.

**Phase 5 — Video pipeline**
Sampling, tracking, quality gate, embedding, aggregation, clustering, assignment, banding, persistence. RQ worker and job status. Then the results UI.
*Done when:* all §8.8 criteria pass on a real classroom video with at least three enrolled people.

**Phase 6 — Calibration**
Process 5 videos with manually recorded ground truth. Sweep `t_high`, `t_low`, and `margin_min` against the stored `observations` table. Choose the operating point where **false present = 0**, then minimise the uncertain band subject to that.
*Done when:* a `calibration_report.md` exists showing the sweep and the chosen values, and `thresholds.yaml` is updated.

Phase 6 is not optional. The shipped defaults in §5.1 are guesses. Running this system on uncalibrated thresholds means you do not know its error rate, which means you cannot honestly claim anything about it.

---

## 13. Testing

| Level | Coverage required |
|---|---|
| Unit | quality gate at each threshold boundary; pose classification for five synthetic landmark sets; block merging including the Wednesday two-room case; banding function at each boundary |
| Integration | full enrolment flow via `httpx` against a test database; video pipeline on a committed 30-second clip |
| Data | assert gallery size equals roster size before matching; assert every stored embedding is unit length; assert no duplicate student assignment in results |

Commit a short test video (10–30 seconds, two or three people) and the corresponding enrolment images so the pipeline test is reproducible.

---

## 14. Guardrails

Things that will silently produce wrong answers rather than errors. Each has caused real failures in systems like this.

1. **Mismatched model versions.** Enrolment and recognition embeddings from different models are meaningless together, and nothing will raise. Store and check `model_version` on every comparison.
2. **Gallery not roster-restricted.** Matching against all students instead of the section produces plausible-looking results with a far worse error rate. Assert the size.
3. **NumPy 2.x.** Breaks insightface 0.7.3 in confusing ways. Pin 1.26.4.
4. **`det_size` too small for the source resolution.** Back-row faces vanish before detection. Scale `det_size` with input resolution; tile for 4K.
5. **Skipping track clustering.** Tracker fragmentation turns one student into four "unknown intruders". Cluster before assigning.
6. **Independent best-match instead of global assignment.** Allows one student to be matched twice, which is precisely the proxy loophole the system exists to close.
7. **Defaulting uncertain to present.** Inverts the error asymmetry and makes the system worse than useless for its main purpose.
8. **Using `.embedding` instead of `.normed_embedding`.** Cosine similarity silently becomes an unnormalised dot product, and every threshold in this document becomes meaningless.
9. **Mutating `observations`.** Destroys the ability to recalibrate without reprocessing video.
10. **Loading the face model per request.** Adds seconds to every call and exhausts memory under any concurrency.

---

## 15. What this prototype deliberately does not prove

Be honest about this in any write-up.

Published systems in this area report around 97% accuracy on benchmark datasets and roughly **85% on real classroom photographs**. Back-row scale and occlusion are documented as open limitations, not solved problems. A prototype that works on a video of six people sitting near the camera has not demonstrated it works on sixty people across a room.

The measurements that matter, and that this prototype should produce:

- **Auto-resolution rate** — proportion of the roster decided without human attention
- **False present count** — must be zero; anything else invalidates the system's purpose
- **Per-row recall** — recognition rate broken down by seating distance, which is the number that predicts whether this scales past the front three rows

Report these. Do not report benchmark accuracy figures, which measure something other than what this system does.

---

*End of specification.*
