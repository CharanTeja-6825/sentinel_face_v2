import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import RegistrationWizard from "@/components/RegistrationWizard";
import { api, errorMessage, type EnrolSession } from "@/lib/api";

const CONSENT_TEXT =
  "I consent to SentinelFace capturing images of my face and storing mathematical " +
  "face embeddings derived from them, for the sole purpose of recording my " +
  "attendance. The captured images are discarded once enrolment completes; only " +
  "the embeddings are retained, and they are deleted when I leave the course or " +
  "on request.";

export default function RegisterPage() {
  const [rollNo, setRollNo] = useState("");
  const [consent, setConsent] = useState(false);
  const [session, setSession] = useState<EnrolSession | null>(null);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    try {
      const { data } = await api.post<EnrolSession>("/enrolment/sessions", {
        roll_no: rollNo.trim(),
        consent,
      });
      setSession(data);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (done !== null) {
    return (
      <div className="mx-auto max-w-xl">
        <Card className="border-success/25 shadow-card">
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success/10">
              <CheckCircle2 className="h-6 w-6 text-success" />
            </div>
            <h2 className="text-xl">Enrolment complete</h2>
            <p className="tnum text-sm text-muted-foreground">
              {done} face templates stored. You can close this page.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (session) {
    return (
      <RegistrationWizard
        session={session}
        onDone={(n) => {
          setDone(n);
          setSession(null);
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-3xl">Face enrolment</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A guided capture, one head angle at a time. It takes about a minute and builds
          the templates every future attendance check is matched against.
        </p>
      </div>

      <Card className="shadow-card">
      <CardHeader>
        <CardTitle className="text-base">Before you start</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="roll">Roll number</Label>
          <Input
            id="roll"
            value={rollNo}
            onChange={(e) => setRollNo(e.target.value)}
            placeholder="e.g. 22BCE1234"
          />
        </div>

        <div className="flex items-start gap-3 rounded-md border bg-muted/40 p-4">
          <Checkbox
            id="consent"
            checked={consent}
            onCheckedChange={(v) => setConsent(v === true)}
            className="mt-1"
          />
          <Label htmlFor="consent" className="text-sm font-normal leading-relaxed">
            {CONSENT_TEXT}
          </Label>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Button
          className="w-full bg-accent text-accent-foreground hover:bg-accent/90"
          size="lg"
          disabled={!rollNo.trim() || !consent}
          onClick={start}
        >
          Start enrolment
        </Button>
      </CardContent>
      </Card>
    </div>
  );
}
