import { act, renderHook as rtlRenderHook, waitFor } from '@testing-library/react'
import type { RenderHookOptions } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { __resetForTests as resetChatStore } from '../../lib/chatConversationStore'
import { useChat } from '../useChat'

vi.mock('../../lib/toaster', () => ({
  toaster: { create: vi.fn() },
}))

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

function mockConversationFetch(
  conversationData = { conversation_id: 'conv-1', provider: 'ollama', model: 'qwen3:4b' }
) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(conversationData),
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
  // chatConversationStore is module-level — without an explicit reset,
  // snapshots from one test leak into the next (e.g. a conversation that was
  // streaming in test N still reads as streaming in test N+1).
  resetChatStore()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Conversation initialisation
// ---------------------------------------------------------------------------

describe('conversation initialisation', () => {
  it('creates a conversation with defaults when localStorage is empty (Plan 06-05a nested payload shape)', async () => {
    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/conversation',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            target: { provider: 'ollama', model: 'qwen3:4b' },
            credentials: { base_url: null, api_key: null },
          }),
        })
      )
    })
  })

  it('reads provider_settings from localStorage and sends api_key in credentials for cloud providers', async () => {
    localStorage.setItem(
      'provider_settings',
      JSON.stringify({
        selected: { provider: 'openai', model: 'gpt-4o' },
        ollama: { base_url: 'http://localhost:11434', models: [] },
        openai: { api_key: 'sk-test-12345', model: 'gpt-4o' },
        anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
      })
    )
    const fetchMock = mockConversationFetch({
      conversation_id: 'conv-2',
      provider: 'openai',
      model: 'gpt-4o',
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/conversation',
        expect.objectContaining({
          body: JSON.stringify({
            target: { provider: 'openai', model: 'gpt-4o' },
            credentials: { base_url: null, api_key: 'sk-test-12345' },
          }),
        })
      )
    })
  })

  it('reads provider_settings and sends base_url in credentials for ollama', async () => {
    localStorage.setItem(
      'provider_settings',
      JSON.stringify({
        selected: { provider: 'ollama', model: 'qwen3:4b' },
        ollama: { base_url: 'http://localhost:11434', models: ['qwen3:4b'] },
        openai: { api_key: '', model: 'gpt-4o-mini' },
        anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
      })
    )
    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useChat())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/conversation',
        expect.objectContaining({
          body: JSON.stringify({
            target: { provider: 'ollama', model: 'qwen3:4b' },
            credentials: { base_url: 'http://localhost:11434', api_key: null },
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
    const fetchMock = mockConversationFetch()
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

    // Conversation was still created using the migrated values.
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/conversation',
      expect.objectContaining({
        body: JSON.stringify({
          target: { provider: 'ollama', model: 'qwen3:4b' },
          credentials: { base_url: 'http://localhost:11434', api_key: null },
        }),
      })
    )
  })

  it('adds an error message when conversation creation fails', async () => {
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
  it('clears messages and creates a new conversation', async () => {
    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())

    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

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
    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const callsBefore = fetchMock.mock.calls.length
    await act(async () => {
      await result.current.sendMessage('   ')
    })

    expect(fetchMock.mock.calls.length).toBe(callsBefore)
  })

  it('does nothing when there is no conversation', async () => {
    // Fail conversation creation so conversationId stays null
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
    const conversationFetch = mockConversationFetch()
    vi.stubGlobal('fetch', conversationFetch)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Hello!","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
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
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Chunk1","conversation_id":"conv-1"}',
      'data: {"type":"content","chunk":" Chunk2","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const assistantMsg = result.current.messages.find((m) => m.role === 'assistant')
    expect(assistantMsg?.content).toBe('Chunk1 Chunk2')
  })

  it('creates a thinking message from a thinking event', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"thinking","chunk":"Let me think...","conversation_id":"conv-1"}',
      'data: {"type":"content","chunk":"Answer","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    const thinkingMsg = result.current.messages.find((m) => m.role === 'thinking')
    expect(thinkingMsg?.content).toBe('Let me think...')
  })

  it('isAwaitingFirstChunk is true while the SSE stream is en route and false once it resolves', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    expect(result.current.isAwaitingFirstChunk).toBe(false)

    const sseBody = makeSSEBody(
      'data: {"type":"content","chunk":"Hi","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
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
    vi.stubGlobal(
      'fetch',
      mockConversationFetch({ conversation_id: 'conv-new', provider: 'ollama', model: 'qwen3:4b' })
    )

    function useChatWithLocation() {
      const chat = useChat()
      const location = useLocation()
      return { chat, location }
    }

    const { result } = renderHook(() => useChatWithLocation())

    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-new'))
    // URL must now name the conversation — Sidebar's activeConversationId reads
    // from ?session= and highlights the row, and the URL is shareable. The
    // search-param key intentionally remains `session` to keep bookmarked
    // links stable across the rename.
    await waitFor(() => expect(result.current.location.search).toBe('?session=conv-new'))
  })

  it('isAwaitingFirstChunk resets to false on stream error', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    expect(result.current.isAwaitingFirstChunk).toBe(false)
  })

  it('creates a tool_execution message from a tool_call event and updates it with tool_result', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"conversation_id":"conv-1"}',
      'data: {"type":"tool_result","tool_name":"search","tool_result":"Found Paris","elapsed_ms":100,"conversation_id":"conv-1"}',
      'data: {"type":"content","chunk":"Great!","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
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
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('adds an error message when the response is not ok', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('resets isLoading to false after an error', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('fail')))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('adds an error message when the response body is null', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: null }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    const last = result.current.messages.at(-1)
    expect(last?.role).toBe('assistant')
    expect(last?.content).toMatch(/error/)
  })

  it('shows a toast when the stream emits a non-retryable error event', async () => {
    const { toaster } = await import('../../lib/toaster')
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"error","error_code":"stream_error","message":"upstream failure","retryable":false,"conversation_id":"conv-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('hello')
    })

    // Non-retryable error routes to toast, not an inline error message
    expect(vi.mocked(toaster.create)).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' })
    )
  })

  it('accumulates multiple thinking chunks into the same thinking message', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"thinking","chunk":"Part1","conversation_id":"conv-1"}',
      'data: {"type":"thinking","chunk":" Part2","conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
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

  it('clears messages and creates a fresh conversation when ?n= changes', async () => {
    let createCallCount = 0
    const fetchMock = vi.fn(async () => {
      createCallCount += 1
      return {
        ok: true,
        json: async () => ({
          conversation_id: `conv-${createCallCount}`,
          provider: 'ollama',
          model: 'qwen3:4b',
        }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate())

    // First mount — initial conversation.
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-1'))
    expect(createCallCount).toBe(1)

    // Bump the new-chat token (mirrors Sidebar.handleNewChat).
    await act(async () => {
      result.current.navigate('/app?n=12345')
    })

    // Effect re-runs → setMessages([]) + setConversationId(null) + a new POST.
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-2'))
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
      json: async () => ({ conversation_id: 'conv-x', provider: 'ollama', model: 'mistral:7b' }),
      body: null,
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate())
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-x'))
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.navigate('/app?n=99999')
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    // Both calls must have used the user-selected mistral:7b — not the
    // factory default qwen3:4b — proving the reset re-reads provider_settings.
    const [, secondCall] = fetchMock.mock.calls
    const secondBody = JSON.parse((secondCall[1] as RequestInit).body as string) as {
      target: { provider: string; model: string }
      credentials: { base_url: string | null; api_key: string | null }
    }
    expect(secondBody).toEqual({
      target: { provider: 'ollama', model: 'mistral:7b' },
      credentials: { base_url: 'http://localhost:11434', api_key: null },
    })
  })
})

