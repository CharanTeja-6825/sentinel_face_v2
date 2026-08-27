# Enhanced Surveillance Face Recognition Pipeline
## Claude Code Implementation & Research Specification

## 0. Mission

Enhance the **existing video-stream face recognition pipeline** into a robust, surveillance-oriented system.

The existing **face registration/enrollment pipeline is already complete and should not be rewritten**.

The live pipeline must be designed around:

- variable face distance / resolution
- multiple simultaneous faces
- pose variation
- illumination variation
- blur and sensor/compression noise
- intermittent visibility
- temporal evidence
- open-set identification
- real-time performance
- graceful degradation

The objective is **not** to recognize every frame independently.

The objective is:

> **Detect → Track → Evaluate quality → Select useful observations → Embed → Aggregate temporal evidence → Search → Confirm identity.**

---

# 1. Before Writing Code: Inspect the Existing System

Claude Code MUST first inspect the repository and produce a concise architecture map.

Identify the current implementation of:

- video/RTSP ingestion
- frame decoding
- frame sampling
- face detection
- face tracking, if present
- face cropping/alignment
- preprocessing
- embedding generation
- vector search/database
- recognition thresholds
- event generation
- frontend/live-stream integration
- GPU/CPU inference
- queues/workers

Then map the existing implementation against this target architecture:

```text
Video / RTSP
      ↓
Frame Sampling
      ↓
Face Detection
      ↓
Face Tracking
      ↓
Face Observation
      ↓
Quality Assessment
      ↓
Best Observation Selection
      ↓
Alignment + Model Preprocessing
      ↓
Embedding
      ↓
Temporal Embedding Buffer
      ↓
Track-Level Aggregation
      ↓
1:N Search
      ↓
Open-Set Decision
      ↓
Temporal Confirmation
      ↓
Identity Event
```

Do not replace working components simply because a different implementation is theoretically better.

---

# 2. Research Before Architecture Changes

Before making significant architectural changes, Claude Code SHOULD inspect the primary sources listed in Section 14.

Research priorities:

1. NIST FIVE and NIST video face-quality work
2. primary papers/repositories for tracking
3. primary documentation for the existing detector/recognition stack
4. official documentation for vector search
5. commercial surveillance architecture references
6. recent low-resolution video recognition research

Use sources to understand **principles and evaluation methodology**, not to blindly copy implementations.

Do not assume a published benchmark transfers to our camera, population, lighting, sensor, compression, or deployment environment.

When sources disagree, prioritize:

```text
NIST / peer-reviewed primary research
        >
official project documentation
        >
official vendor documentation
        >
secondary articles / blogs
```

---

# 3. Core Architectural Principle: Track First, Recognize Second

Do NOT treat:

```text
Frame → embedding → search → identity
```

as the primary live-recognition loop.

Instead:

```text
Frame
 ↓
Detection
 ↓
Track association
 ↓
Track-specific observations
 ↓
Evidence accumulation
 ↓
Identity decision
```

A `track_id` represents a physical face trajectory and is **not** an identity.

Example:

```text
track_id = 381

frame 100 → face
frame 101 → same face
frame 102 → same face
frame 103 → same face
...
```

The tracker answers:

> Is this the same observed face as before?

The recognition system answers:

> Who is this face?

Keep those responsibilities separate.

---

# 4. Video Ingestion and Frame Scheduling

Separate these rates:

```text
camera FPS
detection FPS
tracking FPS
embedding FPS
search FPS
```

Do not automatically run every expensive operation at camera FPS.

The implementation should support configurable/adaptive scheduling.

Example:

```text
Camera: 25–30 FPS
        ↓
Tracking: near real-time
        ↓
Detection: periodic/adaptive
        ↓
Embedding: selected observations only
        ↓
Search: only when sufficient evidence exists
```

Requirements:

