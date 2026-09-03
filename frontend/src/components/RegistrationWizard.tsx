import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, ScanFace } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import AngleGuide, { anglePrompt } from "./AngleGuide";
import FaceOverlay from "./FaceOverlay";
import PoseDial from "./PoseDial";
import { cn } from "@/lib/utils";
import { useCamera, grabFrame } from "@/hooks/useCamera";
import { api, errorMessage, type EnrolSession, type FrameResult } from "@/lib/api";

/** §11 — show friendly text, never the raw reason code. */
const FRIENDLY: Record<string, string> = {
  no_face_detected: "No face found — centre yourself in the frame",
  multiple_faces: "More than one face in view — enrol alone",
  low_detection_confidence: "Face unclear — face the camera directly",
  face_too_small: "Move a little closer",
  too_blurry: "Hold still — try better lighting",
  poor_lighting: "Lighting is too dark or too bright",
  extreme_pose: "Turned too far — ease back towards the camera",
  too_similar: "Move slightly, that looks the same as the last one",
  low_quality: "Not sharp enough to keep — move closer, into better light",
  max_samples_reached: "Sample budget reached — finish enrolment",
  // MediaPipe additions (backend D12).
  eyes_closed: "That frame caught a blink — keep your eyes open",
  extreme_roll: "Head is tilted sideways — level your shoulders and eyes",
  no_landmarks: "Could not read your facial features — try better lighting",
};

/**
 * Pacing. This wizard is deliberately UNHURRIED: it is capturing the templates
 * every future attendance match will be scored against, and a template is
 * permanent in a way a single video frame is not.
 *
 * - PROBE is only how often we look at the camera. Most probes bank nothing;
 *   they exist so the student gets live "you are facing the wrong way" feedback.
 * - SETTLE runs after a sample IS banked, so the next one is not the same
 *   micro-instant of the same pose. The backend's diversity check would reject
 *   such a frame anyway — this makes the student's wait deliberate rather than
 *   a wall of "too similar".
 * - STAGE runs when the target angle changes, so the student reads the new
 *   instruction and moves before the camera starts judging them against it.
 */
const PROBE_MS = 700;
const SETTLE_MS = 1200;
const STAGE_MS = 2000;

