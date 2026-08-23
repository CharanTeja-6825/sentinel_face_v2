import { useEffect, useRef } from "react";
import type { Landmarks } from "@/lib/api";

/**
 * Draws MediaPipe's landmark rings over the webcam preview.
 *
 * ponytail: this repaints at the backend probe rate (~1.4 Hz), not at video frame rate,
 * because the landmarks arrive with each /frames response. It reads as a confirmation
 * indicator — "the system has found your face and these are the features it is
 * measuring" — rather than a smooth AR overlay, and the CSS transition below smooths
 * the steps. Upgrade path if that is not enough: run @mediapipe/tasks-vision in the
 * browser for a 30 fps overlay, at the cost of a second model download and a
 * non-shadcn dependency.
 *
 * The canvas is mirrored by the PARENT (the same -scale-x-100 as the video), because
 * these coordinates describe the unmirrored frame that was POSTed. Mirroring here
 * instead would put the overlay on the wrong side of the student's face.
 */
export default function FaceOverlay({
  landmarks,
  tone,
}: {
  landmarks: Landmarks | null;
  tone: "idle" | "onTarget" | "accepted" | "rejected";
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);
    if (!landmarks) return;

    const stroke = {
      idle: "rgba(255,255,255,0.55)",
      onTarget: "rgba(37,99,235,0.95)",   // accent  #2563EB
      accepted: "rgba(22,163,74,0.95)",   // success #16A34A
      rejected: "rgba(217,119,6,0.95)",   // warning #D97706
    }[tone];

    const ring = (pts: [number, number][], lineWidth: number) => {
      if (pts.length < 2) return;
      ctx.beginPath();
      pts.forEach(([x, y], i) => {
        const px = x * width;
        const py = y * height;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      ctx.lineWidth = lineWidth;
      ctx.strokeStyle = stroke;
      ctx.stroke();
    };

    ctx.lineJoin = "round";
    ring(landmarks.oval, 2.5);
    ring(landmarks.left_eye, 1.5);
    ring(landmarks.right_eye, 1.5);
    ring(landmarks.lips, 1.5);
  }, [landmarks, tone]);

  return (
    <canvas
      ref={ref}
      width={640}
      height={360}
      className="pointer-events-none absolute inset-0 h-full w-full transition-opacity duration-200"
      style={{ opacity: landmarks ? 1 : 0 }}
    />
  );
}
