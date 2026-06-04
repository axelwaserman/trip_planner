/**
 * Vitest spec for the useConversations hook.
 *
 * Covers the four contract behaviors:
 *   1. Calls GET /api/chat/conversations on mount (with apiFetch's auth header path).
 *   2. Parses {conversations: [...]} on a 200 response.
 *   3. Sets a non-null error on a non-2xx response.
 *   4. refetch() re-runs the request.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useConversations } from '../useConversations'

function mockConversationsFetch(
  body: unknown = { conversations: [] },
  ok: boolean = true,
  status: number = 200
) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
}

describe('useConversations', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('calls /api/chat/conversations on mount', async () => {
    const fetchMock = mockConversationsFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useConversations())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/conversations',
        expect.any(Object)
      )
    })
  })

  it('returns parsed conversations on a 200 response', async () => {
    const fetchMock = mockConversationsFetch({
      conversations: [
        {
          conversation_id: 'c1',
          created_at: '2026-05-17T00:00:00Z',
          provider: 'ollama',
          model: 'qwen3:4b',
          first_message_preview: 'Hello',
        },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useConversations())

    await waitFor(() => {
      expect(result.current.conversations.length).toBe(1)
      expect(result.current.conversations[0].conversation_id).toBe('c1')
      expect(result.current.conversations[0].first_message_preview).toBe('Hello')
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('sets a non-null error on a non-2xx response', async () => {
    const fetchMock = mockConversationsFetch({}, false, 500)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useConversations())

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('refetch re-runs the request', async () => {
    const fetchMock = mockConversationsFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useConversations())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    act(() => {
      result.current.refetch()
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })
})