export default function RegistrationWizard({
  session,
  onDone,
}: {
  session: EnrolSession;
  onDone: (templates: number) => void;
}) {
  const { videoRef, ready, error: cameraError } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inFlight = useRef(false);

  // Wall-clock time before which capture() does nothing. A ref, not state, so
  // changing it never re-renders and never restarts the interval.
  const resumeAt = useRef(0);
  const target = useRef<string | null>(session.target_angle);

  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<FrameResult | null>(null);
  const [pauseNote, setPauseNote] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);

  const progress = last?.angle_progress ?? {};
  const captured = last?.captured_count ?? 0;
  const canComplete = last?.can_complete ?? false;
  const perAngle = last?.min_samples_per_angle ?? session.min_samples_per_angle;

  // The backend owns the stage. Deriving it here instead would let the prompt
  // and the angle actually being accepted drift apart.
  const current = last ? last.target_angle : session.target_angle;

  const hold = useCallback((ms: number, note: string) => {
    resumeAt.current = Date.now() + ms;
    setPauseNote(note);
    window.setTimeout(() => setPauseNote(null), ms);
  }, []);

  const capture = useCallback(async () => {
    if (inFlight.current || Date.now() < resumeAt.current) return;
    // grabFrame draws the RAW, unmirrored video frame — see D5 in the hook.
    const image = grabFrame(videoRef.current, canvasRef.current);
    if (!image) return;

    inFlight.current = true;
    try {
      const { data } = await api.post<FrameResult>(
        `/enrolment/sessions/${session.session_id}/frames`,
        { image },
      );
      setLast(data);
      setError(null);

      const previous = target.current;
      if (data.target_angle !== previous) {
        target.current = data.target_angle;
        hold(
          STAGE_MS,
          data.target_angle
            ? `${previous} done — next: ${anglePrompt(data.target_angle).toLowerCase()}`
            : "All angles captured",
        );
      } else if (data.accepted) {
        hold(SETTLE_MS, "Captured — hold that angle, shift very slightly");
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      inFlight.current = false;
    }
  }, [session.session_id, hold, videoRef]);

  useEffect(() => {
    if (!ready) return;
    const id = setInterval(capture, PROBE_MS);
    return () => clearInterval(id);
  }, [ready, capture]);

  async function complete() {
    setCompleting(true);
    try {
      const { data } = await api.post<{ stored_templates: number }>(
        `/enrolment/sessions/${session.session_id}/complete`,
      );
      onDone(data.stored_templates);
    } catch (e) {
      setError(errorMessage(e));
      setCompleting(false);
    }
  }

  const missing = session.required_angles
    .filter((a) => (progress[a] ?? 0) < perAngle)
    .join(", ");
  const blocker = canComplete
    ? null
    : captured < session.min_samples
      ? `${session.min_samples - captured} more samples needed`
      : `Still need: ${missing}`;

  // `wrong_angle` is the common rejection now and it needs the angle we saw,
  // so it cannot come from the static FRIENDLY map.
  const rejection =
    last && !last.accepted && last.reason
      ? last.reason === "wrong_angle" && current
        ? `You are facing ${last.detected_angle ?? "away"} — ${anglePrompt(current).toLowerCase()}`
        : (FRIENDLY[last.reason] ?? last.reason)
      : null;

  // The backend classified this frame; we only ask whether that matches the ask.
  const onTarget = !!last?.detected_angle && last.detected_angle === current;
  const tone = last?.accepted
    ? "accepted"
    : rejection
      ? onTarget
        ? "rejected"
        : "idle"
      : onTarget
        ? "onTarget"
        : "idle";

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      {/* ── camera ── */}
      <div className="space-y-4">
        <div
          className={cn(
            "relative overflow-hidden rounded-lg border-2 bg-primary transition-colors duration-300",
            // captured = a measured value banked; onTarget = do this; rejected = refused
            tone === "accepted"
              ? "border-measure"
              : tone === "onTarget"
                ? "border-instruct"
                : tone === "rejected"
                  ? "border-refuse"
                  : "border-border",
          )}
        >
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full -scale-x-100"
          />

          {/* Landmarks and the positioning oval share the video's mirroring, because
              the coordinates describe the unmirrored frame that was POSTed (D5). */}
          <div className="pointer-events-none absolute inset-0 -scale-x-100">
            <FaceOverlay landmarks={last?.landmarks ?? null} tone={tone} />
          </div>
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div
              className={cn(
                "h-[72%] aspect-[3/4] rounded-[50%] border-2 transition-colors duration-300",
                tone === "accepted"
                  ? "border-measure/80"
                  : tone === "onTarget"
                    ? "border-instruct/80"
                    : "border-white/40",
              )}
            />
          </div>

          {!ready && !cameraError && (
            <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white/80">
              <ScanFace className="h-4 w-4 animate-pulse" />
              Starting the camera…
            </div>
          )}

          {pauseNote && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-foreground/90 px-4 py-3 text-center text-sm font-medium text-background backdrop-blur-sm">
              {pauseNote}
            </div>
          )}
          <canvas ref={canvasRef} className="hidden" />
        </div>

        {/* Status line under the camera, so the student's eyes stay near the lens. */}
        <div className="min-h-[3.25rem]">
          {cameraError || error ? (
            <Alert variant="destructive">
              <AlertDescription data-slot="body">{cameraError ?? error}</AlertDescription>
            </Alert>
          ) : rejection ? (
            <Alert variant={onTarget ? "refuse" : "instruct"}>
              <AlertDescription data-slot="body">{rejection}</AlertDescription>
            </Alert>
          ) : last?.accepted ? (
            <p className="tnum flex items-center gap-2 border-l-2 border-l-measure py-2.5 pl-3.5 text-sm font-medium text-measure">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              Captured {last.detected_angle} · quality {last.quality_score.toFixed(2)}
            </p>
          ) : null}
        </div>
      </div>

      {/* ── guidance ── */}
      <div className="space-y-6">
        <AngleGuide
          angles={session.required_angles}
          progress={progress}
          perAngle={perAngle}
          current={current}
        />

        <div className="space-y-3 rounded-sm border border-border p-4">
          <div className="flex items-baseline justify-between">
            <span className="stamp font-medium text-muted-foreground">Head position</span>
            <span className="tnum text-xs text-muted-foreground">
              {captured}/{session.min_samples} samples
            </span>
          </div>
          <PoseDial pose={last?.pose ?? null} target={current} inZone={onTarget} />
          <Progress
            value={Math.min(100, (captured / session.min_samples) * 100)}
            className="h-1.5"
          />
        </div>

        <div className="space-y-2">
          <Button
            variant="instruct"
              className="w-full"
            size="lg"
            disabled={!canComplete || completing}
            onClick={complete}
          >
            {completing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Complete enrolment
          </Button>
          {blocker && (
            <p className="text-center text-xs text-muted-foreground">{blocker}</p>
          )}
        </div>
      </div>
    </div>
  );
}
