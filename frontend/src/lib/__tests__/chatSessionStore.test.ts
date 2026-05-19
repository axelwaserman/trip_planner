/**
 * Vitest spec for chatSessionStore — the per-session subscribable store
 * useChat and Sidebar both read from.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  __resetForTests,
  getSnapshot,
  getStreamingSessionIds,
  setSession,
  subscribe,
} from '../chatSessionStore'

afterEach(() => {
  __resetForTests()
})

describe('chatSessionStore', () => {
  it('returns the same frozen empty snapshot for a missing session', () => {
    const a = getSnapshot('missing-1')
    const b = getSnapshot('missing-2')
    // Identity equality matters for useSyncExternalStore — without it the
    // hook would re-render on every snapshot read.
    expect(a).toBe(b)
    expect(a.messages).toEqual([])
    expect(a.isStreaming).toBe(false)
  })

  it('writes update the snapshot for the targeted session only', () => {
    setSession('a', () => ({ messages: [{ role: 'user', content: 'hi' }], isAwaitingFirstChunk: true, isStreaming: true, hasUnread: false, hasError: false }))
    expect(getSnapshot('a').messages).toHaveLength(1)
    expect(getSnapshot('b').messages).toHaveLength(0)
  })

  it('notifies subscribers when any session updates', () => {
    const listener = vi.fn()
    const unsubscribe = subscribe(listener)

    setSession('a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(1)

    setSession('b', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
    setSession('c', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('getStreamingSessionIds reflects only sessions with isStreaming=true', () => {
    setSession('streaming-a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    setSession('streaming-b', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    setSession('idle-c', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))

    const ids = getStreamingSessionIds()
    expect(ids.has('streaming-a')).toBe(true)
    expect(ids.has('streaming-b')).toBe(true)
    expect(ids.has('idle-c')).toBe(false)
    expect(ids.size).toBe(2)
  })

  it('stops including a session in getStreamingSessionIds when isStreaming flips false', () => {
    setSession('a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    expect(getStreamingSessionIds().has('a')).toBe(true)

    setSession('a', (prev) => ({ ...prev, isStreaming: false }))
    expect(getStreamingSessionIds().has('a')).toBe(false)
  })
})
