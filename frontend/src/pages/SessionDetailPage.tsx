import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, HelpCircle, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import ErrorAlert from "@/components/ErrorAlert";
import Stat from "@/components/Stat";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import JobProgress from "@/components/JobProgress";
import EvidenceGrid from "@/components/EvidenceGrid";
import {
  api,
  errorMessage,
  type ResultRow,
  type Results,
  type SessionStatus,
} from "@/lib/api";

const TERMINAL = ["completed", "failed", "finalized"];
const POLL_MS = 2000;

function Group({
  title,
  count,
  open,
  tone = "no_match",
  hint,
  children,
}: {
  title: string;
  count: number;
  open?: boolean;
  tone?: "confident" | "uncertain" | "no_match";
  /** What the band actually means. These thresholds decide attendance, and a reader
   *  looking at "Uncertain" has no way to know what separates it from "Confident". */
  hint?: string;
  children: React.ReactNode;
}) {
  // ponytail: native <details> instead of a collapsible component. Native disclosure is
  // keyboard-accessible and animates for free; a Radix collapsible would add a
  // dependency to reproduce it.
  // Band colours come from the message classes — see design/ROUND-2-CONTEXT.md.
  // `confident` is settled (accepted ink), `uncertain` is measured but unresolved,
  // `no match` is a refusal to name.
  const mark = {
    confident: "border-l-foreground",
    uncertain: "border-l-measure",
    no_match: "border-l-refuse",
  }[tone];
  return (
    <details open={open} className={cn("overflow-hidden rounded-sm border border-l-2 border-border", mark)}>
      <summary className="flex cursor-pointer items-center gap-2.5 px-4 py-3.5 font-display font-medium hover:bg-muted">
        {title}
        {hint && (
          <Tooltip>
            <TooltipTrigger asChild>
              <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{hint}</TooltipContent>
          </Tooltip>
        )}
        <span className="tnum stamp ml-auto font-semibold text-measure">{count}</span>
      </summary>
      <div className="space-y-1 border-t border-border px-4 py-3">{children}</div>
    </details>
  );
}

function Crop({ row }: { row: ResultRow }) {
  return row.crop_url ? (
    <img
      src={row.crop_url}
      alt=""
      className="h-14 w-14 shrink-0 rounded-sm border border-border object-cover"
    />
  ) : (
    <div className="h-14 w-14 shrink-0 rounded-sm border border-border bg-muted" />
  );
}

