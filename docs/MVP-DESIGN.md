# SentinelFace — MVP design

**What this document is.** The product view of the system that
`ARCHITECTURE.md` describes technically: what SentinelFace does, who it does it
for, what each of those people actually touches, and where the MVP boundary
sits. Everything below is traced to code that exists — endpoints that respond
and screens that render. Where something is a limit rather than a feature, it
is written as a limit.

---

## 1. The problem

Classroom attendance is taken by roll call, a passed-around sheet, or a card
tap. All three share one failure: **the record is produced by a person who
benefits from it being wrong.** A friend answers "present." A sheet gets a
second signature. A card gets handed over. The register ends up describing
who was *claimed* to be there.

Automating this naively does not fix it — it moves the same loophole into
software. If each detected face is independently matched to its best-scoring
student, one student's face can be matched twice, and a room of thirty can
produce forty present marks.

**SentinelFace's answer is that assignment is global and one-to-one.** Faces
found in the footage and students on the roster are matched as a single
optimisation problem (`gallery_service.match_clusters_to_roster`, Hungarian
assignment), so one student can be claimed by at most one face in the room.
That constraint — not the face model — is what closes the loophole. Everything
else in the system exists to give that constraint good inputs.

Two further decisions make the accuracy tractable:

- **Closed-set matching.** A face is compared only against the roster of the
  section that timetable block belongs to — roughly 60 candidates, not the
  whole student table. Error rate is dominated by gallery size, so this scoping
  is what makes the numbers usable at all.
- **Temporal union.** A student does not have to be recognisable in any
  *particular* frame, only occasionally. Detections are linked into tracks
  across time, each track's crops are averaged into one embedding, and
  fragmented tracks are clustered back together. A single back-row frame gives
  a marginal vector; the mean of thirty routinely matches when no individual
  frame would.

---

## 2. Beneficiaries

### The student — enrols once, then does nothing

**Gains:** attendance that does not depend on being awake for roll call, and no
kiosk queue at the door. Enrolment costs about a minute, once per course.

**Touches:** `/register`, and `/live` if they want to satisfy themselves the
system works.

**What is promised to them, and kept in code:**

- Enrolment is refused outright without consent — `POST /enrolment/sessions`
  returns 422 before any frame is accepted.
- **Captured images are never stored.** Frames live in a Redis buffer during
  the session and are dropped at completion; what persists is 16 float vectors
  per student, from which no photograph can be reconstructed.
- An uncertain match defaults to **absent**, never present. A false absent is
  corrected in seconds by a student sitting in the room; a false present is
  invisible to them and is exactly the fraud the system exists to stop.

### The faculty member — reviews, does not label

**Gains:** the record for a 50-minute class becomes an upload and a review of
the handful of faces the system was not sure about, instead of thirty names
read aloud.

**Touches:** `/sessions` (pick the block, upload the video), `/sessions/:id`
(watch progress, review, finalize).

**The design principle on this screen is that the system's confidence is
visible, not hidden.** Results arrive in three bands:

| Band | Condition | What faculty sees |
|---|---|---|
| `confident` | score ≥ 0.60 **and** margin ≥ 0.10 | already marked present, with an evidence crop |
| `uncertain` | score ≥ 0.45 | shown for a decision; **writes nothing on its own** |
| `no_match` | below 0.45 | listed as an unmatched face to attribute or dismiss |

Every automatic decision carries the crop it was made from, so a wrong one is
visible rather than merely wrong. `POST /sessions/{id}/finalize` locks the
session: no further edits, no re-runs.

### The administrator — owns the roster, and therefore the accuracy

**Gains:** one place to see who has enrolled and who has not, before a class
is ever processed.

**Touches:** `/admin` — seed the timetable, add students, populate section
rosters, read enrolment coverage, browse session history.

**Why this role is load-bearing rather than clerical:** the roster *is* the
gallery. A student missing from the section roster cannot be recognised no
matter how well they enrolled, and a student on the roster who never enrolled
is marked absent every time. `GET /admin/sections/{code}/coverage` reports
`enrolled_pct` and names exactly who is still missing, so that gap is
visible before it becomes a wrong attendance record.

### The institution — gets a record it can defend

Every present mark carries its source (`auto` or `manual_override`) and an
image crop. A dispute is settled by looking at the evidence rather than by
weighing two accounts. Sessions record their model version, so a record can be
interpreted years later against the model that produced it.

---

## 3. Features

