# DECISIONS

Every choice not specified by `INIT.md`, per §0.2. Newest last.

---

## D1 — Postgres image is `pgvector/pgvector:pg16`, not `postgres:16-alpine`

**Phase 1.** §3 asks for `postgres 16-alpine` with the pgvector extension. pgvector is not packaged
in the official alpine image, and compiling it into a derived image is work with no payoff.
`pgvector/pgvector:pg16` is the upstream-maintained Postgres 16 image with pgvector preinstalled.
Postgres major version and pgvector behaviour are unchanged.

## D2 — CPU-only inference

**Phase 1.** The build host is Apple Silicon with no CUDA, so `onnxruntime` (not `onnxruntime-gpu`)
and `CTX_ID=-1`. `face_engine._providers()` filters the requested provider list against
`onnxruntime.get_available_providers()`, because asking a CPU-only build for
`CUDAExecutionProvider` raises rather than falling back — that would take the whole app down at
startup. Moving to a CUDA host needs only `onnxruntime-gpu` in requirements and `CTX_ID=0`.

## D3 — antelopev2 archive layout is repaired at load time

**Phase 2.** The `antelopev2.zip` published on the insightface v0.7 release extracts to
`<root>/models/antelopev2/antelopev2/*.onnx` — one directory deeper than insightface's own
`glob(model_dir + '/*.onnx')` looks. The symptom is a bare `assert 'detection' in self.models`
during `FaceAnalysis.__init__`, which says nothing about the cause.
`face_engine._flatten_nested_model_dir()` lifts the five `.onnx` files up one level on first load.
Confirmed loading `scrfd_10g_bnkps.onnx` (detection) and `glintr100.onnx` (recognition) — the exact
pair §3 specifies for antelopev2.

## D4 — `weighted_score()` formula

**Phase 2.** §7.3 calls for a `weighted_score()` but does not define one. Each input is normalised
against its own configured threshold and clipped to [0, 1], then combined:

    0.35 * detection confidence
  + 0.25 * face width
  + 0.25 * sharpness (Laplacian variance)
  + 0.15 * pose centrality

Detection confidence and face width carry the most weight because they are what actually predict
whether the resulting embedding is usable. Size saturates at 3x `min_face_width_px` and sharpness at
5x `min_blur_variance` — past those points, more does not help. The score is used for ranking crops
(best-crop selection, `mean_quality`), never as a gate, so its exact shape is not safety-critical.

## D5 — Pose formula zero point verified; yaw sign convention resolved

**Phase 2.** §7.4 warns that the yaw sign depends on mirroring and must be resolved empirically.

*Zero point.* Evaluating `pose_ratios()` on the canonical ArcFace 112x112 alignment template — a
perfectly frontal face by construction — gives **yaw = +0.006, pitch = -0.010**, classified `front`.
The specified formula is correctly centred; no offset is needed. (Real photos of people looking
slightly downward read pitch ≈ +0.3, which is the estimator working, not drifting.)

*Sign.* Mirroring `t1.jpg` horizontally inverts the yaw of every face with |yaw| meaningfully above
zero (`+0.589 → -0.621`, `-0.367 → +0.303`, `-0.853 → +0.969`; the single non-inverting case is a
near-frontal face at |yaw| < 0.09, i.e. noise). Yaw sign is therefore tied to image orientation, and
the geometry fixes which way:

> `kps` is `[left_eye, right_eye, nose, left_mouth, right_mouth]` in **image** coordinates, so
> `left_eye` is the eye at smaller x — for an unmirrored frame, that is the subject's *right* eye.
> When a subject turns toward their own left, their nose swings toward image-right, so
> `d_left = nose.x - le.x` grows and `d_right = re.x - nose.x` shrinks, giving **yaw > 0**.

**Convention: positive yaw = the subject turned to their own left**, matching `classify_angle()`
returning `"left"` for `yaw >= 0.15`. Angle labels are in the *subject's* frame, which is what the
wizard prompt "Turn your head left" means to a student.