- bounded queues
- no unbounded frame backlog
- stale-frame dropping
- timestamps/frame IDs
- minimal frame copies
- reusable inference sessions
- controlled CPU↔GPU transfers
- graceful backpressure

For a live system, a current frame is generally more valuable than processing an old frame late.

---

# 5. Face Detection

Reuse the existing detector if it is adequate.

If detector changes are justified, evaluate candidates against the actual deployment data rather than benchmark reputation alone.

Detection output should normalize into:

```text
bbox
detection_confidence
landmarks/keypoints (if available)
frame_id
timestamp
```

Requirements:

- support multiple faces
- configurable minimum face size
- configurable detection confidence
- preserve small detections for tracking when useful
- do not force recognition for unusably small faces

SCRFD is a useful reference implementation for an efficient high-accuracy face detector. See the sources in Section 14.

---

# 6. Multi-Object Face Tracking

Introduce or improve a multi-face tracker.

Suitable established tracker families include:

- ByteTrack
- BoT-SORT
- DeepSORT

Do not select a tracker purely by popularity. Benchmark:

- ID stability
- identity switches
- missed tracks
- recovery after short occlusion
- latency
- CPU/GPU cost

Maintain:

```text
track_id
first_seen
last_seen
last_bbox
track_state
observation_count
miss_count
recognition_state
```

Support:

```text
TRACK_CREATED
TRACK_ACTIVE
TRACK_TEMPORARILY_LOST
TRACK_REACQUIRED
TRACK_EXPIRED
```

---

# 7. Face Observation Abstraction

Create a normalized internal observation object independent of the recognition model.

Suggested shape:

```json
{
  "track_id": "381",
  "frame_id": 18291,
  "timestamp": 1724400000.123,
  "bbox": {
    "x": 100,
    "y": 80,
    "width": 145,
    "height": 170
  },
  "detection_confidence": 0.97,
  "quality": {
    "overall": 0.91,
    "face_size": 0.95,
    "blur": 0.88,
    "pose": 0.94,
    "illumination": 0.86,
    "occlusion": 0.98
  },
  "pose": {
    "yaw": 3.2,
    "pitch": -2.1,
    "roll": 0.8
  },
  "embedding": null
}
```

Keep this representation extensible.

---

# 8. Quality-Aware Recognition

Quality is a **decision gate**, not just telemetry.

For every observation evaluate at least:

### Face size / effective resolution

Use actual face pixel dimensions and/or a more meaningful effective-resolution metric.

Do not define universal thresholds without testing.

Suggested operational bands:

```text
HIGH
MEDIUM
LOW
UNUSABLE
```

### Pose

Evaluate:

```text
yaw
pitch
roll
```

Prefer better-frontal observations for recognition, but allow configurable tolerances.

### Blur

Estimate:

- motion blur
- defocus blur

Do not assume sharpening fixes blur.

### Illumination

Evaluate:

- underexposure
- overexposure
- severe shadows
- backlighting
- uneven illumination

### Occlusion

Evaluate:

- hands
- masks
- major facial obstruction
- severe hair obstruction
- other objects

Do not automatically reject normal glasses.

### Detection confidence

Use it as a quality signal, not as identity confidence.

---

# 9. Quality Policy

Bad observations should usually become:

```text
TRACK ONLY
```

rather than:

```text
RECOGNIZE ANYWAY
```

Example:

```text
Detection
   ↓
Quality
   ├── unusable → maintain track / wait
   └── usable   → recognition candidate
```

This allows the system to exploit the temporal nature of video.

If a person is currently represented by a 25-pixel blurry face but may produce a 70-pixel sharp face 300 ms later, **wait for the better evidence**.

---

# 10. Best-Observation Buffer

Maintain a bounded quality-aware buffer per track.

Example:

```text
Track 381

frame A → quality 0.42
frame B → quality 0.73
frame C → quality 0.94
frame D → quality 0.36
frame E → quality 0.88
```

