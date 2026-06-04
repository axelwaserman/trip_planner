/**
 * Vitest spec for chatConversationStore — the per-conversation subscribable
 * store useChat and Sidebar both read from.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  __resetForTests,
  getSnapshot,
  getStreamingConversationIds,
  setConversation,
  subscribe,
} from '../chatConversationStore'

afterEach(() => {
  __resetForTests()
})

describe('chatConversationStore', () => {
  it('returns the same frozen empty snapshot for a missing conversation', () => {
    const a = getSnapshot('missing-1')
    const b = getSnapshot('missing-2')
    // Identity equality matters for useSyncExternalStore — without it the
    // hook would re-render on every snapshot read.
    expect(a).toBe(b)
    expect(a.messages).toEqual([])
    expect(a.isStreaming).toBe(false)
  })

  it('writes update the snapshot for the targeted conversation only', () => {
    setConversation('a', () => ({ messages: [{ role: 'user', content: 'hi' }], isAwaitingFirstChunk: true, isStreaming: true, hasUnread: false, hasError: false }))
    expect(getSnapshot('a').messages).toHaveLength(1)
    expect(getSnapshot('b').messages).toHaveLength(0)
  })

  it('notifies subscribers when any conversation updates', () => {
    const listener = vi.fn()
    const unsubscribe = subscribe(listener)

    setConversation('a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(1)

    setConversation('b', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
    setConversation('c', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('getStreamingConversationIds reflects only conversations with isStreaming=true', () => {
    setConversation('streaming-a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    setConversation('streaming-b', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    setConversation('idle-c', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: false, hasUnread: false, hasError: false }))

    const ids = getStreamingConversationIds()
    expect(ids.has('streaming-a')).toBe(true)
    expect(ids.has('streaming-b')).toBe(true)
    expect(ids.has('idle-c')).toBe(false)
    expect(ids.size).toBe(2)
  })

  it('stops including a conversation in getStreamingConversationIds when isStreaming flips false', () => {
    setConversation('a', () => ({ messages: [], isAwaitingFirstChunk: false, isStreaming: true, hasUnread: false, hasError: false }))
    expect(getStreamingConversationIds().has('a')).toBe(true)

    setConversation('a', (prev) => ({ ...prev, isStreaming: false }))
    expect(getStreamingConversationIds().has('a')).toBe(false)
  })
})