| Feature | What it does | Endpoints | Screen |
|---|---|---|---|
| **Guided enrolment** | Captures five head angles one at a time — front, left, right, up, down — with live feedback on pose, lighting, sharpness and blinking. The backend owns which angle is being asked for, so the prompt and what is accepted cannot drift apart. | `POST /enrolment/sessions`, `.../frames`, `.../complete` | `/register` |
| **Live test** | Point a webcam at yourself and watch the system name you, running the same detector, quality gate and matching a classroom video runs. Read-only — no attendance is marked. | `POST /recognition/identify` | `/live` |
| **Timetable** | Consecutive periods of the same subject are merged into one block; blocks outside eligible periods are refused with a reason. | `POST /timetable/seed`, `GET /timetable/blocks` | `/sessions` |
| **Video attendance** | Upload classroom footage; a background worker samples frames, detects, tracks, clusters, matches and bands. Progress is reported while it runs. | `POST /sessions`, `.../video`, `GET /sessions/{id}` | `/sessions` |
| **Evidence review** | Three confidence bands, per-decision image crops, manual override, unmatched-face attribution, and a finalize lock. | `GET /sessions/{id}/results`, `PATCH .../decisions`, `PATCH .../unmatched`, `POST .../finalize` | `/sessions/:id` |
| **Roster & coverage** | Students, section rosters, enrolment coverage with the missing students named, session history with per-session auto-resolution rate. | `GET/POST /admin/students`, `POST /admin/sections/{code}/students`, `GET .../coverage`, `GET /admin/sessions` | `/admin` |
| **Honest health** | Reports database, Redis, face model and landmark model state independently, and flags that the period clock times are still unverified. | `GET /health` | `/admin` |

### Why the Live Test exists

Until it did, the only proof the recognition half worked was to upload a video
and wait for a worker. That made the system's central claim unverifiable in the
room where it was being demonstrated — a viewer could enrol and then had
nothing to see.

The Live Test runs the **attendance** path, not a lookalike: the same SCRFD
detector including its 4K tiling rule, the same quality gate, the same
roster-scoped gallery, the same one-to-one assignment and the same banding. It
shows the arithmetic behind each verdict — similarity against `t_high`/`t_low`,
margin against `margin_min`, and the runner-up — so a wrong answer can be
diagnosed rather than merely observed.

One honest caveat, stated on the screen: a live frame gets **one look**, with
no tracking and no cluster averaging. Its score is therefore the pessimistic
case. A face recognised here would be recognised at least as confidently in a
real run.

---

## 4. Journeys

**Setting up a course (administrator, once).**
Seed the timetable → add students → add their roll numbers to the section
roster → watch coverage climb as students enrol → chase the students coverage
names as missing.

**Enrolling (student, once, ~1 minute).**
Enter roll number → read and accept the consent statement → turn head through
five prompted angles, one at a time, with live feedback → 16 templates stored,
images discarded → optionally open the Live Test and confirm the system names
them.

**Taking attendance (faculty, per class).**
Choose section and date → pick the timetable block → create the session →
upload the footage → watch frame progress → review: confident marks already
made with crops, uncertain ones decided by eye, unmatched faces attributed or
dismissed → finalize to lock.

---

## 5. Screens

| Route | For | Purpose |
|---|---|---|
| `/` | everyone | What the system is, who it serves, and the way into each flow |
| `/register` | student | Consent, then guided five-angle capture |
| `/live` | student, faculty, evaluator | Webcam self-test against a section roster |
| `/sessions` | faculty | Pick a block, create a session, upload footage |
| `/sessions/:id` | faculty | Progress, banded results, evidence, override, finalize |
| `/admin` | administrator | Timetable, students, rosters, coverage, history, health |

---

## 6. Out of scope for the MVP

Stated as limits, because a prototype that hides them is worse than one that
does not exist.

- **No authentication or authorisation.** Every screen is open to anyone who
  can reach the host. Nothing records who changed a decision.
- **No liveness detection.** A printed photograph held to the webcam will
  enrol, and a photograph in the classroom will be counted present.
- **No real-time streaming attendance.** The Live Test is a diagnostic, not an
  attendance path; attendance comes from uploaded footage.
- **Accuracy is unmeasured.** No labelled classroom video has been scored
  against ground truth. Every threshold in `matching` and `observation` is a
  starting value, not a calibrated one. `scripts/diagnose_video.py` produces the
  distributions needed to set them; the instrument existing is not the same as
  the measurement having been taken.
- **Fairness is unmeasured.** Recognition error rates vary across demographics.
  Nothing here measures that. The human-review band is the only mitigation
  present.
- **Scale is undemonstrated.** One worker, one section, ~60 students. The queue
  boundary makes horizontal scaling possible; nothing has shown it.
- **The period clock times are unverified.** `/health` reports
  `periods_verified: false` for exactly this reason.

---

## 7. What "done" means for the MVP

1. An administrator can seed a timetable, add students and populate a roster
   from a clean database.
2. A student can enrol through the guided flow and reach 15+ templates covering
   all five angles.
3. **That student can open the Live Test and be named, with the score, margin
   and band shown.** This is the demonstrable proof of the core claim.
4. A faculty member can create a session, upload footage, watch it process, and
   receive banded results with evidence crops.
5. Uncertain results write nothing until a human decides, and finalize locks
   the session.
6. Coverage reports name every roster student who has not yet enrolled.
7. `/health` reports database, Redis, face model and landmark model
   independently, and refuses to report a partially loaded model as loaded.
