/**
 * Minimal LERNA-backend client for the Voice AI service (Node 18+ / fetch).
 *
 * Copy into your backend. Two server-side calls: create a session, mint a token.
 * The service key never reaches the browser.
 *
 * Env:
 *   VOICE_SERVICE_URL        e.g. https://voice.your-domain  (no trailing slash)
 *   VOICE_SERVICE_API_KEY    the shared secret (X-Voice-Service-Key)
 */

const BASE = (process.env.VOICE_SERVICE_URL ?? "").replace(/\/$/, "");
const KEY = process.env.VOICE_SERVICE_API_KEY ?? "";
const HEADERS = { "X-Voice-Service-Key": KEY, "Content-Type": "application/json" };

export interface StartLessonOpts {
  language?: string;          // default "ar"
  topicId?: string;           // catalogue id (preferred)
  topic?: string;             // or free text
  level?: string;             // beginner | intermediate | advanced
  documentIds?: string[];     // from POST /voice/material
  resumeLatest?: boolean;     // recap instead of restart
}

export interface StartLessonResult {
  sessionId: string;
  wsUrl: string;              // browser opens this directly
  language?: string;
  currentTopic?: string;
}

export async function startLesson(
  studentId: string,
  opts: StartLessonOpts = {},
): Promise<StartLessonResult> {
  const body: Record<string, unknown> = {
    student_id: studentId,
    language: opts.language ?? "ar",
  };
  if (opts.topicId) body.topic_id = opts.topicId;
  if (opts.topic) body.topic = opts.topic;
  if (opts.level) body.level = opts.level;
  if (opts.documentIds) body.document_ids = opts.documentIds;
  if (opts.resumeLatest) body.resume_latest = true;

  const created = await fetch(`${BASE}/voice/session`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify(body),
  });
  if (!created.ok) throw new Error(`create session failed: ${created.status}`);
  const session = await created.json();

  const tokRes = await fetch(`${BASE}/voice/session/${session.session_id}/token`, {
    method: "POST",
    headers: HEADERS,
  });
  if (!tokRes.ok) throw new Error(`mint token failed: ${tokRes.status}`);
  const { token } = (await tokRes.json()) as { token: string };

  return {
    sessionId: session.session_id,
    wsUrl: `${session.websocket_url}?token=${token}`,
    language: session.language,
    currentTopic: session.current_topic,
  };
}

/** For continuation: the student's most recent session, if any. */
export async function latestSession(studentId: string): Promise<unknown | null> {
  const r = await fetch(`${BASE}/voice/students/${studentId}/latest`, { headers: HEADERS });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`latest session failed: ${r.status}`);
  return r.json();
}
