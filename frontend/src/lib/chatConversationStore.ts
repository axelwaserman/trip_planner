/**
 * chatConversationStore — module-level subscribable store keyed by conversation_id.
 *
 * Why this exists: useChat used to keep `messages`/`isStreaming` as local
 * React state, so a switch from conv A → conv B mid-stream wiped A's
 * accumulator and dropped any chunks A was still receiving. The Sidebar
 * also had no way to surface "this row is currently generating" because
 * the streaming flag lived inside ChatInterface.
 *
 * The store solves both:
 *   - Per-conversation message lists + flags survive across `useChat` resets,
 *     so the user can switch chats and come back to a still-running
 *     conversation with full progress visible.
 *   - The Sidebar subscribes to `getStreamingConversationIds()` so streaming
 *     rows can show a live indicator.
 *
 * The store is intentionally simple: a `Map<conversationId, ConversationState>`
 * snapshot, a `Set` of listeners, and a "version" tick that bumps on
 * every write so React's `useSyncExternalStore` can detect changes
 * without deep-comparing snapshots.
 */

import type { Message } from '../types/chat'

export interface ConversationState {
  messages: Message[]
  isAwaitingFirstChunk: boolean
  isStreaming: boolean
  /** True when the conversation finished streaming while the user was looking at a different chat. */
  hasUnread: boolean
  /** True when the stream ended with an error while the user was away. */
  hasError: boolean
}

const EMPTY_STATE: ConversationState = Object.freeze({
  messages: [],
  isAwaitingFirstChunk: false,
  isStreaming: false,
  hasUnread: false,
  hasError: false,
}) as ConversationState

const conversations = new Map<string, ConversationState>()
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
  for (const [id, state] of conversations.entries()) {
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

export function getSnapshot(conversationId: string | null): ConversationState {
  if (!conversationId) return EMPTY_STATE
  const existing = conversations.get(conversationId)
  return existing ?? EMPTY_STATE
}

export function setConversation(
  conversationId: string,
  updater: (prev: ConversationState) => ConversationState
): void {
  const prev = conversations.get(conversationId) ?? EMPTY_STATE
  const next = updater(prev)
  conversations.set(conversationId, next)
  notify()
}

export function clearConversation(conversationId: string): void {
  if (conversations.delete(conversationId)) {
    notify()
  }
}

export function getStreamingConversationIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return streamingIdsSnapshot
}

export function getUnreadConversationIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return unreadIdsSnapshot
}

export function getErrorConversationIds(): ReadonlySet<string> {
  rebuildIdsIfNeeded()
  return errorIdsSnapshot
}

// Test-only: drop everything. Lets vitest specs reset between cases.
export function __resetForTests(): void {
  conversations.clear()
  listeners.clear()
  streamingIdsSnapshot = new Set()
  unreadIdsSnapshot = new Set()
  errorIdsSnapshot = new Set()
  idsDirty = true
}