Retain the strongest useful observations.

Rank using configurable components such as:

```text
face size
pose
blur
illumination
occlusion
detection confidence
```

Do not store every frame indefinitely.

---

# 11. Recognition Preprocessing

For accepted observations:

```text
Face crop
   ↓
Landmark-based alignment
   ↓
Model-specific resize
   ↓
Model-specific color conversion
   ↓
Model-specific normalization
   ↓
Recognition model
```

Critical requirement:

> Live recognition preprocessing MUST remain compatible with registration preprocessing for the same recognition model/version.

Track and version:

```text
model_name
model_version
embedding_dimension
preprocessing_version
```

Do not introduce arbitrary:

- sharpening
- CLAHE
- aggressive denoising
- beautification
- generic histogram manipulation

unless controlled experiments show a recognition improvement on the target data.

---

# 12. Enhancement / Super-Resolution

Treat image enhancement as an **experimental branch**, not a mandatory production stage.

Do NOT assume:

```text
low-resolution face
 → super-resolution
 → better recognition
```

is true.

If the sensor did not capture identity information, enhancement cannot reliably reconstruct it.

Evaluate any enhancement against:

```text
baseline embedding
vs
enhanced embedding
```

using recognition metrics.

Default behavior should prefer:

```text
low-quality observation
 → wait for better observation
```

over aggressive hallucination.

---

# 13. Embedding Generation

Use the same recognition model and compatible preprocessing as registration.

For each accepted observation:

```text
aligned face
 ↓
recognition model
 ↓
embedding
 ↓
L2 normalization
```

Do not compare incompatible embedding spaces.

Do not change the registration model without explicitly designing a migration strategy.

---

# 14. Temporal Embedding Buffer

Each active track should maintain a bounded embedding buffer:

```text
track_id
 ├── embedding_1 + quality
 ├── embedding_2 + quality
 ├── embedding_3 + quality
 └── ...
```

Do not search the vector database for every embedding by default.

Generate recognition evidence periodically or when the track has accumulated enough new/high-quality information.

---

# 15. Track-Level Embedding Aggregation

The baseline should be:

```text
selected embeddings
      ↓
quality filtering
      ↓
mean / quality-weighted mean
      ↓
L2 normalization
      ↓
track embedding
```

Start with simple aggregation.

Only introduce sophisticated weighting after establishing a measurable baseline.

Do not allow low-quality observations to dominate the aggregate.

---

# 16. Open-Set 1:N Identification

The gallery search must support:

```text
KNOWN
UNKNOWN
INSUFFICIENT_EVIDENCE
```

Do not blindly assign:

```text
nearest vector = identity
```

because every query has a nearest vector.

Use:

```text
query embedding
 ↓
top-k candidates
 ↓
similarity score
 ↓
operating threshold
 ↓
known / unknown
```

Thresholds MUST be configurable and calibrated using deployment data.

NIST FIVE is specifically relevant because it evaluates the problem of identifying or ignoring people in video, including open-set identification.

---

# 17. Temporal Identity Confirmation

Never rely on one weak recognition result when temporal evidence is available.

Example:

```text
frame 1 → Person A, 0.62
frame 2 → Person A, 0.71
frame 3 → Person A, 0.76
frame 4 → Person A, 0.78
frame 5 → Person A, 0.77

→ confirmed Person A
```

Implement configurable confirmation logic using combinations of:

- number of supporting observations
- aggregate similarity
- consecutive evidence
- confidence accumulation
- state hysteresis

---

# 18. Recognition State Machine

Suggested state machine:

```text
UNSEEN
  ↓
TRACKING
  ↓
COLLECTING_EVIDENCE
  ↓
CANDIDATE
  ├── UNKNOWN
  └── CONFIRMED
          ↓
      TRACK_LOST
          ↓
       EXPIRED
```

Do not emit the same identity event on every frame.

Implement:

