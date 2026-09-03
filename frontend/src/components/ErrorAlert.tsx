import { Alert, AlertDescription } from "@/components/ui/alert";

/**
 * The `useState<string | null>` + destructive Alert pair was copy-pasted in five
 * files. Renders nothing when there is no message, so call sites do not need the
 * conditional either.
 */
export default function ErrorAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Alert variant="refuse">
      <AlertDescription data-slot="body">{message}</AlertDescription>
    </Alert>
  );
}
