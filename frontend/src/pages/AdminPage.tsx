import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  api,
  errorMessage,
  type Coverage,
  type SessionHistory,
  type Student,
} from "@/lib/api";

export default function AdminPage() {
  const navigate = useNavigate();
  const [students, setStudents] = useState<Student[]>([]);
  const [section, setSection] = useState("S-67");
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [history, setHistory] = useState<SessionHistory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [newRoll, setNewRoll] = useState("");
  const [newName, setNewName] = useState("");
  const [rosterRolls, setRosterRolls] = useState("");

  const loadStudents = () =>
    api.get<Student[]>("/admin/students").then((r) => setStudents(r.data));
  const loadCoverage = (code: string) =>
    api
      .get<Coverage>(`/admin/sections/${code}/coverage`)
      .then((r) => setCoverage(r.data))
      .catch(() => setCoverage(null));

  useEffect(() => {
    loadStudents().catch((e) => setError(errorMessage(e)));
    api.get<SessionHistory[]>("/admin/sessions").then((r) => setHistory(r.data));
  }, []);
  useEffect(() => {
    loadCoverage(section);
  }, [section]);

  async function run(fn: () => Promise<unknown>, message: string) {
    setError(null);
    setNote(null);
    try {
      await fn();
      setNote(message);
      await loadStudents();
      await loadCoverage(section);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Admin</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Roster, enrolment coverage and session history.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {note && (
        <Alert className="border-success/30 bg-success/5">
          <AlertDescription className="text-foreground">{note}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="setup" className="space-y-6">
        <TabsList>
          <TabsTrigger value="setup">Setup</TabsTrigger>
          <TabsTrigger value="coverage">Coverage</TabsTrigger>
          <TabsTrigger value="students">Students</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="setup">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Setup</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <Button
              variant="outline"
              onClick={() =>
                run(
                  () => api.post("/timetable/seed"),
                  "Timetable seeded (idempotent).",
                )
              }
            >
              Seed timetable
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <Input
              className="w-44"
              placeholder="Roll number"
              value={newRoll}
              onChange={(e) => setNewRoll(e.target.value)}
            />
            <Input
              className="w-56"
              placeholder="Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <Button
              className="bg-accent text-accent-foreground hover:bg-accent/90"
              disabled={!newRoll.trim() || !newName.trim()}
              onClick={() =>
                run(async () => {
                  await api.post("/admin/students", {
                    roll_no: newRoll.trim(),
                    name: newName.trim(),
                  });
                  setNewRoll("");
                  setNewName("");
                }, "Student created.")
              }
            >
              Add student
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <Input
              className="w-96"
              placeholder="Roll numbers to add to the section, comma separated"
              value={rosterRolls}
              onChange={(e) => setRosterRolls(e.target.value)}
            />
            <Button
              variant="outline"
              disabled={!rosterRolls.trim()}
              onClick={() =>
                run(async () => {
                  await api.post(`/admin/sections/${section}/students`, {
                    roll_nos: rosterRolls
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  });
                  setRosterRolls("");
                }, `Roster for ${section} updated.`)
              }
            >
              Add to {section}
            </Button>
          </div>
        </CardContent>
      </Card>

        </TabsContent>

        <TabsContent value="coverage">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Section coverage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            className="w-40"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          />
          {coverage ? (
            <>
              <Progress
                value={coverage.enrolled_pct}
                className="h-2 [&>*]:bg-accent"
              />
              <p className="tnum text-sm">
                <span className="text-2xl font-semibold text-card-foreground">
                  {coverage.enrolled_pct}%
                </span>{" "}
                <span className="text-muted-foreground">
                  — {coverage.enrolled} of {coverage.roster_size} enrolled
                </span>
              </p>
              {coverage.missing.length > 0 && (
                <p className="text-sm text-muted-foreground">
                  Still to enrol:{" "}
                  {coverage.missing.map((m) => `${m.roll_no} ${m.name}`).join(", ")}
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              No section {section}.
            </p>
          )}
        </CardContent>
      </Card>

        </TabsContent>

        <TabsContent value="students">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Students</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Roll no</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Consent</TableHead>
                <TableHead className="text-right">Templates</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="tnum">{s.roll_no}</TableCell>
                  <TableCell>{s.name}</TableCell>
                  <TableCell className="text-muted-foreground">{s.consent_given ? "yes" : "no"}</TableCell>
                  <TableCell className="tnum text-right">
                    {s.template_count}
                  </TableCell>
                  <TableCell>
                    <Badge
                      className={
                        s.enrolled
                          ? "bg-success/10 text-success hover:bg-success/10"
                          : "bg-muted text-muted-foreground hover:bg-muted"
                      }
                    >
                      {s.enrolled ? "enrolled" : "not enrolled"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

        </TabsContent>

        <TabsContent value="history">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">Session history</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Detected</TableHead>
                <TableHead className="text-right">Uncertain</TableHead>
                <TableHead className="text-right">Auto-resolution</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((s) => (
                <TableRow
                  key={s.session_id}
                  className="cursor-pointer hover:bg-accent-light/60"
                  onClick={() => navigate(`/sessions/${s.session_id}`)}
                >
                  <TableCell className="tnum">
                    {s.session_date}
                  </TableCell>
                  <TableCell className="tnum">
                    {s.start_period}
                  </TableCell>
                  <TableCell>{s.status}</TableCell>
                  <TableCell className="tnum text-right">
                    {s.detected_count ?? 0}/{s.expected_count}
                  </TableCell>
                  <TableCell className="tnum text-right">
                    {s.uncertain}
                  </TableCell>
                  <TableCell className="tnum text-right">
                    {s.auto_resolution_rate === null
                      ? "—"
                      : `${(s.auto_resolution_rate * 100).toFixed(0)}%`}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