- event deduplication
- cooldown
- hysteresis
- identity-change handling

---

# 19. Distance-Aware Recognition

Treat face resolution as an operational constraint.

Example:

```text
HIGH effective resolution
→ normal recognition

MEDIUM resolution
→ require more evidence

LOW resolution
→ track / wait

UNUSABLE
→ no recognition
```

Do not treat all detected faces equally.

The exact boundaries must be learned from the actual camera setup.

---

# 20. Lighting / Noise / Compression

Use a hierarchy:

```text
Good frame
→ normal pipeline

Moderately degraded frame
→ quality filtering + temporal evidence

Severely degraded frame
→ wait for better observation
```

Avoid globally applying expensive restoration.

If enhancement is introduced:

1. create an A/B baseline
2. evaluate on real target footage
3. measure recognition accuracy
4. measure false accepts/rejects
5. measure latency
6. keep enhancement only if it improves the complete system

---

# 21. Vector Search

Use the existing vector store if it meets scale/latency requirements.

If a vector index is required, FAISS is a strong reference implementation for dense-vector similarity search.

Support:

```text
top_k
similarity metric
index configuration
threshold
gallery version
```

Keep vector-search infrastructure separate from recognition logic.

---

# 22. Performance

The pipeline should be asynchronous where appropriate.

Logical workers:

```text
Decoder
Detector
Tracker
Quality
Embedding
Search
Event Processor
```

Use bounded queues.

Prioritize:

1. real-time responsiveness
2. current frames
3. active tracks
4. high-quality observations

Avoid:

- stale frame backlogs
- repeated model initialization
- repeated preprocessing
- unnecessary frame copies
- unnecessary GPU↔CPU movement
- unnecessary embedding generation
- unnecessary vector searches

Profile before optimizing.

---

# 23. Observability

Expose operational metrics:

```text
camera FPS
processed FPS
detection FPS
active tracks
faces/frame
track duration
face-size distribution
quality distribution
embedding latency
search latency
queue depth
dropped frames
recognition attempts
confirmed identities
unknown rate
```

During development, expose per-track diagnostics:

```text
track_id
bbox
face size
pose
quality
embedding count
best similarity
candidate identity
recognition state
```

Do not permanently retain raw biometric frames merely for telemetry.

---

# 24. Evaluation

Build a repeatable evaluation set from the actual target environment.

Test across:

### Distance

```text
near
medium
far
failure range
```

### Lighting

```text
normal
low light
backlit
uneven
overexposed
```

### Motion

```text
stationary
walking
running
camera motion
```

### Pose

```text
frontal
moderate yaw
large yaw
pitch variation
```

### Degradation

```text
compression
sensor noise
motion blur
low resolution
```

Measure:

```text
FAR
FRR
TAR
open-set identification accuracy
unknown rejection
track-level accuracy
time-to-recognition
end-to-end latency
throughput
GPU/CPU utilization
```

Evaluate multiple operating thresholds.

Do not use visual quality as the success criterion.

---

# 25. Camera/System-Level Principle

Do not treat the neural network as the entire surveillance system.

Performance is jointly determined by:

```text
camera
+
sensor
+
lens
+
mounting
+
field of view
+
lighting
+
compression
+
detection
+
tracking
+
quality filtering
+
recognition
+
temporal aggregation
+
decision thresholds
```

If the camera consistently produces unusable face resolution, changing the recognition model is unlikely to solve the underlying problem.

---

# 26. Research Sources

Claude Code SHOULD retrieve and inspect these sources before making architecture decisions.

## Tier 1 — Evaluation / Scientific Ground Truth

### NIST Face in Video Evaluation (FIVE)

https://www.nist.gov/programs-projects/face-video-evaluation-five

Use this to understand:

- open-set face identification in video
- degraded video
- low-resolution imagery
- non-cooperative subjects
- operational evaluation
- accuracy/speed tradeoffs

