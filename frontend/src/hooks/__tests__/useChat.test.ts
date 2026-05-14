import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChat } from '../useChat'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSSEBody(...lines: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  const fullText = lines.join('\n') + '\n'
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(fullText))
      controller.close()
    },
  })
}

function mockSessionFetch(sessionData = { session_id: 'sess-1', provider: 'ollama', model: 'qwen3:4b' }) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(sessionData),
    body: null,
  })
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()

beforeEach(() => {
  localStorageMock.clear()
  Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Session initialisation
// ---------------------------------------------------------------------------

describe('session initialisation', () => {
  it('creates a session with defaults when localStorage is empty', async () => {
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/session',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ provider: 'ollama', model: 'qwen3:4b' }),
        })
      )
    })
  })

  it('creates a session using saved localStorage config', async () => {
    localStorage.setItem('llm_provider_config', JSON.stringify({ provider: 'openai', model: 'gpt-4o' }))
    const fetchMock = mockSessionFetch({ session_id: 'sess-2', provider: 'openai', model: 'gpt-4o' })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/session',
        expect.objectContaining({
          body: JSON.stringify({ provider: 'openai', model: 'gpt-4o' }),
        })
      )
    })
  })

  it('adds an error message when session creation fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    const { result } = renderHook(() => useChat())

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toMatch(/Failed to initialize/)
    })
  })
})

// ---------------------------------------------------------------------------
// handleProviderChange
// ---------------------------------------------------------------------------

describe('handleProviderChange', () => {
  it('clears messages and creates a new session', async () => {
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())

    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    act(() => {
      result.current.handleProviderChange('openai', 'gpt-4o')
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(result.current.messages).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// sendMessage — guard conditions
// ---------------------------------------------------------------------------

describe('sendMessage guards', () => {
  it('does nothing when text is empty', async () => {
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const callsBefore = fetchMock.mock.calls.length
    await act(async () => {
      await result.current.sendMessage('   ')
    })

    expect(fetchMock.mock.calls.length).toBe(callsBefore)
  })

  it('does nothing when there is no session', async () => {
    // Fail session creation so sessionId stays null
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.messages).toHaveLength(1)) // error message

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// sendMessage — happy path
// ---------------------------------------------------------------------------

describe('sendMessage happy path', () => {
  it('adds a user message immediately and an assistant message from the stream', async () => {
    const sessionFetch = mockSessionFetch()
    vi.stubGlobal('fetch', sessionFetch)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Hello!","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )

    const chatFetch = vi.fn().mockResolvedValue({ ok: true, body: sseBody })
    vi.stubGlobal('fetch', chatFetch)

    await act(async () => {
      await result.current.sendMessage('Hi there')
    })

    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[0]).toEqual({ role: 'user', content: 'Hi there' })
    expect(result.current.messages[1]).toEqual({ role: 'assistant', content: 'Hello!' })
  })

  it('accumulates content chunks into a single assistant message', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Chunk1","session_id":"sess-1"}',
      'data: {"type":"content","chunk":" Chunk2","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const assistantMsg = result.current.messages.find((m) => m.role === 'assistant')
    expect(assistantMsg?.content).toBe('Chunk1 Chunk2')
  })

  it('creates a thinking message from a thinking event', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"thinking","chunk":"Let me think...","session_id":"sess-1"}',
      'data: {"type":"content","chunk":"Answer","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const thinkingMsg = result.current.messages.find((m) => m.role === 'thinking')
    expect(thinkingMsg?.content).toBe('Let me think...')
  })

  it('creates a tool_execution message from a tool_call event and updates it with tool_result', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"session_id":"sess-1"}',
      'data: {"type":"tool_result","tool_name":"search","tool_result":"Found Paris","elapsed_ms":100,"session_id":"sess-1"}',
      'data: {"type":"content","chunk":"Great!","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const toolMsg = result.current.messages.find((m) => m.role === 'tool_execution')
    expect(toolMsg?.toolExecution?.callMetadata.tool_name).toBe('search')
    expect(toolMsg?.toolExecution?.resultMetadata?.summary).toBe('Found Paris')
    expect(toolMsg?.toolExecution?.resultMetadata?.elapsed_ms).toBe(100)
  })
})

// ---------------------------------------------------------------------------
// sendMessage — error handling
// ---------------------------------------------------------------------------

describe('sendMessage error handling', () => {
  it('adds an error assistant message when the fetch itself fails', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('adds an error message when the response is not ok', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('resets isLoading to false after an error', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('fail')))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('adds an error message when the response body is null', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: null }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('adds an error message when the stream emits an error event', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"error","error":"upstream failure"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('accumulates multiple thinking chunks into the same thinking message', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"thinking","chunk":"Part1","session_id":"sess-1"}',
      'data: {"type":"thinking","chunk":" Part2","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const thinkingMessages = result.current.messages.filter((m) => m.role === 'thinking')
    expect(thinkingMessages).toHaveLength(1)
    expect(thinkingMessages[0].content).toBe('Part1 Part2')
  })
})
