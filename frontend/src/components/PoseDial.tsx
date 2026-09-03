import { cn } from "@/lib/utils";
import type { Pose } from "@/lib/api";

/**
 * Yaw against pitch on a small pad, with the accepting zone shaded.
 *
 * This exists because the backend now measures pose in real degrees (D12) and the
 * student previously had no way to see how far they had turned — only a pass/fail
 * after the fact. A dial stays legible at the 700 ms probe rate in a way a landmark
 * overlay does not: it is a slow-moving indicator, not a tracker.
 *
 * `inZone` is passed in, derived from the backend's own `detected_angle`, rather than
 * recomputed here. The bucket boundaries live in thresholds.yaml and the backend is the
 * only authority on which angle a frame counts as; duplicating that decision in the
 * client is how the prompt and the acceptance drift apart. The degree constants below
 * scale the PAD only — they are presentational, and being slightly stale would move a
 * dot a few pixels, not change what gets banked.
 */
const YAW_SPAN_DEG = 45;
const PITCH_SPAN_DEG = 35;
const YAW_BAND_DEG = 15;
const PITCH_BAND_DEG = 12;

export default function PoseDial({
  pose,
  target,
  inZone,
}: {
  pose: Pose | null;
  target: string | null;
  inZone: boolean;
}) {
  // Clamped so an extreme pose pins at the edge instead of leaving the pad.
  const clamp = (v: number, max: number) => Math.max(-1, Math.min(1, v / max));
  // Negated: the preview is CSS-mirrored, so turning your head left must move the dot
  // left on your own screen.
  const x = pose ? -clamp(pose.yaw, YAW_SPAN_DEG) : 0;
  const y = pose ? clamp(pose.pitch, PITCH_SPAN_DEG) : 0;

  const yawBand = (YAW_BAND_DEG / YAW_SPAN_DEG) * 50;
  const pitchBand = (PITCH_BAND_DEG / PITCH_SPAN_DEG) * 50;
  const zones: Record<string, React.CSSProperties> = {
    front: {
      left: `${50 - yawBand}%`, right: `${50 - yawBand}%`,
      top: `${50 - pitchBand}%`, bottom: `${50 - pitchBand}%`,
    },
    // "left" is the subject's left, which is screen-left in a mirrored preview.
    left: { left: 0, right: `${50 + yawBand}%`, top: 0, bottom: 0 },
    right: { left: `${50 + yawBand}%`, right: 0, top: 0, bottom: 0 },
    up: { left: 0, right: 0, top: 0, bottom: `${50 + pitchBand}%` },
    down: { left: 0, right: 0, top: `${50 + pitchBand}%`, bottom: 0 },
  };

  const fmt = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}°`;

  return (
    <div className="space-y-2">
      <div className="relative aspect-square w-full overflow-hidden rounded-sm border border-border">
        {target && zones[target] && (
          <div
            className="absolute rounded-sm ring-1 ring-inset ring-instruct/40"
            style={zones[target]}
          />
        )}
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <div
          className={cn(
            "absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-background",
            "transition-all duration-300 ease-out",
            !pose ? "bg-muted-foreground/40" : inZone ? "bg-measure" : "bg-instruct",
          )}
          style={{ left: `${50 + x * 50}%`, top: `${50 + y * 50}%` }}
        />
      </div>
      <p className="tnum text-center text-xs text-muted-foreground">
        {pose
          ? `yaw ${fmt(pose.yaw)} · pitch ${fmt(pose.pitch)} · roll ${fmt(pose.roll)}`
          : "waiting for a face…"}
      </p>
    </div>
  );
}
