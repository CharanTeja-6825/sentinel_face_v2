import { useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, errorMessage } from "@/lib/api";

/**
 * Client-side courtesy check only — video.max_upload_mb in thresholds.yaml is
 * the authority and the backend rejects oversized files regardless.
 */
const MAX_UPLOAD_MB = 2048;

export default function VideoUpload({
  sessionId,
  onQueued,
}: {
  sessionId: string;
  onQueued: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tooBig = file ? file.size > MAX_UPLOAD_MB * 1024 * 1024 : false;

  async function upload() {
    if (!file) return;
    setError(null);
    setPct(0);
    const body = new FormData();
    body.append("file", file);
    try {
      await api.post(`/sessions/${sessionId}/video`, body, {
        onUploadProgress: (e) =>
          setPct(e.total ? Math.round((100 * e.loaded) / e.total) : null),
      });
      onQueued();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPct(null);
    }
  }

  return (
    <div className="space-y-3">
      <Input
        type="file"
        accept="video/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      {file && (
        <p className="tnum text-sm text-muted-foreground">
          {file.name} — {(file.size / 1024 / 1024).toFixed(1)} MB
        </p>
      )}
      {tooBig && (
        <Alert variant="destructive">
          <AlertDescription data-slot="body">
            Larger than the {MAX_UPLOAD_MB} MB limit.
          </AlertDescription>
        </Alert>
      )}
      {pct !== null && <Progress value={pct} className="h-2" />}
      {error && (
        <Alert variant="destructive">
          <AlertDescription data-slot="body">{error}</AlertDescription>
        </Alert>
      )}
      <Button
        variant="instruct"
        disabled={!file || tooBig || pct !== null}
        onClick={upload}
      >
        <Upload className="mr-2 h-4 w-4" />
        Upload and queue
      </Button>
    </div>
  );
}
