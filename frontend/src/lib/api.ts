import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "http://localhost:8000",
});

/** FastAPI puts the message in `detail`; anything else is a network failure. */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data as { detail?: unknown } | undefined;
    if (typeof d?.detail === "string") return d.detail;
    if (e.response) return `${e.response.status} ${e.response.statusText}`;
    return "Cannot reach the server.";
  }
  return String(e);
}

// ── enrolment ──────────────────────────────────────────────────────────
export type EnrolSession = {
  session_id: string;
  student_id: string;
  required_angles: string[];
  min_samples: number;
  min_samples_per_angle: number;
  /** The angle to prompt for first; the backend owns the stage. */
  target_angle: string | null;
  expires_at: string;
};

/** Real 3D head pose in DEGREES, from MediaPipe (backend D12).
 *  Positive yaw = the subject turned to their OWN left; positive pitch = looking down.
 *  Labels are in the subject's frame, which is what "turn your head left" means. */
export type Pose = { yaw: number; pitch: number; roll: number };

/** Curated landmark rings, normalised [0,1] against the UNMIRRORED frame that was
 *  POSTed. The preview is CSS-mirrored, so the overlay must be mirrored with it. */
export type Landmarks = {
  oval: [number, number][];
  left_eye: [number, number][];
  right_eye: [number, number][];
  lips: [number, number][];
};

export type FrameResult = {
  accepted: boolean;
  reason: string | null;
  detected_angle: string | null;
  quality_score: number;
  captured_count: number;
  angle_progress: Record<string, number>;
  can_complete: boolean;
  /** The angle to prompt for next; null once every requirement is met. */
  target_angle: string | null;
  min_samples_per_angle: number;
  /** Null whenever the frame never reached the stage that produces them. */
  pose: Pose | null;
  landmarks: Landmarks | null;
  eyes_open: boolean | null;
};

// ── timetable ──────────────────────────────────────────────────────────
export type Block = {
  id: string;
  section: string;
  day_of_week: string;
  start_period: number;
  end_period: number;
  course_code: string;
  component: string;
  group_code: string;
  room: string;
  eligible: boolean;
  ineligible_reason: string | null;
  time_window: { start: string; end: string } | null;
};

// ── sessions ───────────────────────────────────────────────────────────
export type StudentBrief = { student_id: string; roll_no: string; name: string };

export type SessionStatus = {
  session_id: string;
  status: string;
  session_date: string;
  start_period: number;
  expected_count: number | null;
  detected_count: number | null;
  frames_sampled: number | null;
  expected_frames: number | null;
  progress: number | null;
  video_duration_s: number | null;
  processing_ms: number | null;
  error_message: string | null;
  model_version: string | null;
  finalized_at: string | null;
};

export type ResultRow = {
  cluster_id: number;
  student: StudentBrief | null;
  score: number | null;
  margin: number | null;
  crop_url: string | null;
  first_seen_s: number | null;
  runner_up?: StudentBrief | null;
  runner_up_score?: number | null;
};

export type Unmatched = {
  id: string;
  cluster_id: number;
  crop_url: string | null;
  best_score: number | null;
  resolution: string;
};

export type Results = {
  session_id: string;
  status: string;
  confident: ResultRow[];
  uncertain: ResultRow[];
  absent: (StudentBrief & { source: string | null })[];
  unmatched: Unmatched[];
  stats: {
    detected_count: number | null;
    expected_count: number | null;
    present_count: number;
    frames_sampled: number | null;
    processing_ms: number | null;
    auto_resolution_rate: number | null;
    model_version: string | null;
  };
};

// ── admin ──────────────────────────────────────────────────────────────
export type Student = {
  id: string;
  roll_no: string;
  name: string;
  email: string | null;
  consent_given: boolean;
  template_count: number;
  enrolled: boolean;
};

export type Coverage = {
  section: string;
  roster_size: number;
  enrolled: number;
  enrolled_pct: number;
  missing: { roll_no: string; name: string }[];
};

export type SessionHistory = {
  session_id: string;
  session_date: string;
  start_period: number;
  status: string;
  expected_count: number;
  detected_count: number | null;
  clusters: number;
  uncertain: number;
  processing_ms: number | null;
  auto_resolution_rate: number | null;
  auto_present: number;
};
