import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import EmptyState from "@/components/EmptyState";
import type { SessionHistory } from "@/lib/api";

/**
 * Session history existed twice against the same endpoint — as a list of buttons on
 * /sessions and as a table on /admin — in two different designs. One component now,
 * used by both.
 */
export default function SessionList({ sessions }: { sessions: SessionHistory[] }) {
  const navigate = useNavigate();

  if (sessions.length === 0) {
    return (
      <EmptyState action="Create one from a timetable block above.">
        No sessions have been processed yet.
      </EmptyState>
    );
  }

  return (
    <ul className="divide-y divide-border border-y border-border">
      {sessions.map((s) => (
        <li key={s.session_id}>
          <button
            onClick={() => navigate(`/sessions/${s.session_id}`)}
            className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-1 py-3 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="tnum font-medium">{s.session_date}</span>
            <span className="tnum stamp text-muted-foreground">P{s.start_period}</span>
            <Badge variant={s.status === "failed" ? "refuse" : "default"}>{s.status}</Badge>
            <span className="tnum ml-auto text-sm text-measure">
              {s.detected_count ?? 0}/{s.expected_count} detected
              {s.auto_resolution_rate !== null &&
                ` · auto ${(s.auto_resolution_rate * 100).toFixed(0)}%`}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
