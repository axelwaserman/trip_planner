/**
 * chatSessionStore — module-level subscribable store keyed by session_id.
 *
 * Why this exists: useChat used to keep `messages`/`isStreaming` as local
 * React state, so a switch from conv A → conv B mid-stream wiped A's
 * accumulator and dropped any chunks A was still receiving. The Sidebar
 * also had no way to surface "this row is currently generating" because
 * the streaming flag lived inside ChatInterface.
 *
 * The store solves both:
 *   - Per-session message lists + flags survive across `useChat` resets,
 *     so the user can switch chats and come back to a still-running
 *     conversation with full progress visible.
 *   - The Sidebar subscribes to `getStreamingSessionIds()` so streaming
 *     rows can show a live indicator.
 *
 * The store is intentionally simple: a `Map<sessionId, SessionState>`
 * snapshot, a `Set` of listeners, and a "version" tick that bumps on
 * every write so React's `useSyncExternalStore` can detect changes
 * without deep-comparing snapshots.
 */

import type { Message } from '../types/chat'

export interface SessionState {
  messages: Message[]
  isAwaitingFirstChunk: boolean
  isStreaming: boolean
  /** True when the session finished streaming while the user was looking at a different chat. */
  hasUnread: boolean
  /** True when the stream ended with an error while the user was away. */
  hasError: boolean
}

const EMPTY_STATE: SessionState = Object.freeze({
  messages: [],
  isAwaitingFirstChunk: false,
  isStreaming: false,
  hasUnread: false,
  hasError: false,
}) as SessionState

const sessions = new Map<string, SessionState>()
const listeners = new Set<() => void>()

// Cached Set snapshots — useSyncExternalStore requires identity-stable
// references between notifications, otherwise every getSnapshot call returns
// a new object and React enters an infinite re-render loop.
let streamingIdsSnapshot: ReadonlySet<string> = new Set()
let unreadIdsSnapshot: ReadonlySet<string> = new Set()
let errorIdsSnapshot: ReadonlySet<string> = new Set()
let idsDirty = true

function rebuildIdsIfNeeded() {
  if (!idsDirty) return
  const streaming = new Set<string>()
  const unread = new Set<string>()
  const error = new Set<string>()
  for (const [id, state] of sessions.entries()) {
    if (state.isStreaming) streaming.add(id)
    if (state.hasUnread) unread.add(id)
    if (state.hasError) error.add(id)
  }
  streamingIdsSnapshot = streaming
  unreadIdsSnapshot = unread
  errorIdsSnapshot = error
  idsDirty = false
}

function notify() {
  idsDirty = true
  for (const listener of listeners) {
    listener()
  }
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getSnapshot(sessionId: string | null): SessionState {
  if (!sessionId) return EMPTY_STATE
  const existing = sessions.get(sessionId)
  return existing ?? EMPTY_STATE
}

export function setSession(
  sessionId: string,
  updater: (prev: SessionState) => SessionState
): void {
  const prev = sessions.get(sessionId) ?? EMPTY_STATE
  const next = updater(prev)
  sessions.set(sessionId, next)
  notify()
}

export function clearSession(sessionId: string): void {
  if (sessions.delete(sessionId)) {
    notify()
  }
}

export function getStreamingSessionIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return streamingIdsSnapshot
}

export function getUnreadSessionIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return unreadIdsSnapshot
}

export function getErrorSessionIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return errorIdsSnapshot
}

// Test-only: drop everything. Lets vitest specs reset between cases.
export function __resetForTests(): void {
  sessions.clear()
  listeners.clear()
  streamingIdsSnapshot = new Set()
  unreadIdsSnapshot = new Set()
  errorIdsSnapshot = new Set()
  idsDirty = false
}
