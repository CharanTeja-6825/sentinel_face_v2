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

## D12 — MediaPipe drives the enrolment front-end; ArcFace still decides identity

**Phase 6.** The enrolment wizard needed things SCRFD's five keypoints cannot supply: real
degree-valued head pose for the guided angle prompts, eye state to catch a blink, and enough
landmarks to draw a live overlay. MediaPipe Face Landmarker gives all three — 478 landmarks, 52
blendshapes and a 4x4 facial transform matrix.

What MediaPipe replaced is **detection and landmarking on the enrolment path only**. It does not
touch identity: the 5 points ArcFace aligns from are still 5 points (`KPS_IDX = (468, 473, 1, 61,
291)` — iris centres, nose tip, mouth corners), still fed to the same `norm_crop` similarity
transform, still embedded by the same glintr100. `FaceEngine.MODEL_VERSION` is therefore deliberately
**unchanged** — the embedding space did not move, so the stored gallery stays valid.

That claim is measured, not asserted. `scripts/verify_alignment_parity.py` embeds the same frame
twice, once aligned from SCRFD keypoints and once from MediaPipe's, and requires cosine > 0.95;
observed range is 0.96–0.98. A new `landmark_source` column records which produced each template.

**The video path does not load MediaPipe and should not.** The RQ worker runs a face mesh per face
per frame for pose we already estimate adequately from SCRFD keypoints, at the cost of a second
model in memory and a second inference lock. Spec §5 says reuse the existing detector when it is
adequate; here it is.

## D13 — Preprocessing enhances the copy that gets DETECTED, never the pixels that get EMBEDDED

**Phase 6.** Poor lighting made MediaPipe fail to find or land a face at all, so
`preprocess.enhance()` (bilateral denoise -> adaptive gamma -> CLAHE on the L channel) was added.
It runs on a downscaled copy that feeds detection, landmarking and nothing else.

**ArcFace always embeds the original pixels.** Two reasons, both load-bearing:

* ArcFace was trained on largely un-enhanced faces. Enhancing what it embeds shifts the embedding
  distribution away from the thresholds the video path is calibrated against (`t_high` 0.60,
  `t_low` 0.45, `cluster_distance` 0.50).
* Every stored template would otherwise depend on the preprocessing parameters. Retuning
  `clahe_clip` would silently invalidate the entire gallery, with nothing raising.

The quality gate also reads the **raw** frame, for the same reason in miniature: blur measured after
a bilateral filter reads sharper than the truth, and brightness measured after adaptive gamma reads
in-range by construction. Preprocessing earns its place upstream of the gate, not as a way past it.

This is what spec §11 asks for — "live recognition preprocessing MUST remain compatible with
registration preprocessing" — and it is why the video path must **not** grow a CLAHE stage of its
own. Both paths do exactly `align(raw_frame, kps5)` -> `embed_aligned([crop])`, and that identity is
the parity guarantee.

## D14 — A track keeps its best few looks, not every frame it appeared in

**Phase 7, the pipeline enhancement.** `run_pipeline` held every sampled frame in a dict for the
duration of the video, because the quality gate and alignment ran *after* the frame loop and needed
the pixels back. At the configured ceilings — `max_duration_minutes: 60`, `sample_fps: 2.0`, a 4K
source — that is ~7,200 full-resolution frames, roughly **180 GB resident**. `max_duration_minutes`
did nothing to prevent it, and the failure mode is an OOM kill partway through a class, not a
readable error.

The gate now runs inside the frame loop against the frame in hand, and each track retains only the
aligned 112x112 crops of its best `observation.max_per_track` looks (default 8, ~300 KB per track).
Memory is a function of how many people are in the room, not how long the video is. The same
restructuring is what spec §7 (a normalised observation object), §9 (bad observation -> track only)
and §10 (a bounded, quality-ranked per-track buffer) ask for — one change, three requirements.

`Detection` already carried `.bbox`, `.kps` and `.det_score`, which is exactly what `quality.assess()`
duck-types on, so the `_CropFace` adapter was deleted rather than rewritten.

**This changes one behaviour, and it is the only one.** A track's mean embedding was the mean of
*every* accepted crop; it is now the mean of the best K. Spec §10 and §29.5 both want that — weak
observations should not dilute a track's identity — but "should be better" is not a measurement, so
`scripts/diagnose_video.py` reports cosine(all-crops mean, best-K mean) per track. Measured on three
tracks where the cap actually evicted something (23→8, 18→8, 12→8): **0.9978 – 0.9986**. The best 8
looks carry essentially all of what the full set carried. Raise `max_per_track` if that ever drops
below ~0.98 on real footage.

Two things deliberately did **not** change with it:

* Rejected observations still maintain their track. A face too small or too blurry to recognise now
  is often sharp and close 300 ms later, and that only helps if the track survived the bad stretch.
  Quality decides whether to RECOGNISE, never whether to TRACK.
* Aggregation is still an unweighted mean over the survivors. Quality-*weighted* aggregation is spec
  §15 and waits for Phase 4, because there is no labelled classroom footage to verify a weighting
  against and inventing one blind is how §24's warning gets ignored.

The per-track diagnostics earned their keep on the first run. The smoke video reported 2 of 6
students present, which previously looked like an accuracy question with nowhere to start. The report
answers it in one line: four of the six tracks retained **zero** crops, each with all 23 observations
rejected `extreme_pose`. That is the ratio-based pose gate against a photo of people looking sideways
— a known limitation of the 5-keypoint estimator, not a matching problem — and no amount of retuning
`t_low` would have touched it. Before this phase that distinction was invisible.

New quality knobs went into their own `observation:` block rather than into `quality:`, which is
read by both the video gate and the enrolment gate. D9 is the record of what a shared-threshold
change does when it goes wrong; the separation makes that class of mistake structurally impossible
here.
