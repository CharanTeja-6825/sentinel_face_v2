import { cn } from "@/lib/utils";

/**
 * A figure and what it measures. Numbers take the measure colour and tabular
 * figures so a readout does not reflow as its digits change.
 */
export default function Stat({
  label,
  value,
  tone = "measure",
  hint,
}: {
  label: string;
  value: string | number;
  tone?: "measure" | "accepted" | "refuse" | "instruct";
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="stamp font-medium text-muted-foreground">{label}</p>
      <p
        className={cn(
          "tnum mt-1.5 text-xl font-semibold",
          tone === "measure" && "text-measure",
          tone === "accepted" && "text-foreground",
          tone === "refuse" && "text-refuse",
          tone === "instruct" && "text-instruct",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
