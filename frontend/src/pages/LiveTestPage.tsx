import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, ScanFace } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import PageHeader from "@/components/PageHeader";
import ErrorAlert from "@/components/ErrorAlert";
import BandLabel from "@/components/BandLabel";
import DetectionOverlay from "@/components/DetectionOverlay";
import { useCamera, grabFrame } from "@/hooks/useCamera";
import { cn } from "@/lib/utils";
import { api, errorMessage, type Identification, type IdentifiedFace } from "@/lib/api";

/** §11 — friendly text, never the raw reason code. */
const FRIENDLY: Record<string, string> = {
  low_detection_confidence: "Face unclear — turn towards the camera",
  face_too_small: "Too far away — this face is below the minimum width",
  too_blurry: "Motion blur — hold still, or add light",
  poor_lighting: "Too dark or too bright to measure",
  extreme_pose: "Turned too far from the camera",
};

/**
 * SCRFD at 640x640 plus a glintr100 embedding is materially slower on CPU than
 * the enrolment path's MediaPipe probe, so this looks less often than the
 * wizard's 700 ms. `inFlight` drops any tick that arrives while a request is
 * still out, so a slow backend stretches the cadence instead of queueing.
 */
const PROBE_MS = 1000;

export default function LiveTestPage() {
  const { videoRef, ready, error: cameraError } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inFlight = useRef(false);

  const [section, setSection] = useState("S-67");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Identification | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The section the loop is actually using. Editing the input mid-run should not
  // silently change what is being matched against without a restart.
  const active = useRef(section);

  const probe = useCallback(async () => {
    if (inFlight.current) return;
    const image = grabFrame(videoRef.current, canvasRef.current);
    if (!image) return;

    inFlight.current = true;
    try {
      const { data } = await api.post<Identification>("/recognition/identify", {
        image,
        section: active.current,
      });
      setResult(data);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
      // A 404 section or an empty gallery will not fix itself by retrying.
      setRunning(false);
    } finally {
      inFlight.current = false;
    }
  }, [videoRef]);

  useEffect(() => {
    if (!running || !ready) return;
    const id = setInterval(probe, PROBE_MS);
    return () => clearInterval(id);
  }, [running, ready, probe]);

  function start() {
    active.current = section.trim();
    setResult(null);
    setError(null);
    setRunning(true);
  }

  const video = videoRef.current;
  const faces = result?.faces ?? [];

  return (
    <div className="space-y-8">
      <PageHeader stamp="Diagnostic · nothing is recorded" title="Live test">
        Point the camera at yourself and watch the system try to name you. This runs the
        same detector, quality gate and matching that a classroom video runs, so what you
        see here is what attendance would decide. No attendance is marked.
      </PageHeader>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* ── camera ── */}
        <div className="space-y-4">
          <div className="relative overflow-hidden rounded-lg border-2 border-border bg-primary">
            <video ref={videoRef} autoPlay playsInline muted className="w-full -scale-x-100" />
            {running && video && (
              <DetectionOverlay
                faces={faces}
                frameWidth={video.videoWidth}
                frameHeight={video.videoHeight}
              />
            )}

            {!ready && !cameraError && (
              <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white/80">
                <ScanFace className="h-4 w-4 animate-pulse" />
                Starting the camera…
              </div>
            )}
            {running && !result && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 bg-primary/85 px-4 py-3 text-sm font-medium text-primary-foreground backdrop-blur-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                Looking…
              </div>
            )}
            <canvas ref={canvasRef} className="hidden" />
          </div>

          <ErrorAlert message={cameraError ?? error} />

          {running && result && faces.length === 0 && (
            <Alert variant="refuse">
              <AlertDescription data-slot="body">
                No face found in the frame — centre yourself and check the lighting.
              </AlertDescription>
            </Alert>
          )}
        </div>

        {/* ── controls and readout ── */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>What to match against</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="section">Section</Label>
                <Input
                  id="section"
                  value={section}
                  onChange={(e) => setSection(e.target.value)}
                  placeholder="e.g. S-67"
                />
                <p className="text-xs text-muted-foreground">
                  Only this section's roster is searched. That scoping is what makes the
                  accuracy meaningful — matching against every student in the database
                  would give a worse error rate and say nothing about it.
                </p>
              </div>

              <Button
                variant="instruct"
              className="w-full"
                size="lg"
                disabled={!section.trim() || !ready}
                onClick={running ? () => setRunning(false) : start}
              >
                {running ? "Stop" : "Start live test"}
              </Button>

              {result && (
                <p className="tnum text-xs text-muted-foreground">
                  {result.gallery_size} enrolled of {result.roster_size} on {result.section}
                </p>
              )}
            </CardContent>
          </Card>

          {faces.map((face, i) => (
            <FaceReadout key={i} face={face} thresholds={result!.thresholds} />
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * The arithmetic, not just the verdict. A test screen that says "confident" and
 * nothing else cannot be used to work out WHY a match failed, which is the only
 * reason to have one.
 */
function FaceReadout({
  face,
  thresholds,
}: {
  face: IdentifiedFace;
  thresholds: Identification["thresholds"];
}) {
  if (!face.accepted) {
    return (
      <div className="border-l-2 border-l-refuse py-2.5 pl-3.5">
        <p className="stamp font-medium text-refuse">Face not usable</p>
        <p className="mt-1.5 text-sm text-foreground">
          {FRIENDLY[face.reason ?? ""] ?? face.reason ?? "Rejected by the quality gate"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Nothing is matched against a crop this poor — the video pipeline drops it too.
        </p>
      </div>
    );
  }

  const score = face.score ?? 0;
  const margin = face.margin ?? 0;

  return (
    <div className="space-y-3 rounded-sm border border-border p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="font-display text-lg font-medium">
          {face.name ?? "Not recognised"}
        </span>
        <BandLabel band={face.band} />
      </div>
      {face.roll_no && <p className="tnum text-sm text-measure">{face.roll_no}</p>}

      <dl className="tnum space-y-2 text-xs">
        <Row
          label="Similarity"
          value={score.toFixed(3)}
          note={`needs ≥ ${thresholds.t_high.toFixed(2)} to be automatic, ≥ ${thresholds.t_low.toFixed(2)} to be shown at all`}
          ok={score >= thresholds.t_high}
        />
        <Row
          label="Margin over runner-up"
          value={margin.toFixed(3)}
          note={`needs ≥ ${thresholds.margin_min.toFixed(2)}${face.runner_up_roll ? ` · next best ${face.runner_up_roll}` : ""}`}
          ok={margin >= thresholds.margin_min}
        />
        <Row label="Crop quality" value={face.quality_score.toFixed(2)} note="" ok />
      </dl>

      {face.band === "uncertain" && (
        <p className="text-xs text-muted-foreground">
          In a real session this would be shown to faculty and default to <em>absent</em>.
          A false absent is corrected in seconds; a false present is invisible.
        </p>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  note,
  ok,
}: {
  label: string;
  value: string;
  note: string;
  ok: boolean;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className={cn("font-semibold", ok ? "text-measure" : "text-refuse")}>
          {value}
        </dd>
      </div>
      {note && <p className="mt-0.5 text-[0.6875rem] leading-relaxed text-muted-foreground">{note}</p>}
    </div>
  );
}