NIST's current FIVE page describes the evaluation as assessing whether systems correctly identify or ignore people appearing in video, including degraded video imagery. citeturn0search0turn0search1

### NIST IR 8173 — Face in Video Evaluation

https://www.nist.gov/publications/face-video-evaluation-five-face-recognition-non-cooperative-subjects

Study the methodology and operational problem definition. citeturn0search1

### NIST IR 8004 — Face Quality and Factor Measures for Video

https://www.nist.gov/publications/identifying-face-quality-and-factor-measures-video

Use this specifically when designing quality metrics.

NIST identifies factors including pose, face size, face detection confidence, environment and sensor, and reports that face size and detection confidence can be useful quality indicators for video recognition. citeturn0search3turn0search14

### NIST Biometric Evaluations

https://www.nist.gov/itl/iad/btg/resources/biometrics-evaluations

Use this to understand the broader NIST biometric evaluation ecosystem and distinguish still-image FR evaluation from video evaluation. citeturn0search6

---

## Tier 2 — Face Detection / Recognition Reference

### InsightFace

https://github.com/deepinsight/insightface

Study:

- SCRFD
- ArcFace
- alignment
- recognition pipeline structure
- model evaluation
- inference architecture

InsightFace documents SCRFD as an efficient high-accuracy face detector and provides recognition methods including ArcFace and related approaches. citeturn0search5turn0search10turn0search16

IMPORTANT: inspect the licensing of the exact model/weights being used before commercial deployment. Do not infer model licensing solely from repository source-code licensing.

### SCRFD

https://github.com/deepinsight/insightface/tree/master/detection/scrfd

Use this as the primary detector reference if the current system uses or evaluates SCRFD. citeturn0search5

---

## Tier 3 — Tracking

### ByteTrack

Primary paper / repository should be retrieved and inspected.

Research:

- association strategy
- detection-to-track association
- handling low-score detections
- identity switches
- real-time tracking

Do not copy a tracker blindly. Benchmark it against the current tracker and target footage.

---

## Tier 4 — Vector Search

### FAISS

https://github.com/facebookresearch/faiss

Use for:

- dense-vector similarity search
- index selection
- top-k search
- GPU acceleration
- scaling considerations

FAISS is a Meta-developed library for efficient similarity search and clustering of dense vectors and supports CPU/GPU implementations. citeturn0search4

---

## Tier 5 — Capture / Landmark Reference

### MediaPipe Face Landmarker

https://developers.google.com/mediapipe/solutions/vision/face_landmarker

Use when the existing system needs landmark/pose/capture-side analysis.

Do NOT treat MediaPipe landmarks as the identity embedding itself.

---

## Tier 6 — Commercial Surveillance Architecture References

Use these only to study **system architecture, operational UX, edge/cloud division, analytics pipelines, tracking, event generation and forensic search**.

Do not copy proprietary implementations.

### Hikvision DeepinMind

https://www.hikvision.com/en/core-technologies/ai/

Study:

- edge AI
- camera/NVR processing
- face analytics
- video structuralization
- large-scale surveillance architecture

### Axis Video Analytics

https://www.axis.com/products/video-analytics

Study:

- edge analytics
- camera-side processing
- metadata
- bandwidth/latency considerations
- analytics application architecture

### Avigilon

https://www.avigilon.com/

Study:

- multi-camera analytics
- Appearance Search
- video analytics services
- centralized/edge processing

Avigilon's current documentation explicitly describes Appearance Search and Face Recognition as analytics services associated with its video-management architecture. citeturn0search19

### Dahua WizMind

https://www.dahuasecurity.com/solutions/technology/wizmind

Study:

- edge AI
- camera/NVR architecture
- face analytics
- event-driven surveillance

### Hanwha Vision

https://www.hanwhavision.com/

Study:

- edge AI cameras
- on-device analytics
- camera/server division

### Genetec Security Center

