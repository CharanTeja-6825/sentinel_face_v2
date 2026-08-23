import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import VideoUpload from "@/components/VideoUpload";
import {
  api,
  errorMessage,
  type Block,
  type SessionHistory,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

type Created = {
  session_id: string;
  expected_count: number;
  enrolled_pct: number;
  roster: { student_id: string; roll_no: string; name: string; enrolled: boolean }[];
};

export default function SessionsPage() {
  const navigate = useNavigate();
  const [section, setSection] = useState("S-67");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [created, setCreated] = useState<Created | null>(null);
  const [history, setHistory] = useState<SessionHistory[]>([]);
  const [error, setError] = useState<string | null>(null);

  const day = DAYS[new Date(`${date}T00:00:00`).getDay()];

  useEffect(() => {
    api
      .get<Block[]>("/timetable/blocks", {
        params: { section, day, on_date: date },
      })
      .then((r) => setBlocks(r.data))
      .catch((e) => setError(errorMessage(e)));
  }, [section, day, date]);

  const loadHistory = () =>
    api.get<SessionHistory[]>("/admin/sessions").then((r) => setHistory(r.data));
  useEffect(() => {
    loadHistory().catch(() => undefined);
  }, []);

  async function createSession(block: Block) {
    setError(null);
    setCreated(null);
    try {
      const { data } = await api.post<Created>("/sessions", {
        block_id: block.id,
        session_date: date,
      });
      setCreated(data);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl">Sessions</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Pick a timetable block, then upload the classroom video for it.
        </p>
      </div>

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">New attendance session</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-4">
            <div className="space-y-2">
              <Label htmlFor="section">Section</Label>
              <Input
                id="section"
                className="w-40"
                value={section}
                onChange={(e) => setSection(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="date">Date ({day})</Label>
              <Input
                id="date"
                type="date"
                className="w-48"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
          </div>

          {blocks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No blocks for {section} on {day}. Seed the timetable from the Admin
              page if this is a fresh database.
            </p>
          )}

          <div className="space-y-2">
            {blocks.map((b) => (
              <div
                key={b.id}
                className={cn(
                  "flex flex-wrap items-center gap-3 rounded-md border p-3.5 transition-colors",
                  b.eligible
                    ? "hover:border-accent/40 hover:bg-accent-light/50"
                    : "bg-muted/40 text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "tnum rounded px-2 py-0.5 text-sm font-semibold",
                    b.eligible
                      ? "bg-accent-light text-accent"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  P{b.start_period}
                  {b.end_period !== b.start_period && `–${b.end_period}`}
                </span>
                <span className="font-medium text-card-foreground">{b.course_code}</span>
                <Badge variant="outline">{b.component}</Badge>
                <span className="text-sm">{b.room}</span>
                {b.time_window && (
                  <span className="tnum text-sm">
                    {new Date(b.time_window.start).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    –
                    {new Date(b.time_window.end).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                )}
                <div className="ml-auto flex items-center gap-3">
                  {/* §11: show WHY an ineligible period cannot be selected. */}
                  {!b.eligible && (
                    <span className="text-sm">{b.ineligible_reason}</span>
                  )}
                  <Button
                    size="sm"
                    className="bg-accent text-accent-foreground hover:bg-accent/90"
                    disabled={!b.eligible}
                    onClick={() => createSession(b)}
                  >
                    Create session
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {created && (
            <div className="space-y-4 rounded-md border border-accent/25 bg-accent-light/50 p-4">
              <p className="tnum text-sm">
                Roster {created.expected_count} students · {created.enrolled_pct}% enrolled
                {created.enrolled_pct < 100 && (
                  <span className="text-warning">
                    {" "}
                    — students without templates can never be matched
                  </span>
                )}
              </p>
              <VideoUpload
                sessionId={created.session_id}
                onQueued={() => navigate(`/sessions/${created.session_id}`)}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Session history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {history.length === 0 && (
            <p className="text-sm text-muted-foreground">No sessions yet.</p>
          )}
          {history.map((s) => (
            <button
              key={s.session_id}
              onClick={() => navigate(`/sessions/${s.session_id}`)}
              className="flex w-full flex-wrap items-center gap-3 rounded-md border p-3.5 text-left transition-colors hover:border-accent/40 hover:bg-accent-light/50"
            >
              <span className="tnum font-medium text-card-foreground">{s.session_date}</span>
              <span className="tnum rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                P{s.start_period}
              </span>
              <Badge variant="outline">{s.status}</Badge>
              <span className="tnum ml-auto text-sm text-muted-foreground">
                {s.detected_count ?? 0}/{s.expected_count} detected
                {s.auto_resolution_rate !== null &&
                  ` · auto ${(s.auto_resolution_rate * 100).toFixed(0)}%`}
              </span>
            </button>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
