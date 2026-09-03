import { Badge } from "@/components/ui/badge";

/**
 * The three verdicts, coloured by message class rather than by convention — see
 * design/ROUND-2-CONTEXT.md. `confident` is settled and takes primary ink;
 * `uncertain` is measured but unresolved and takes measure; `no match` is a refusal
 * to name and takes refuse.
 */
const LABEL: Record<string, string> = {
  confident: "confident",
  uncertain: "uncertain",
  no_match: "no match",
};

export default function BandLabel({ band }: { band: string | null }) {
  if (!band) return null;
  const variant =
    band === "confident" ? "confident" : band === "uncertain" ? "uncertain" : "no_match";
  return <Badge variant={variant}>{LABEL[band] ?? band}</Badge>;
}