https://www.genetec.com/products/unified-security/genetec-security-center

Study:

- enterprise VMS
- analytics integration
- event architecture
- multi-camera system design

### BriefCam

https://www.briefcam.com/

Study:

- forensic video indexing
- search architecture
- large-scale video analytics
- metadata-driven investigation

---

# 27. Research Rules for Claude Code

When researching:

### Prefer

```text
NIST
peer-reviewed papers
official project repositories
official documentation
official vendor documentation
```

### Avoid relying on

```text
SEO articles
affiliate comparisons
unverified GitHub forks
benchmark screenshots without methodology
vendor marketing claims as accuracy evidence
```

For any claimed improvement, ask:

1. On what dataset?
2. What camera/sensor?
3. What face resolution?
4. What operating threshold?
5. Is it detection, verification, or identification?
6. Is it image or video?
7. Is it closed-set or open-set?
8. Does it measure accuracy, latency, or both?
9. Does the evaluation resemble our deployment?

---

# 28. Implementation Strategy

Implement incrementally.

## Phase 1 — Existing pipeline mapping

- inspect current code
- document current flow
- identify bottlenecks
- identify missing stages
- do not change behavior yet

## Phase 2 — Track-centric architecture

- introduce normalized face observations
- stable track IDs
- detection/tracking separation
- bounded track lifecycle

## Phase 3 — Quality system

- face-size metrics
- pose
- blur
- illumination
- occlusion
- quality scoring
- best-observation buffer

## Phase 4 — Temporal recognition

- embedding buffer
- quality filtering
- aggregation
- 1:N search
- open-set threshold
- temporal confirmation

## Phase 5 — Performance

- asynchronous workers
- adaptive detection cadence
- batching
- queue management
- GPU optimization

## Phase 6 — Experimental improvements

Only after a strong baseline:

- enhancement
- super-resolution
- restoration
- specialized low-resolution models
- camera-specific calibration

---

# 29. Non-Negotiable Constraints

1. Do not rewrite the registration pipeline.
2. Do not replace the current recognition model without benchmarking.
3. Do not recognize every frame by default.
4. Do not force an identity from nearest-neighbor search without an open-set threshold.
5. Do not let low-quality observations dominate track-level identity.
6. Do not assume super-resolution improves recognition.
7. Do not add expensive preprocessing without measured benefit.
8. Do not create unbounded queues or memory buffers.
9. Do not store raw biometric frames unnecessarily.
10. Do not optimize benchmark metrics while ignoring actual camera footage.
11. Do not treat a track ID as an identity.
12. Do not emit repeated identity events for the same track without deduplication.
13. Do not make thresholds impossible to configure.
14. Preserve existing working APIs unless change is demonstrably necessary.

---

# 30. Definition of Done

The enhanced system is complete when:

- multiple faces are tracked simultaneously
- recognition is track-centric rather than frame-centric
- poor observations are rejected/deferred
- high-quality observations are selected automatically
- registration/live preprocessing remains compatible
- embeddings are temporally aggregated
- 1:N search supports UNKNOWN
- identity decisions require configurable evidence
- recognition events are deduplicated
- low-resolution faces can be tracked without forced recognition
- severe degradation causes graceful deferral
- processing remains real-time under expected load
- metrics expose system behavior
- thresholds are configurable
- tests cover major pipeline states
- real target footage is used for evaluation
- existing functionality remains intact

---

# 31. Final Instruction to Claude Code

Do not begin by implementing every section.

First:

1. inspect the existing repository
2. retrieve and read the highest-priority sources
3. map the current architecture
4. identify the smallest missing architectural pieces
5. produce an implementation plan
6. implement Phase 1
7. test it
8. measure it
9. proceed incrementally

The target is a **quality-aware, track-based, temporally aggregated, open-set video face recognition system** built on top of the existing implementation.

Prefer measured engineering improvements over adding more models.
