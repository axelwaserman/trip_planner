/**
 * Backend HTTP helpers for Playwright UAT smoke + visual regression suites.
 *
 * The chat surface streams Server-Sent Events; Playwright's APIRequestContext
 * speaks fetch-shaped requests but exposes the raw response body via `body()`,
 * which lets us collect SSE frames as text. The browser-side tests still
 * exercise the real DOM via the running Vite dev server; these helpers exist
 * for the SSE smoke pack where parsing JSON event types is faster, more
 * deterministic, and not coupled to layout markup.
 */

import type { APIRequestContext } from '@playwright/test'

const DEFAULT_BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000'

export interface AuthSession {
  token: string
  username: string
}

export interface ChatSession {
  sessionId: string
  provider: string
  model: string
}

export interface SseFrame {
  type: 'content' | 'thinking' | 'tool_call' | 'tool_result' | 'error'
  payload: Record<string, unknown>
}

const TEST_USER = process.env.TEST_USER ?? 'admin'
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? 'admin'

export async function login(
  request: APIRequestContext,
  username: string = TEST_USER,
  password: string = TEST_PASSWORD,
): Promise<AuthSession> {
  const response = await request.post(`${DEFAULT_BACKEND}/api/auth/token`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    form: { username, password },
  })
  if (!response.ok()) {
    throw new Error(`Login failed: ${response.status()} ${await response.text()}`)
  }
  const body = (await response.json()) as { access_token: string }
  return { token: body.access_token, username }
}

export async function listProviders(
  request: APIRequestContext,
  token: string,
): Promise<Record<string, { available: boolean; models: string[] }>> {
  const response = await request.get(`${DEFAULT_BACKEND}/api/providers`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok()) {
    throw new Error(`/api/providers failed: ${response.status()}`)
  }
  return (await response.json()) as Record<string, { available: boolean; models: string[] }>
}

export async function createSession(
  request: APIRequestContext,
  token: string,
  provider: string,
  model: string,
): Promise<ChatSession> {
  const response = await request.post(`${DEFAULT_BACKEND}/api/chat/session`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: { provider, model },
  })
  if (!response.ok()) {
    throw new Error(`Session create failed: ${response.status()} ${await response.text()}`)
  }
  const body = (await response.json()) as { session_id: string; provider: string; model: string }
  return { sessionId: body.session_id, provider: body.provider, model: body.model }
}

/**
 * Stream a chat turn and parse SSE frames. Returns every event in order
 * along with the raw body for diagnostics.
 */
export async function streamChat(
  request: APIRequestContext,
  token: string,
  sessionId: string,
  message: string,
  timeoutMs = 180_000,
): Promise<{ frames: SseFrame[]; raw: string }> {
  const response = await request.post(`${DEFAULT_BACKEND}/api/chat`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: { session_id: sessionId, message },
    timeout: timeoutMs,
  })
  if (!response.ok()) {
    throw new Error(`Chat stream HTTP failed: ${response.status()} ${await response.text()}`)
  }
  const raw = await response.text()
  const frames = parseSseBody(raw)
  return { frames, raw }
}

function parseSseBody(body: string): SseFrame[] {
  const frames: SseFrame[] = []
  for (const block of body.split('\n\n')) {
    const trimmed = block.trim()
    if (!trimmed.startsWith('data: ')) continue
    const json = trimmed.slice('data: '.length)
    try {
      const payload = JSON.parse(json) as Record<string, unknown>
      const type = payload['type']
      if (typeof type !== 'string') continue
      if (
        type === 'content' ||
        type === 'thinking' ||
        type === 'tool_call' ||
        type === 'tool_result' ||
        type === 'error'
      ) {
        frames.push({ type, payload })
      }
    } catch {
      // Skip malformed frames — they would surface as test diagnostics via
      // `raw` rather than crash the parser.
    }
  }
  return frames
}

export function frameTypes(frames: SseFrame[]): SseFrame['type'][] {
  return frames.map((f) => f.type)
}

export function firstError(frames: SseFrame[]): SseFrame | undefined {
  return frames.find((f) => f.type === 'error')
}

export const config = {
  backend: DEFAULT_BACKEND,
}
