import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Unmatched } from "@/lib/api";

/** The `resolution` values accepted by PATCH /sessions/{id}/unmatched. */
const RESOLUTIONS = [
  { value: "outsider", label: "Outsider" },
  { value: "unenrolled", label: "Not enrolled" },
  { value: "not_a_person", label: "Not a person" },
];

export default function EvidenceGrid({
  faces,
  disabled,
  onResolve,
}: {
  faces: Unmatched[];
  disabled: boolean;
  onResolve: (clusterId: number, resolution: string) => void;
}) {
  if (faces.length === 0) {
    return <p className="text-sm text-muted-foreground">No unmatched faces.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {faces.map((f) => (
        <div key={f.id} className="space-y-2 rounded-lg border bg-card p-2 shadow-card">
          {f.crop_url ? (
            <img
              src={f.crop_url}
              alt={`cluster ${f.cluster_id}`}
              className="aspect-square w-full rounded-md object-cover"
            />
          ) : (
            <div className="flex aspect-square items-center justify-center rounded-md bg-muted text-xs text-muted-foreground">
              no crop
            </div>
          )}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>#{f.cluster_id}</span>
            <span className="tnum">
              best {f.best_score?.toFixed(2) ?? "—"}
            </span>
          </div>
          {f.resolution !== "unresolved" ? (
            <Badge className="w-full justify-center bg-muted text-muted-foreground hover:bg-muted">
              {f.resolution}
            </Badge>
          ) : (
            <div className="flex flex-col gap-1">
              {RESOLUTIONS.map((r) => (
                <Button
                  key={r.value}
                  size="sm"
                  variant="outline"
                  disabled={disabled}
                  onClick={() => onResolve(f.cluster_id, r.value)}
                >
                  {r.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
