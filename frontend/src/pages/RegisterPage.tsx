import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import PageHeader from "@/components/PageHeader";
import ErrorAlert from "@/components/ErrorAlert";
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
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-10">
            <p className="stamp flex items-center gap-2 font-medium text-instruct">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Enrolment complete
            </p>
            <h2 className="text-2xl font-semibold">{done} face templates stored</h2>
            <p className="text-sm text-muted-foreground">
              The captured images have been discarded — only the embeddings are kept.
              You can close this page, or check the result on the live test.
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
      <PageHeader stamp="Student · once" title="Face enrolment">
        A guided capture, one head angle at a time. It takes about a minute and builds
        the templates every future attendance check is matched against. The captured
        images are discarded when it completes.
      </PageHeader>

      <Card>
      <CardHeader>
        <CardTitle>Before you start</CardTitle>
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

        <div className="flex items-start gap-3 rounded-sm border border-border p-4">
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

        <ErrorAlert message={error} />

        <Button
          variant="instruct"
              className="w-full"
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
