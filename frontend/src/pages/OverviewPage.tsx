import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

/**
 * The overview is direction C's own composition, used for the job it was drawn for:
 * a dense machine log on the left against open human statements on the right. The
 * log is not decoration — every line in it is a real string this system produces.
 */

/** Real reason codes and prompts from the enrolment and quality gates. */
const LOG: { text: string; kind: "refuse" | "instruct" | "measure" }[] = [
  { text: "Move a little closer", kind: "refuse" },
  { text: "Hold still — try better lighting", kind: "refuse" },
  { text: "You are facing front — turn your head to your left", kind: "instruct" },
  { text: "Move a little closer", kind: "refuse" },
  { text: "Captured front · quality 0.83", kind: "measure" },
  { text: "Turned too far — ease back towards the camera", kind: "refuse" },
  { text: "You are facing front — turn your head to your right", kind: "instruct" },
  { text: "Captured right · quality 0.79", kind: "measure" },
  { text: "Move slightly, that looks the same as the last one", kind: "refuse" },
  { text: "15 templates stored · 5 angles", kind: "measure" },
  { text: "gallery=58 enrolled=58 roster=62", kind: "measure" },
  { text: "22BCE1234 · 0.62 ≥ 0.60 · margin 0.14", kind: "measure" },
];

const KIND_CLASS = {
  refuse: "text-refuse",
  instruct: "text-instruct",
  measure: "font-semibold text-measure",
} as const;

const CLAIMS = [
  {
    title: "Sixty candidates, not twenty thousand.",
    body: "A face is compared only against the roster of the timetable block the footage belongs to. Error rate is dominated by gallery size, so this scoping is what makes the accuracy usable at all.",
  },
  {
    title: "No single frame is enough. The mean of thirty is.",
    body: "Detections are linked into tracks across time and averaged into one embedding. A student does not have to be recognisable in any particular frame, only occasionally.",
  },
  {
    title: "One face can claim at most one student.",
    body: "Faces and roster students are matched as a single global assignment, not independent best-match. That constraint — not the face model — is what closes the proxy-attendance loophole.",
    tone: "instruct" as const,
  },
  {
    title: "An uncertain match is marked absent, never present.",
    body: "A false absent is corrected in seconds by a student sitting in the room. A false present is invisible, and is exactly the fraud this system exists to stop.",
    tone: "refuse" as const,
  },
];

const ROLES = [
  {
    role: "Student",
    note: "enrols once",
    heading: "Attendance without a roll call",
    body: "About a minute of guided capture, once per course. Consent is a hard precondition, and the captured images are discarded at completion — only the embeddings are kept, and no photograph can be reconstructed from them.",
    to: "/register",
    cta: "Enrol",
  },
  {
    role: "Faculty",
    note: "reviews, does not label",
    heading: "An upload and a short review",
    body: "Pick the timetable block, upload the footage, and review only what the system was unsure about. Every automatic decision carries the image crop it was made from, so a wrong one is visible rather than merely wrong.",
    to: "/sessions",
    cta: "Take attendance",
  },
  {
    role: "Administrator",
    note: "owns the roster",
    heading: "The roster is the gallery",
    body: "A student missing from the section roster cannot be recognised no matter how well they enrolled. Coverage reports who is still missing, so that gap is visible before it becomes a wrong attendance record.",
    to: "/admin",
    cta: "Manage rosters",
  },
];

export default function OverviewPage() {
  return (
    <div className="space-y-20">
      {/* ── the dense/open pair ── */}
      <section className="grid items-start gap-x-12 gap-y-10 lg:grid-cols-[minmax(16rem,26fr)_minmax(0,44fr)]">
        <div>
          <p className="stamp mb-5 font-medium text-instruct">front left right up down</p>
          <div className="log">
            {LOG.map((line, i) => (
              <p key={i} className={KIND_CLASS[line.kind]}>
                {line.text}
              </p>
            ))}
          </div>
        </div>

        <div>
          <h1 className="max-w-[13ch] text-4xl font-semibold">SentinelFace</h1>
          <p className="mt-5 max-w-[24ch] font-display text-2xl font-normal text-foreground">
            Attendance from the room, not from a roll call
          </p>
          <p className="mt-6 max-w-[52ch] text-sm text-muted-foreground">
            Classroom attendance is recorded from uploaded video, matched against the
            roster of the timetable block the footage belongs to. This is a prototype
            demonstrating a pipeline — not an authentication system, and not a
            liveness check.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild variant="instruct" size="lg">
              <Link to="/live">Try the live test</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/register">Enrol a face</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* ── what it claims ── */}
      <section>
        <h2 className="stamp mb-8 font-medium text-muted-foreground">What it claims</h2>
        <div className="grid gap-x-12 gap-y-9 md:grid-cols-2">
          {CLAIMS.map((c) => (
            <div key={c.title}>
              <h3
                className={
                  c.tone === "refuse"
                    ? "max-w-[26ch] text-lg font-medium text-refuse"
                    : c.tone === "instruct"
                      ? "max-w-[26ch] text-lg font-medium text-instruct"
                      : "max-w-[26ch] text-lg font-medium"
                }
              >
                {c.title}
              </h3>
              <p className="mt-2.5 max-w-[46ch] text-sm text-muted-foreground">{c.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── who it is for ── */}
      <section>
        <h2 className="stamp mb-8 font-medium text-muted-foreground">Who it is for</h2>
        <div className="space-y-10">
          {ROLES.map((r) => (
            <div
              key={r.role}
              className="grid gap-x-8 gap-y-3 border-t border-border pt-6 md:grid-cols-[11rem_minmax(0,1fr)_auto]"
            >
              <div>
                <p className="stamp font-medium text-instruct">{r.role}</p>
                <p className="stamp mt-1.5 text-muted-foreground">{r.note}</p>
              </div>
              <div className="min-w-0">
                <h3 className="text-lg font-medium">{r.heading}</h3>
                <p className="mt-2 max-w-[54ch] text-sm text-muted-foreground">{r.body}</p>
              </div>
              <div className="self-start">
                <Button asChild variant="outline" size="sm">
                  <Link to={r.to}>{r.cta}</Link>
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── the limits, stated rather than hidden ── */}
      <section className="border-t border-border pt-8">
        <h2 className="stamp mb-5 font-medium text-muted-foreground">
          What this prototype does not do
        </h2>
        <div className="log max-w-[60ch] text-refuse">
          <p>No authentication — every screen is open to anyone who can reach the host</p>
          <p>No liveness — a printed photograph will enrol, and will be counted present</p>
          <p>No real-time attendance — the live test is a diagnostic, not a register</p>
          <p>Accuracy unmeasured — every threshold is a starting value, not a calibrated one</p>
          <p>Fairness unmeasured — the human-review band is the only mitigation present</p>
        </div>
      </section>
    </div>
  );
}
