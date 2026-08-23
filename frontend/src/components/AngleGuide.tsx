import { Check } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/**
 * The five prompts, in the SUBJECT's frame of reference.
 *
 * "your left" is load-bearing, not a turn of phrase: DECISIONS.md D5 fixes positive yaw
 * as the subject turning to their own left, and the backend labels angles the same way.
 * Rewording these to the camera's point of view would invert the whole wizard.
 */
const PROMPTS: Record<string, string> = {
  front: "Look straight ahead",
  left: "Turn your head to your left",
  right: "Turn your head to your right",
  up: "Tilt your chin up",
  down: "Tilt your chin down",
};

const HINTS: Record<string, string> = {
  front: "Eyes on the lens, shoulders square.",
  left: "About a quarter turn. Both eyes still visible.",
  right: "About a quarter turn. Both eyes still visible.",
  up: "A small lift only — do not show the underside of your chin.",
  down: "A small drop only — keep your eyes on the lens.",
};

export function anglePrompt(angle: string) {
  return PROMPTS[angle] ?? `Show the ${angle} angle`;
}

export default function AngleGuide({
  angles,
  progress,
  perAngle,
  current,
}: {
  angles: string[];
  progress: Record<string, number>;
  perAngle: number;
  current: string | null;
}) {
  const step = current ? angles.indexOf(current) + 1 : angles.length;
  const done = current === null;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {done ? "Complete" : `Step ${step} of ${angles.length}`}
        </p>
        <h2 className="mt-1.5 text-2xl leading-tight">
          {done ? "All angles captured" : anglePrompt(current!)}
        </h2>
        {!done && (
          <p className="mt-1.5 text-sm text-muted-foreground">{HINTS[current!]}</p>
        )}
      </div>

      <ul className="space-y-2.5">
        {angles.map((angle) => {
          const n = progress[angle] ?? 0;
          const complete = n >= perAngle;
          const active = angle === current;
          return (
            <li
              key={angle}
              className={cn(
                "rounded-md border px-3 py-2 transition-colors",
                active
                  ? "border-accent/40 bg-accent-light"
                  : complete
                    ? "border-transparent bg-muted/50"
                    : "border-transparent",
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "text-sm capitalize",
                    active
                      ? "font-semibold text-card-foreground"
                      : complete
                        ? "text-muted-foreground"
                        : "text-muted-foreground",
                  )}
                >
                  {angle}
                </span>
                {complete && <Check className="h-3.5 w-3.5 text-success" />}
                <span
                  className={cn(
                    "tnum ml-auto text-xs",
                    complete ? "text-success" : "text-muted-foreground",
                  )}
                >
                  {n}/{perAngle}
                </span>
              </div>
              <Progress
                value={Math.min(100, (n / perAngle) * 100)}
                className={cn(
                  "mt-2 h-1",
                  complete
                    ? "[&>*]:bg-success"
                    : active
                      ? "[&>*]:bg-accent"
                      : "[&>*]:bg-muted-foreground/30",
                )}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
