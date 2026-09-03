import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import VideoUpload from "@/components/VideoUpload";
import PageHeader from "@/components/PageHeader";
import ErrorAlert from "@/components/ErrorAlert";
import EmptyState from "@/components/EmptyState";
import SessionList from "@/components/SessionList";
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
      loadHistory().catch(() => undefined);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader stamp="Faculty" title="Sessions">
        Pick a timetable block, then upload the classroom video for it. Nothing is
        decided until the worker finishes and you review what it was unsure about.
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle>New attendance session</CardTitle>
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
            <EmptyState action="Seed the timetable from the Admin page if this is a fresh database.">
              No blocks for {section} on {day}.
            </EmptyState>
          )}

          <div className="space-y-2">
            {blocks.map((b) => (
              <div
                key={b.id}
                className={cn(
                  "flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-1 py-3 transition-colors",
                  b.eligible ? "hover:bg-muted" : "text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "tnum stamp font-semibold",
                    b.eligible ? "text-instruct" : "text-muted-foreground",
                  )}
                >
                  P{b.start_period}
                  {b.end_period !== b.start_period && `–${b.end_period}`}
                </span>
                <span className="font-medium">{b.course_code}</span>
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
                    <span className="text-sm text-refuse">{b.ineligible_reason}</span>
                  )}
                  <Button
                    size="sm"
                    variant="instruct"
                    disabled={!b.eligible}
                    onClick={() => createSession(b)}
                  >
                    Create session
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <ErrorAlert message={error} />

          {created && (
            <div className="space-y-4 rounded-sm border border-instruct/30 p-4">
              <p className="tnum text-sm">
                Roster {created.expected_count} students · {created.enrolled_pct}% enrolled
                {created.enrolled_pct < 100 && (
                  <span className="text-refuse">
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

      <Card>
        <CardHeader>
          <CardTitle>Session history</CardTitle>
        </CardHeader>
        <CardContent>
          <SessionList sessions={history} />
        </CardContent>
      </Card>

    </div>
  );
}