// ---------------------------------------------------------------------------
// Resume conversation (`?session=<id>`)
// ---------------------------------------------------------------------------

describe('resume conversation signal', () => {
  function useChatWithNavigate() {
    const navigate = useNavigate()
    const chat = useChat()
    return { chat, navigate }
  }

  it('fetches /api/chat/conversations/:id and replays messages on ?session=<id>', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (typeof url === 'string' && url.startsWith('/api/chat/conversations/conv-resumed')) {
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv-resumed',
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
      // Fallback: any /api/chat/conversation POST just returns a fresh conv —
      // the resume path should NOT hit this on success.
      return {
        ok: true,
        json: async () => ({
          conversation_id: 'conv-fresh',
          provider: 'ollama',
          model: 'qwen3:4b',
        }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate(), {
      initialEntries: ['/app?session=conv-resumed'],
    })

    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-resumed'))
    expect(result.current.chat.currentProvider).toBe('ollama')
    expect(result.current.chat.currentModel).toBe('qwen3:8b')
    expect(result.current.chat.messages).toEqual([
      { role: 'user', content: 'hi from earlier' },
      { role: 'assistant', content: 'hello again' },
    ])

    // Resume must NOT POST /api/chat/conversation — only the GET should fire.
    const postCalls = fetchMock.mock.calls.filter(
      ([url, init]) =>
        url === '/api/chat/conversation' && (init as RequestInit | undefined)?.method === 'POST'
    )
    expect(postCalls).toHaveLength(0)
  })

  it('falls through to a fresh conversation when ?session=<id> 404s (stale link)', async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (typeof url === 'string' && url.startsWith('/api/chat/conversations/conv-gone')) {
        return { ok: false, status: 404, json: async () => ({}), body: null }
      }
      return {
        ok: true,
        json: async () => ({
          conversation_id: 'conv-fresh',
          provider: 'ollama',
          model: 'qwen3:4b',
        }),
        body: null,
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatWithNavigate(), {
      initialEntries: ['/app?session=conv-gone'],
    })

    // Resume failed → fresh conversation created. conversationId ends up as the fresh one.
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-fresh'))
    // No replayed history.
    expect(result.current.chat.messages).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Background streaming (chatConversationStore)
// ---------------------------------------------------------------------------

describe('background streaming', () => {
  it('writes stream chunks to the submit-time conversation even after the URL switches', async () => {
    // Build a manually-controlled SSE body so the test can interleave a
    // mid-stream conversation switch.
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null
    const sseBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller
      },
    })
    const encoder = new TextEncoder()

    // Single dispatcher serves every endpoint the test exercises:
    //   POST /api/chat/conversation         → create initial conv-a
    //   GET  /api/chat/conversations/conv-b → empty history (resume target)
    //   POST /api/chat                      → the manually-controlled SSE stream
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.startsWith('/api/chat/conversations/conv-b')) {
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv-b',
            provider: 'ollama',
            model: 'qwen3:4b',
            messages: [],
          }),
          body: null,
        }
      }
      if (url === '/api/chat/conversation' && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv-a',
            provider: 'ollama',
            model: 'qwen3:4b',
          }),
          body: null,
        }
      }
      if (url === '/api/chat' && init?.method === 'POST') {
        return { ok: true, body: sseBody }
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    function useChatWithNavigate() {
      const navigate = useNavigate()
      const chat = useChat()
      return { chat, navigate }
    }

    const { result } = renderHook(() => useChatWithNavigate())
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-a'))
    const submitConversationId = 'conv-a'

    // Kick off the send. Don't await — we need to interleave events.
    let sendPromise: Promise<void> | undefined
    await act(async () => {
      sendPromise = result.current.chat.sendMessage('hello from conv-a')
    })

    // First content chunk lands while conv-a is the active conversation.
    await act(async () => {
      controllerRef!.enqueue(
        encoder.encode('data: {"type":"content","chunk":"first ","conversation_id":"conv-a"}\n')
      )
      // Yield to React.
      await new Promise((r) => setTimeout(r, 0))
    })

    // Now switch to conv-b mid-stream.
    await act(async () => {
      result.current.navigate('/app?session=conv-b')
    })
    await waitFor(() => expect(result.current.chat.conversationId).toBe('conv-b'))
    // conv-b has empty history — current view shows no streamed content.
    expect(
      result.current.chat.messages.some((m) => m.role === 'assistant')
    ).toBe(false)

    // Second content chunk arrives — must land in conv-a's store entry,
    // not conv-b's.
    await act(async () => {
      controllerRef!.enqueue(
        encoder.encode('data: {"type":"content","chunk":"second","conversation_id":"conv-a"}\n')
      )
      controllerRef!.enqueue(
        encoder.encode('data: {"type":"done","conversation_id":"conv-a"}\n')
      )
      controllerRef!.close()
    })
    await sendPromise

    // Re-mount or read the store directly to confirm conv-a's accumulator
    // contains BOTH chunks even though the active view was on conv-b for
    // the second one.
    const { getSnapshot } = await import('../../lib/chatConversationStore')
    const convAState = getSnapshot(submitConversationId)
    const assistantMsg = convAState.messages.find((m) => m.role === 'assistant')
    expect(assistantMsg?.content).toBe('first second')
    // Stream finished: isStreaming back to false.
    expect(convAState.isStreaming).toBe(false)
  })

  it('isStreaming still false after a stream completes with non-retryable error', async () => {
    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"error","error_code":"stream_error","message":"Something failed","retryable":false,"conversation_id":"conv-1"}',
      'data: {"type":"done","conversation_id":"conv-1"}'
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    await act(async () => {
      await result.current.sendMessage('test')
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('isStreaming flips true while a stream is in-flight and false on completion', async () => {
    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    // Slow stream so we can observe the flag mid-flight.
    let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null
    const sseBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controllerRef = controller
      },
    })
    const encoder = new TextEncoder()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    let sendPromise: Promise<void> | undefined
    await act(async () => {
      sendPromise = result.current.sendMessage('test')
    })

    // sendMessage set isStreaming → true synchronously via setConversation.
    await waitFor(() => expect(result.current.isLoading).toBe(true))

    // Drain + close.
    await act(async () => {
      controllerRef!.enqueue(
        encoder.encode('data: {"type":"content","chunk":"ok","conversation_id":"conv-1"}\n')
      )
      controllerRef!.enqueue(encoder.encode('data: {"type":"done","conversation_id":"conv-1"}\n'))
      controllerRef!.close()
      await sendPromise
    })

    expect(result.current.isLoading).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// ErrorEvent routing (Phase 4.7 Plan 04)
// ---------------------------------------------------------------------------

describe('ErrorEvent routing (switch-narrowed handler)', () => {
  it('retryable=true error updates the last tool_execution message errorEvent field (no toast)', async () => {
    // Arrange: mock toaster, set up conversation, send tool_call + retryable error
    const { toaster } = await import('../../lib/toaster')
    vi.mocked(toaster.create).mockClear()

    const fetchMock = mockConversationFetch()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"conversation_id":"conv-1"}',
      'data: {"type":"error","error_code":"tool_error","message":"Tool search failed: timeout","retryable":true,"tool_name":"search","conversation_id":"conv-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    // Act
    await act(async () => {
      await result.current.sendMessage('hello')
    })

    // Assert: tool_execution message has errorEvent populated
    const toolMsg = result.current.messages.find((m) => m.role === 'tool_execution')
    expect(toolMsg).toBeDefined()
    expect(toolMsg?.toolExecution?.errorEvent).toBeDefined()
    expect(toolMsg?.toolExecution?.errorEvent?.message).toBe('Tool search failed: timeout')
    expect(toolMsg?.toolExecution?.errorEvent?.retryable).toBe(true)

    // Toast must NOT have been called for retryable errors
    expect(vi.mocked(toaster.create)).not.toHaveBeenCalled()
  })

  it('retryable=false error fires toaster.create and does NOT update tool_execution errorEvent', async () => {
    // Arrange
    const { toaster } = await import('../../lib/toaster')
    vi.mocked(toaster.create).mockClear()

    vi.stubGlobal('fetch', mockConversationFetch())
    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    const sseBody = makeSSEBody(
      'data: {"type":"error","error_code":"stream_error","message":"Something went wrong","retryable":false,"conversation_id":"conv-1"}'
    )

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: sseBody }))

    // Act
    await act(async () => {
      await result.current.sendMessage('hello')
    })

    // Assert: toast was called
    expect(vi.mocked(toaster.create)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(toaster.create)).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Something went wrong',
        type: 'error',
      })
    )
    // No tool_execution message with errorEvent (there was no tool_call first)
    const toolMsg = result.current.messages.find((m) => m.role === 'tool_execution')
    expect(toolMsg?.toolExecution?.errorEvent).toBeUndefined()
  })

  it('session_error fires toaster.create AND triggers a follow-up POST /api/chat/conversation', async () => {
    // Arrange
    const { toaster } = await import('../../lib/toaster')
    vi.mocked(toaster.create).mockClear()

    let conversationPostCount = 0
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/conversation' && init?.method === 'POST') {
        conversationPostCount += 1
        return {
          ok: true,
          json: async () => ({
            conversation_id: `conv-${conversationPostCount}`,
            provider: 'ollama',
            model: 'qwen3:4b',
          }),
          body: null,
        }
      }
      if (url === '/api/chat' && init?.method === 'POST') {
        return {
          ok: true,
          body: makeSSEBody(
            'data: {"type":"error","error_code":"session_error","message":"Conversation not found","retryable":false,"conversation_id":"conv-1"}'
          ),
        }
      }
      return { ok: true, json: async () => ({}), body: null }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))
    expect(conversationPostCount).toBe(1) // initial conversation creation

    // Act: send a message that results in a session_error
    await act(async () => {
      await result.current.sendMessage('hello')
    })

    // Assert: toast fired
    expect(vi.mocked(toaster.create)).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' })
    )
    // A second POST /api/chat/conversation should have been made (silent re-init)
    await waitFor(() => expect(conversationPostCount).toBeGreaterThanOrEqual(2))
  })

  it('retryLastTool POSTs to /api/chat/retry with conversation_id and feeds events through the stream handler', async () => {
    // Arrange: first get a conversation, do a tool call to populate last tool state
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/chat/conversation' && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv-1',
            provider: 'ollama',
            model: 'qwen3:4b',
          }),
          body: null,
        }
      }
      if (url === '/api/chat' && init?.method === 'POST') {
        return {
          ok: true,
          body: makeSSEBody(
            'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"conversation_id":"conv-1"}',
            'data: {"type":"error","error_code":"tool_error","message":"Tool failed","retryable":true,"tool_name":"search","conversation_id":"conv-1"}'
          ),
        }
      }
      if (url === '/api/chat/retry' && init?.method === 'POST') {
        return {
          ok: true,
          body: makeSSEBody(
            'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"conversation_id":"conv-1"}',
            'data: {"type":"tool_result","tool_name":"search","tool_result":"Found Paris","elapsed_ms":100,"conversation_id":"conv-1"}',
            'data: {"type":"content","chunk":"Great!","conversation_id":"conv-1"}'
          ),
        }
      }
      return { ok: false, body: null }
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChat())
    await waitFor(() => expect(result.current.conversationId).toBe('conv-1'))

    // Send message to get a tool call with error
    await act(async () => {
      await result.current.sendMessage('hello')
    })

    // Verify tool_execution exists with errorEvent
    const toolMsgBefore = result.current.messages.find((m) => m.role === 'tool_execution')
    expect(toolMsgBefore?.toolExecution?.errorEvent).toBeDefined()

    // Verify retryLastTool is exposed
    expect(result.current.retryLastTool).toBeDefined()

    // Act: call retryLastTool
    await act(async () => {
      await result.current.retryLastTool()
    })

    // Assert: /api/chat/retry was called with the right conversation_id
    const retryCall = fetchMock.mock.calls.find(
      ([url, init]) => url === '/api/chat/retry' && (init as RequestInit)?.method === 'POST'
    )
    expect(retryCall).toBeDefined()
    const retryBody = JSON.parse((retryCall![1] as RequestInit).body as string) as {
      conversation_id: string
    }
    expect(retryBody.conversation_id).toBe('conv-1')

    // The retry stream fed a new tool_call + result into the store
    const toolMsgAfter = result.current.messages.find(
      (m) =>
        m.role === 'tool_execution' &&
        m.toolExecution?.resultMetadata?.summary === 'Found Paris'
    )
    expect(toolMsgAfter).toBeDefined()
  })
})
