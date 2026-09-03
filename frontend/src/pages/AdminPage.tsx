import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import PageHeader from "@/components/PageHeader";
import ErrorAlert from "@/components/ErrorAlert";
import SessionList from "@/components/SessionList";
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
      <PageHeader stamp="Administrator" title="Roster and coverage">
        The roster is the gallery. A student missing from a section roster cannot be
        recognised no matter how well they enrolled, and a roster student who never
        enrolled is marked absent every time.
      </PageHeader>

      <ErrorAlert message={error} />
      {note && (
        <Alert variant="instruct">
          <AlertDescription data-slot="body">{note}</AlertDescription>
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
      <Card>
        <CardHeader>
          <CardTitle>Setup</CardTitle>
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
              variant="instruct"
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
      <Card>
        <CardHeader>
          <CardTitle>Section coverage</CardTitle>
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
                className="h-1.5"
              />
              <p className="tnum text-sm">
                <span className="text-2xl font-semibold text-measure">
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
      <Card>
        <CardHeader>
          <CardTitle>Students</CardTitle>
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
                    <Badge variant={s.enrolled ? "instruct" : "secondary"}>
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
          <Card>
            <CardHeader>
              <CardTitle>Session history</CardTitle>
            </CardHeader>
            <CardContent>
              <SessionList sessions={history} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
