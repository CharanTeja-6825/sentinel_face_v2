
## D11 — Enrolment is guided one angle at a time, and the backend owns the stage

**Phase 6, registration polish.** §7.1 draws the flow as a loop *per angle prompt*
(`front → left → right → up → down`), but the frame endpoint it specifies has no notion of which
angle is being asked for: it classifies whatever pose arrives and banks it. `angle_hint` was sent by
the wizard and read by nobody. The two halves therefore disagreed, and the wizard's 700 ms capture
loop resolved the disagreement in favour of speed — a student sitting still filled the `front` quota
in about two seconds while the prompt had already moved on, then spent the rest of the session
fighting `too_similar` on angles the pose classifier kept scoring as `front`.

The templates that came out of this were lopsided: deep in one orientation, minimal in the other
four. That is precisely the gallery shape §8.5's max-over-templates scoring cannot use, because a
side-on classroom crop has no side-on template to match against. The failure is invisible — the
session reports "15 samples, all angles met" either way.

**`enrolment_service.target_angle(samples)` is now the single authority.** It derives the current
target from the buffer — the first angle in `required_angles` order still short of
`min_samples_per_angle` — and `submit_frame()` refuses any frame whose classified pose is not that
angle, with reason `wrong_angle` and the pose it *did* see, so the wizard can say which way to turn.
Deriving rather than storing means a reloaded or resumed client lands on the same stage, and no
column or Redis key had to be added.

*Deadlock avoidance.* When the target is derived only from per-angle quotas, a config with
`min_samples > min_samples_per_angle * len(required_angles)` reaches a state where every angle is
satisfied, `can_complete()` is still False, and no angle wants a frame. `target_angle()` falls back
to round-robin on the least-sampled angle for exactly that case. Simulated across `2/15`, `3/15`,
`3/20` and `4/15`: every configuration terminates with a balanced buffer.

*Two enrolment-only gates,* because these templates are matched against for the rest of the term
while a video frame is discarded after one session:

- `min_quality_score: 0.50` — a floor on `weighted_score()` (D4). The §7.3 gate answers "is this
  usable"; enrolment can afford to ask "is this good", because it can simply request another frame.
  **This is the primary calibration knob for the module** — raise it for stricter vectors, lower it
  if real webcams stall. Reference points from the D4 formula: a good 1280x720 capture scores
  ~0.80–0.85 even at the edge of the yaw bucket, a dim marginal one ~0.22.
- `diversity_max_cosine: 0.95`, tightened from 0.97. Now that a whole quota is collected at one
  orientation, consecutive frames of a held pose are the common case rather than the exception.

`min_samples_per_angle` goes 2 → 3, making `3 x 5 = 15 = min_samples` exactly: one clean pass of the
five angles completes a session, with no leftover top-up phase.

**The wizard's pacing is now deliberate rather than incidental.** It still probes at 700 ms — that
is what produces live "you are facing front, turn to your left" feedback — but it pauses 1200 ms
after each *banked* sample and 2000 ms when the target angle changes, so the student reads the new
instruction and moves before being judged against it. Prompt, step counter and per-angle progress
all render from `target_angle` in the response; the client no longer computes the stage, which is
what let prompt and acceptance drift apart in the first place.
