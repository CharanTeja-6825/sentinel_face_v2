import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { SessionStatus } from "@/lib/api";

function elapsed(since: number) {
  const s = Math.floor((Date.now() - since) / 1000);
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export default function JobProgress({ status }: { status: SessionStatus }) {
  const [start] = useState(Date.now());
  const [, tick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (status.status === "failed") {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Processing failed: {status.error_message ?? "no message recorded"}
        </AlertDescription>
      </Alert>
    );
  }

  const pct = Math.round((status.progress ?? 0) * 100);
  return (
    <div className="space-y-2.5 rounded-lg border bg-card p-4 shadow-card">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium capitalize text-card-foreground">
          {status.status}
        </span>
        <span className="tnum text-sm text-muted-foreground">{pct}%</span>
      </div>
      <Progress value={pct} className="h-2 [&>*]:bg-accent" />
      <p className="tnum text-xs text-muted-foreground">
        {status.frames_sampled ?? 0}
        {status.expected_frames ? ` / ~${status.expected_frames}` : ""} frames ·{" "}
        {elapsed(start)} elapsed
      </p>
    </div>
  );
}
