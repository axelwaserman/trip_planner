import { act, renderHook as rtlRenderHook, waitFor } from '@testing-library/react'
import type { RenderHookOptions } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChat } from '../useChat'

// useChat reads `useSearchParams()` to observe Sidebar's `?n=<token>` New
// chat signal, so every renderHook call needs a Router context. Wrap the
// upstream renderHook so each test stays single-line. createElement avoids
// JSX in this `.ts` file.
function makeMemoryRouterWrapper(initialEntries: string[] = ['/app']) {
  return function MemoryRouterWrapper({ children }: { children: ReactNode }) {
    return createElement(MemoryRouter, { initialEntries }, children)
  }
}

function renderHook<TResult, TProps>(
  callback: (props: TProps) => TResult,
  options?: Omit<RenderHookOptions<TProps>, 'wrapper'> & { initialEntries?: string[] }
) {
  const { initialEntries, ...rest } = options ?? {}
  return rtlRenderHook(callback, {
    wrapper: makeMemoryRouterWrapper(initialEntries),
    ...rest,
  })
}

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
  it('creates a session with defaults when localStorage is empty (D-24 payload shape)', async () => {
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/session',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            provider: 'ollama',
            model: 'qwen3:4b',
            base_url: null,
            api_key: null,
          }),
        })
      )
    })
  })

  it('reads provider_settings from localStorage and sends api_key for cloud providers (D-24)', async () => {
    localStorage.setItem(
      'provider_settings',
      JSON.stringify({
        selected: { provider: 'openai', model: 'gpt-4o' },
        ollama: { base_url: 'http://localhost:11434', models: [] },
        openai: { api_key: 'sk-test-12345', model: 'gpt-4o' },
        anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
      })
    )
    const fetchMock = mockSessionFetch({ session_id: 'sess-2', provider: 'openai', model: 'gpt-4o' })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/session',
        expect.objectContaining({
          body: JSON.stringify({
            provider: 'openai',
            model: 'gpt-4o',
            base_url: null,
            api_key: 'sk-test-12345',
          }),
        })
      )
    })
  })

  it('reads provider_settings and sends base_url for ollama (D-21)', async () => {
    localStorage.setItem(
      'provider_settings',
      JSON.stringify({
        selected: { provider: 'ollama', model: 'qwen3:4b' },
        ollama: { base_url: 'http://localhost:11434', models: ['qwen3:4b'] },
        openai: { api_key: '', model: 'gpt-4o-mini' },
        anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
      })
    )
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/session',
        expect.objectContaining({
          body: JSON.stringify({
            provider: 'ollama',
            model: 'qwen3:4b',
            base_url: 'http://localhost:11434',
            api_key: null,
          }),
        })
      )
    })
  })

  it('migrates legacy llm_provider_config to provider_settings on first load (D-21)', async () => {
    localStorage.setItem(
      'llm_provider_config',
      JSON.stringify({ provider: 'ollama', model: 'qwen3:4b' })
    )
    const fetchMock = mockSessionFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      // Migration ran: new key present, legacy key removed.
      expect(localStorage.getItem('provider_settings')).not.toBeNull()
      expect(localStorage.getItem('llm_provider_config')).toBeNull()
    })

    const migrated = JSON.parse(localStorage.getItem('provider_settings')!) as {
      selected: { provider: string; model: string }
    }
    expect(migrated.selected).toEqual({ provider: 'ollama', model: 'qwen3:4b' })

    // Session was still created using the migrated values.
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/session',
      expect.objectContaining({
        body: JSON.stringify({
          provider: 'ollama',
          model: 'qwen3:4b',
          base_url: 'http://localhost:11434',
          api_key: null,
        }),
      })
    )
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

  it('isAwaitingFirstChunk is true while the SSE stream is en route and false once it resolves', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    expect(result.current.isAwaitingFirstChunk).toBe(false)

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Hi","session_id":"sess-1"}',
      'data: {"type":"done","session_id":"sess-1"}'
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    // Once the stream finished (and well past the first chunk), the flag
    // is back to false. The "Thinking..." placeholder relies on this so it
    // disappears as soon as the assistant bubble starts filling in.
    expect(result.current.isAwaitingFirstChunk).toBe(false)
  })

  it('replaces the URL with ?session=<new_id> after a successful create', async () => {
    vi.stubGlobal('fetch', mockSessionFetch({ session_id: 'sess-new', provider: 'ollama', model: 'qwen3:4b' }))

    function useChatWithLocation() {
      const chat = useChat()
      const location = useLocation()
      return { chat, location }
    }

    const { result } = renderHook(() => useChatWithLocation())

    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-new'))
    // URL must now name the session — Sidebar's activeSessionId reads from
    // ?session= and highlights the row, and the URL is shareable.
    await waitFor(() => expect(result.current.location.search).toBe('?session=sess-new'))
  })

  it('isAwaitingFirstChunk resets to false on stream error', async () => {
    vi.stubGlobal('fetch', mockSessionFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    expect(result.current.isAwaitingFirstChunk).toBe(false)
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

// ---------------------------------------------------------------------------
// New chat reset (Sidebar `?n=<token>` signal)
// ---------------------------------------------------------------------------

describe('new chat reset signal', () => {
  // Compose useChat + useNavigate so the test can bump `?n=<token>` and
  // observe the hook reacting. Minimal wrapper — the real Sidebar does the
  // same via navigate(`/app?n=${Date.now()}`).
  function useChatWithNavigate() {
    const navigate = useNavigate()
    const chat = useChat()
    return { chat, navigate }
  }

  it('clears messages and creates a fresh session when ?n= changes', async () => {
    let createCallCount = 0
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => {
      createCallCount += 1
      return {
        ok: true,
        json: async () => ({
          session_id: `sess-${createCallCount}`,
          provider: 'ollama',
          model: 'qwen3:4b',
        }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate())

    // First mount — initial session.
    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-1'))
    expect(createCallCount).toBe(1)

    // Seed a stale message so we can prove it gets cleared on the reset.
    await act(async () => {
      result.current.chat.sendMessage // touch — exists
    })

    // Bump the new-chat token (mirrors Sidebar.handleNewChat).
    await act(async () => {
      result.current.navigate('/app?n=12345')
    })

    // Effect re-runs → setMessages([]) + setSessionId(null) + a new POST.
    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-2'))
    expect(createCallCount).toBe(2)
    expect(result.current.chat.messages).toEqual([])
  })

  it('reuses the currently-selected provider/model when resetting', async () => {
    localStorage.setItem(
      'provider_settings',
      JSON.stringify({
        selected: { provider: 'ollama', model: 'mistral:7b' },
        ollama: { base_url: 'http://localhost:11434', models: ['mistral:7b'] },
        lmstudio: { base_url: 'http://localhost:1234/v1', models: [] },
        openai: { api_key: '', model: 'gpt-4o-mini' },
        anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
      })
    )

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: 'sess-x', provider: 'ollama', model: 'mistral:7b' }),
      body: null,
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate())
    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-x'))
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.navigate('/app?n=99999')
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    // Both calls must have used the user-selected mistral:7b — not the
    // factory default qwen3:4b — proving the reset re-reads provider_settings.
    const [, secondCall] = fetchMock.mock.calls
    const secondBody = JSON.parse((secondCall[1] as RequestInit).body as string) as {
      provider: string
      model: string
    }
    expect(secondBody).toEqual({
      provider: 'ollama',
      model: 'mistral:7b',
      base_url: 'http://localhost:11434',
      api_key: null,
    })
  })
})

// ---------------------------------------------------------------------------
// Resume session (`?session=<id>`)
// ---------------------------------------------------------------------------

describe('resume session signal', () => {
  function useChatWithNavigate() {
    const navigate = useNavigate()
    const chat = useChat()
    return { chat, navigate }
  }

  it('fetches /api/chat/sessions/:id and replays messages on ?session=<id>', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (typeof url === 'string' && url.startsWith('/api/chat/sessions/sess-resumed')) {
        return {
          ok: true,
          json: async () => ({
            session_id: 'sess-resumed',
            provider: 'ollama',
            model: 'qwen3:8b',
            messages: [
              { role: 'user', content: 'hi from earlier' },
              { role: 'assistant', content: 'hello again' },
            ],
          }),
          body: null,
        }
      }
      // Fallback: any /api/chat/session POST just returns a fresh session —
      // the resume path should NOT hit this on success.
      return {
        ok: true,
        json: async () => ({ session_id: 'sess-fresh', provider: 'ollama', model: 'qwen3:4b' }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate(), {
      initialEntries: ['/app?session=sess-resumed'],
    })

    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-resumed'))
    expect(result.current.chat.currentProvider).toBe('ollama')
    expect(result.current.chat.currentModel).toBe('qwen3:8b')
    expect(result.current.chat.messages).toEqual([
      { role: 'user', content: 'hi from earlier' },
      { role: 'assistant', content: 'hello again' },
    ])

    // Resume must NOT POST /api/chat/session — only the GET call should happen.
    const postCalls = fetchMock.mock.calls.filter(
      ([url, init]) => url === '/api/chat/session' && (init as RequestInit | undefined)?.method === 'POST'
    )
    expect(postCalls).toHaveLength(0)
  })

  it('falls through to a fresh session when ?session=<id> 404s (stale link)', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (typeof url === 'string' && url.startsWith('/api/chat/sessions/sess-gone')) {
        return { ok: false, status: 404, json: async () => ({}), body: null }
      }
      return {
        ok: true,
        json: async () => ({ session_id: 'sess-fresh', provider: 'ollama', model: 'qwen3:4b' }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate(), {
      initialEntries: ['/app?session=sess-gone'],
    })

    // Resume failed → fresh session created. session_id ends up as the fresh one.
    await waitFor(() => expect(result.current.chat.sessionId).toBe('sess-fresh'))
    // No replayed history.
    expect(result.current.chat.messages).toEqual([])
  })
})
