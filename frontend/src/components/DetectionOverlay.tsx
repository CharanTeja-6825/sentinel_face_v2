import { useEffect, useRef } from "react";
import type { IdentifiedFace } from "@/lib/api";

const BAND_COLOR: Record<string, string> = {
  confident: "--success",
  uncertain: "--warning",
  no_match: "--muted-foreground",
};

function token(name: string, alpha = 1): string {
  // Read the palette rather than hard-coding it. FaceOverlay keeps a hand-synced
  // rgba() copy of these same three colours; this is the version that cannot
  // drift when the tokens change.
  const hsl = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return hsl ? `hsl(${hsl} / ${alpha})` : `rgba(255,255,255,${alpha})`;
}

/**
 * Boxes and name labels over the webcam preview.
 *
 * Unlike FaceOverlay — which is mirrored by its PARENT along with the video —
 * this canvas is NOT mirrored, and flips x itself. Labels inherit the parent's
 * transform, so a mirrored canvas would render every name backwards. The boxes
 * arrive in unmirrored frame coordinates (the frame that was POSTed), so the
 * flip is `x' = frameWidth - x`.
 */
export default function DetectionOverlay({
  faces,
  frameWidth,
  frameHeight,
}: {
  faces: IdentifiedFace[];
  frameWidth: number;
  frameHeight: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !frameWidth || !frameHeight) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = frameWidth;
    canvas.height = frameHeight;
    ctx.clearRect(0, 0, frameWidth, frameHeight);

    for (const face of faces) {
      const [x1, y1, x2, y2] = face.bbox;
      // Mirror to match the preview the user is looking at.
      const left = frameWidth - x2;
      const width = x2 - x1;
      const height = y2 - y1;
      const stroke = face.accepted
        ? token(BAND_COLOR[face.band ?? "no_match"] ?? "--muted-foreground", 0.95)
        : token("--warning", 0.75);

      ctx.lineWidth = 3;
      ctx.strokeStyle = stroke;
      ctx.strokeRect(left, y1, width, height);

      const label = face.accepted
        ? face.roll_no
          ? `${face.roll_no} · ${face.score?.toFixed(2)}`
          : `unrecognised · ${face.score?.toFixed(2) ?? "—"}`
        : "gated";

      ctx.font = "600 20px \"Azeret Mono\", ui-monospace, monospace";
      const pad = 8;
      const textWidth = ctx.measureText(label).width;
      // The label sits above the box, or inside it when the face is near the top edge.
      const boxTop = y1 > 34 ? y1 - 32 : y1 + 4;
      ctx.fillStyle = stroke;
      ctx.fillRect(left, boxTop, textWidth + pad * 2, 28);
      ctx.fillStyle = token("--card", 1);
      ctx.fillText(label, left + pad, boxTop + 20);
    }
  }, [faces, frameWidth, frameHeight]);

  return (
    <canvas
      ref={ref}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