export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const { data } = await api.get<SessionStatus>(`/sessions/${id}`);
      setStatus(data);
      if (TERMINAL.includes(data.status)) {
        const r = await api.get<Results>(`/sessions/${id}/results`);
        setResults(r.data);
      }
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The interval depends only on WHETHER polling should run, not on the status object
  // itself — `status` is replaced by every response, so depending on it tore the
  // interval down and rebuilt it on each tick, making the real cadence "POLL_MS after
  // each response lands" and stretching silently whenever the server was slow.
  const running = !!status && !TERMINAL.includes(status.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [running, refresh]);

  async function setDecision(studentId: string, decision: string) {
    setBusy(true);
    try {
      await api.patch(`/sessions/${id}/decisions`, [
        { student_id: studentId, decision },
      ]);
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function resolve(clusterId: number, resolution: string) {
    setBusy(true);
    try {
      await api.patch(`/sessions/${id}/unmatched`, [
        { cluster_id: clusterId, resolution },
      ]);
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function finalize() {
    setBusy(true);
    try {
      await api.post(`/sessions/${id}/finalize`);
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const locked = status.status === "finalized";
  const stats = results?.stats;
  const headcountGap =
    stats && stats.detected_count !== null
      ? Math.abs(stats.detected_count - stats.present_count)
      : 0;

  return (
    <TooltipProvider delayDuration={200}>
    <div className="space-y-6">
      <header className="border-b border-border pb-5">
        {/* This page was reachable only by navigate() and had no way out. */}
        <Link
          to="/sessions"
          className="stamp inline-flex items-center gap-1.5 font-medium text-instruct hover:underline"
        >
          <ArrowLeft className="h-3 w-3" />
          All sessions
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="tnum text-2xl font-semibold">
            {status.session_date} · Period {status.start_period}
          </h1>
          <Badge variant={status.status === "failed" ? "refuse" : "default"}>
            {status.status}
          </Badge>
          {locked && (
            <span className="flex items-center gap-1.5 text-sm text-refuse">
              <Lock className="h-3.5 w-3.5" /> finalized — no further edits
            </span>
          )}
        </div>
      </header>

      <ErrorAlert message={error} />

      {!TERMINAL.includes(status.status) && <JobProgress status={status} />}
      {status.status === "failed" && <JobProgress status={status} />}

      {results && stats && (
        <>
          <Card>
            <CardContent className="grid grid-cols-2 gap-x-6 gap-y-5 py-5 sm:grid-cols-3 lg:grid-cols-5">
              <Stat
                label="detected / expected"
                value={`${stats.detected_count ?? 0} / ${stats.expected_count ?? 0}`}
              />
              <Stat label="present" value={stats.present_count} tone="accepted" />
              <Stat
                label="auto-resolution"
                value={
                  stats.auto_resolution_rate === null
                    ? "—"
                    : `${(stats.auto_resolution_rate * 100).toFixed(0)}%`
                }
              />
              <Stat label="frames sampled" value={stats.frames_sampled ?? 0} />
              <Stat
                label="processing"
                value={stats.processing_ms ? `${(stats.processing_ms / 1000).toFixed(1)}s` : "—"}
              />
              <p className="col-span-full border-t border-border pt-3 text-xs text-muted-foreground">
                {stats.model_version}
              </p>
            </CardContent>
          </Card>

          {headcountGap > 3 && (
            <Alert variant="refuse">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription data-slot="body">
                {stats.detected_count} faces were detected but{" "}
                {stats.present_count} students are marked present — a gap of{" "}
                {headcountGap}. Review the uncertain and unmatched groups before
                finalising.
              </AlertDescription>
            </Alert>
          )}

          <Group
            title="Confident present"
            count={results.confident.length}
            tone="confident"
            hint="Matched above the high threshold with a clear gap to the runner-up. Marked present automatically."
          >
            {results.confident.map((r) => (
              <div
                key={r.cluster_id}
                className="flex items-center gap-3 rounded-sm px-2 py-2 hover:bg-muted"
              >
                <Crop row={r} />
                <span className="font-medium">{r.student?.name}</span>
                <span className="text-sm text-muted-foreground">
                  {r.student?.roll_no}
                </span>
                <span className="tnum ml-auto text-sm text-measure">
                  score {r.score?.toFixed(3)} · margin {r.margin?.toFixed(3)}
                  {r.first_seen_s !== null &&
                    ` · first seen ${r.first_seen_s?.toFixed(1)}s`}
                </span>
              </div>
            ))}
          </Group>

          <Group
            title="Uncertain"
            count={results.uncertain.length}
            open
            tone="uncertain"
            hint="Matched, but either the score or the margin to the runner-up was too low to trust. These count as ABSENT unless you mark them present."
          >
            <p className="pb-2 text-sm text-muted-foreground">
              Uncertain rows count as <strong>absent</strong> unless marked
              present here.
            </p>
            {results.uncertain.map((r) => (
              <div
                key={r.cluster_id}
                className="flex items-center gap-3 rounded-sm px-2 py-2 hover:bg-muted"
              >
                <Crop row={r} />
                <div>
                  <p className="font-medium">{r.student?.name}</p>
                  <p className="tnum text-sm text-muted-foreground">
                    {r.student?.roll_no} · score {r.score?.toFixed(3)} · margin{" "}
                    {r.margin?.toFixed(3)}
                    {r.runner_up && ` · runner-up ${r.runner_up.roll_no}`}
                  </p>
                </div>
                <div className="ml-auto flex gap-2">
                  <Button
                    size="sm"
                    variant="instruct"
                    disabled={locked || busy || !r.student}
                    onClick={() => setDecision(r.student!.student_id, "present")}
                  >
                    Present
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={locked || busy || !r.student}
                    onClick={() => setDecision(r.student!.student_id, "absent")}
                  >
                    Absent
                  </Button>
                </div>
              </div>
            ))}
          </Group>

          <Group
            title="Absent"
            count={results.absent.length}
            open
            tone="no_match"
            hint="On the roster but never matched to a face in the video — including students with no enrolment templates, who can never be matched."
          >
            {results.absent.map((s) => (
              <div
                key={s.student_id}
                className="flex items-center gap-3 rounded-sm px-2 py-2 hover:bg-muted"
              >
                <span className="font-medium">{s.name}</span>
                <span className="text-sm text-muted-foreground">
                  {s.roll_no}
                </span>
                {s.source === "manual_override" && (
                  <Badge variant="secondary">manual</Badge>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={locked || busy}
                  onClick={() => setDecision(s.student_id, "present")}
                >
                  Mark present
                </Button>
              </div>
            ))}
          </Group>

          <Separator />

          <div className="space-y-3">
            <h2 className="text-base">
              Unmatched faces{" "}
              <span className="tnum font-normal text-muted-foreground">
                ({results.unmatched.length})
              </span>
            </h2>
            <EvidenceGrid
              faces={results.unmatched}
              disabled={locked || busy}
              onResolve={resolve}
            />
          </div>

          {!locked && (
            <Button variant="refuse" size="lg" disabled={busy} onClick={finalize}>
              <Lock className="mr-2 h-4 w-4" />
              Finalize session
            </Button>
          )}
        </>
      )}
    </div>
    </TooltipProvider>
  );
}
