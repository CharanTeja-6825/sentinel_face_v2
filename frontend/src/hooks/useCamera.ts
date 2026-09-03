import { useEffect, useRef, useState } from "react";

/**
 * One webcam implementation, shared by the enrolment wizard and the Live Test.
 *
 * The stream is stopped on unmount. Leaving it running keeps the camera light on
 * after the user navigates away, which reads as the app still watching them.
 */
export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: { width: 1280, height: 720 } })
      .then((s) => {
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          setReady(true);
        }
      })
      .catch(() =>
        setError("Cannot access the webcam. Grant camera permission and reload."),
      );
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  return { videoRef, ready, error };
}

/**
 * Draw the current video frame to `canvas` and return it as a JPEG data URL.
 *
 * DECISIONS.md D5: the preview is CSS-mirrored so the user can position
 * themselves naturally, but this draws the RAW frame. Mirroring here would flip
 * the yaw sign — every "left" capture would be labelled "right", and every
 * turn-your-head instruction would point the wrong way.
 *
 * Returns null when the video has not produced a frame yet.
 */
export function grabFrame(
  video: HTMLVideoElement | null,
  canvas: HTMLCanvasElement | null,
): string | null {
  if (!video || !canvas || video.readyState < 2) return null;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d")!.drawImage(video, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.92);
}