**Consequence the frontend must honour:** the webcam preview is CSS-mirrored (`scaleX(-1)`) because
an unmirrored preview feels wrong to the user, but the canvas frame POSTed to the backend is **not**
mirrored. Mirroring the capture would invert every yaw and make the wizard tell students to turn the
wrong way — a failure invisible to code review.

## D6 — Enrolment frame buffer lives in Redis

**Phase 4.** §7.1 has the backend hold accepted frames in a "session buffer" until `/complete`, but
does not say where. Redis is already a dependency, so the buffer is a Redis key
`enrol:{session_id}` with TTL = `enrolment.session_timeout_minutes`. This avoids inventing a table
for data that is deliberately discarded (§7.6 step 4), and survives a uvicorn `--reload` restart
mid-enrolment, which an in-process dict would not. The TTL also enforces §5.1
`session_timeout_minutes` for free.

## D7 — Gallery/roster size assertion

**Phase 5.** §8.5 says "Assert the gallery size equals the roster size before matching". Taken
literally this fails whenever any roster student has not enrolled — which is the normal case that
the spec's own `enrolled_pct` field (§10 `POST /sessions`) exists to report.

The guarantee that actually matters is that matching never reaches outside the roster (§1.2, §14.2).
So `gallery_service.load_roster_gallery()` asserts:

    set(gallery) == set(enrolled roster)  and  set(gallery) ⊆ set(roster)

and logs `gallery=N enrolled=N roster=M` on every run. A student on the roster with no templates
cannot be matched and is therefore marked absent, which is the correct and honest outcome.

## D8 — Test database is separate

**Phase 3.** Tests run against `sentinelface_test`, created on demand and migrated with the real
Alembic chain (not `create_all`), so the migration path is exercised by the test suite rather than
duplicated. Dev data in `sentinelface` is never touched.

## D9 — Blur is measured at a fixed crop scale

**Phase 5, found on real footage.** §7.3 specifies "variance of Laplacian on the crop" but does not
say at what size the crop is measured, and that omission is load-bearing.

The Laplacian is a per-pixel second derivative, so the same face photographed larger spreads each
edge over more pixels and scores *lower*. Measured on one real crop from the pilot video:

| face width in source | raw variance | normalised to 112 px |
|---|---|---|
| 60 px  | 1585 | 361 |
| 150 px |  646 | 505 |
| 600 px |  123 | 809 |
| 1100 px |  20–41 | 266–841 |

A 13x swing driven purely by subject distance, in the wrong direction. Against `min_blur_variance:
40.0` this meant a 1100 px phone close-up was rejected `too_blurry` on 9 frames out of 10, the track
fell below `min_crops_per_track: 3`, and the session reported zero detections — a silently wrong
answer of exactly the kind §14 warns about, with no error anywhere.

`quality.blur_variance()` now resizes the greyscale crop to **112x112** (`BLUR_REFERENCE_PX`) before
the Laplacian. 112 is the size ArcFace consumes, so sharpness is judged at the resolution the
recogniser actually sees. This collapses the spread to ~2x and puts it in the honest direction (a
smaller face really does carry less detail).

**The threshold value is unchanged at the §5.1 figure of 40.0** — only the measurement was wrong.
Measured at this scale it separates cleanly: real frames 266–841, visibly soft ~122, clearly blurred
~57, unusable <=26. Pinned by `test_blur_metric_does_not_move_with_face_size`.

## D10 — Tiling triggers on the longer side, not the width

**Phase 5, same footage.** The 4K tiling path (§8.3, §14.4) was gated on `width >= 3000`. Phone
video shot upright arrives as 2160x3840, so a genuine 4K source skipped tiling purely because it was
held in portrait. The constant is now `TILING_MIN_DIM` and tests `max(width, height)`.
