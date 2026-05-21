import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ChatStreamEvent, ErrorEvent, Message, MessageType } from '../types/chat'
import { apiFetch } from '../lib/auth'
import {
  getSnapshot as getSessionSnapshot,
  setSession,
  subscribe as subscribeToStore,
} from '../lib/chatSessionStore'
import {
  mapProbeError,
  type BackendProbeError,
  type ProviderErrorView,
} from '../lib/providerErrors'
import {
  DEFAULT_PROVIDER_SETTINGS,
  loadProviderSettings as loadSharedProviderSettings,
  type ProviderSettings,
} from '../lib/providerSettings'
import { toaster } from '../lib/toaster'
import { readSSEStream } from './useSSEStream'

interface UseChatReturn {
  messages: Message[]
  isLoading: boolean
  // True between submitting a message and the first SSE event arriving back.
  // ChatInterface shows the "Thinking..." placeholder only while this is
  // true — once content/thinking/tool events start streaming the placeholder
  // is redundant with the assistant bubble that's actively filling in.
  isAwaitingFirstChunk: boolean
  sessionId: string | null
  currentProvider: string
  currentModel: string
  providerError: ProviderErrorView | null
  sendMessage: (text: string) => Promise<void>
  handleProviderChange: (provider: string, model: string) => void
  retryProvider: () => void
  // Re-streams the last tool invocation via POST /api/chat/retry.
  // No-op if sessionId is null or the session is currently streaming.
  retryLastTool: () => Promise<void>
}

interface SessionData {
  session_id: string
  provider: string
  model: string
}

type CreateSessionResult =
  | { ok: true; data: SessionData }
  | { ok: false; probeError: ProviderErrorView }
  | { ok: false; probeError: null }

// ProviderSettings + DEFAULT_PROVIDER_SETTINGS now live in
// `frontend/src/lib/providerSettings.ts` (the shared module promoted by Plan
// 08b so Sidebar/Settings/cards/hooks can co-consume without circular
// imports). useChat re-uses the same shape verbatim — the only difference is
// that loadSharedProviderSettings always returns a complete record (defaults
// back-fill missing entries), so the local `loadProviderSettings()` here
// simply forwards to it and re-narrows nullability for the existing
// resolveSelection wiring.

interface ResolvedSelection {
  provider: string
  model: string
  baseUrl: string | null
  apiKey: string | null
}

/**
 * Pull the active selection out of a ProviderSettings record.
 *
 * - For ollama: base_url is non-null, api_key is null.
 * - For openai/anthropic: api_key is non-null (may be empty string), base_url null.
 * - Empty api_key strings are normalised to null so the backend factory falls
 *   back to its env-var precedence (D-08).
 */
function resolveSelection(settings: ProviderSettings): ResolvedSelection {
  const { provider, model } = settings.selected
  if (provider === 'ollama') {
    return {
      provider,
      model,
      baseUrl: settings.ollama.base_url || null,
      apiKey: null,
    }
  }
  if (provider === 'lmstudio') {
    return {
      provider,
      model,
      baseUrl: settings.lmstudio.base_url || null,
      apiKey: null,
    }
  }
  if (provider === 'openai' || provider === 'anthropic') {
    const key = settings[provider].api_key
    return {
      provider,
      model,
      baseUrl: null,
      apiKey: key.length > 0 ? key : null,
    }
  }
  // Unknown provider — fall through to a permissive shape; the backend
  // SessionCreateRequest validators will reject it with a structured error.
  return { provider, model, baseUrl: null, apiKey: null }
}

/**
 * Forward to the shared module for the canonical migration handling.
 * Returns null only when the storage shim is itself unavailable — every
 * other path returns a complete record. The legacy useChat behaviour
 * treated "no settings ever persisted" as null so the backend factory
 * falls back to its env-var precedence (D-08); we preserve that signal
 * by detecting the cold-start case via a single localStorage probe BEFORE
 * delegating, keeping the original behaviour bit-identical.
 */
function loadProviderSettings(): ProviderSettings | null {
  try {
    const existing = localStorage.getItem('provider_settings')
    const legacy = localStorage.getItem('llm_provider_config')
    if (!existing && !legacy) {
      // Cold first run — preserve the original null signal so initSession
      // sends null base_url + null api_key (backend env-var fallback path).
      return null
    }
    return loadSharedProviderSettings()
  } catch {
    return null
  }
}

function isProbeErrorBody(value: unknown): value is { detail: BackendProbeError } {
  if (typeof value !== 'object' || value === null) return false
  const detail = (value as { detail?: unknown }).detail
  if (typeof detail !== 'object' || detail === null) return false
  const d = detail as Record<string, unknown>
  return (
    typeof d.error === 'string' &&
    typeof d.message === 'string' &&
    typeof d.hint === 'string'
  )
}

async function createSession(
  provider: string,
  model: string,
  baseUrl: string | null,
  apiKey: string | null
): Promise<CreateSessionResult> {
  const response = await apiFetch('/api/chat/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // Backend SessionCreateRequest (D-24) uses snake_case wire keys.
    body: JSON.stringify({ provider, model, base_url: baseUrl, api_key: apiKey }),
  })

  if (response.ok) {
    const data = (await response.json()) as SessionData
    return { ok: true, data }
  }

  // Try to parse the structured probe error body. Anything else falls through
  // to a non-probe failure that the caller's existing error UI handles.
  try {
    const body: unknown = await response.json()
    if (isProbeErrorBody(body)) {
      return {
        ok: false,
        probeError: mapProbeError(body.detail, { provider, model }),
      }
    }
  } catch {
    // Body wasn't JSON — fall through.
  }
  return { ok: false, probeError: null }
}

export function useChat(): UseChatReturn {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [currentProvider, setCurrentProvider] = useState('ollama')
  const [currentModel, setCurrentModel] = useState('qwen3:4b')
  const [providerError, setProviderError] = useState<ProviderErrorView | null>(null)
  // Session-init failure surfaces here when the create call returned a
  // non-probe failure (no session_id to key the store entry on). Cleared
  // every time we successfully initialize a session.
  const [initFailureMessage, setInitFailureMessage] = useState<string | null>(null)

  // Per-session state lives in chatSessionStore so a switch from conv A → B
  // mid-stream doesn't drop A's accumulator and the Sidebar can surface
  // "this row is generating" indicators from the same source. The hook only
  // reads the slice for the currently-active session_id.
  const sessionSnapshot = useSyncExternalStore(
    subscribeToStore,
    useCallback(() => getSessionSnapshot(sessionId), [sessionId])
  )
  // When session init failed before a session_id existed, expose the inline
  // error message via the same `messages` array consumers already render.
  const messages: Message[] = sessionId
    ? sessionSnapshot.messages
    : initFailureMessage
      ? [{ role: 'assistant', content: initFailureMessage }]
      : []
  const isLoading = sessionSnapshot.isStreaming
  const isAwaitingFirstChunk = sessionSnapshot.isAwaitingFirstChunk

  // The Sidebar bumps `?n=<timestamp>` whenever the user clicks "New chat".
  // This is the only signal useChat watches to know it should clear messages
  // and create a fresh session — purely URL-driven so the hook stays oblivious
  // to where the click came from. Mount-time init runs with `n === null`.
  //
  // `?session=<id>` is the resume signal: the Sidebar's recent-chats list
  // navigates to /app?session=<id> and useChat fetches the history for that
  // session, replays it into messages, and adopts the provider/model the
  // session was bound to (rather than POSTing /api/chat/session). Both
  // params are mutually exclusive in practice — Sidebar emits one or the
  // other — but the resume path takes precedence if both are present so
  // an accidental ?n=...&session=... wouldn't silently start a new chat.
  const [searchParams] = useSearchParams()
  const newChatToken = searchParams.get('n')
  const resumeSessionId = searchParams.get('session')
  const navigate = useNavigate()

  // Tracks the session id useChat has already initialized for. Used to skip
  // the resume-from-URL effect when initSession just replaced the URL with
  // ?session=<new_id> on its own — without this guard the effect would
  // re-fire, wipe messages, and re-fetch history for a session it just
  // created. Distinct from `sessionId` state because we want to remember
  // it across the effect's reset-then-initialize cycle.
  const ownedSessionIdRef = useRef<string | null>(null)
  // Mirror of sessionId state kept in a ref so the sendMessage finally block
  // can read the CURRENT active session without capturing stale closure values.
  const activeSessionIdRef = useRef<string | null>(sessionId)
  activeSessionIdRef.current = sessionId

  const initSession = useCallback(
    async (provider: string, model: string, baseUrl: string | null, apiKey: string | null) => {
      setProviderError(null)
      setInitFailureMessage(null)
      setCurrentProvider(provider)
      setCurrentModel(model)

      try {
        const result = await createSession(provider, model, baseUrl, apiKey)

        if (result.ok) {
          ownedSessionIdRef.current = result.data.session_id
          // Seed the store with an empty state for the new session so
          // useSyncExternalStore returns a stable empty snapshot rather
          // than briefly showing whatever the previous session held.
          setSession(result.data.session_id, () => ({
            messages: [],
            isAwaitingFirstChunk: false,
            isStreaming: false,
            hasUnread: false,
            hasError: false,
          }))
          setSessionId(result.data.session_id)
          setCurrentProvider(result.data.provider)
          setCurrentModel(result.data.model)
          // Replace the URL so the Sidebar's activeSessionId highlights the
          // new row and the page is bookmarkable / shareable. `replace: true`
          // avoids polluting back-button history with `/app?n=<token>` →
          // `/app?session=<id>` pairs. The effect won't re-run as a resume
          // because ownedSessionIdRef already holds the new id by the time
          // the URL change fires the next pass.
          navigate(`/app?session=${result.data.session_id}`, { replace: true })
          return
        }

        if (result.probeError) {
          setProviderError(result.probeError)
          return
        }

        // Failed init: surface the error inline (no session_id to key the
        // store on). Cleared on the next successful initSession.
        setInitFailureMessage('❌ Failed to initialize chat session. Please refresh the page.')
      } catch {
        // apiFetch's 401 handler already redirected; nothing to do here.
      }
    },
    [navigate]
  )

  const resumeSession = useCallback(async (id: string): Promise<boolean> => {
    setProviderError(null)
    try {
      const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}`)
      if (!response.ok) {
        // 404 (not yours / missing), 401 (apiFetch already redirected), etc.
        return false
      }
      const body = (await response.json()) as {
        session_id: string
        provider: string
        model: string
        messages: Array<{ role: 'user' | 'assistant'; content: string }>
      }
      ownedSessionIdRef.current = body.session_id
      setSessionId(body.session_id)
      setCurrentProvider(body.provider)
      setCurrentModel(body.model)
      setInitFailureMessage(null)
      // Seed the store with the persisted history. Don't overwrite an
      // already-streaming session — picking conv A from the Sidebar while
      // its previous response is still streaming should keep the live
      // accumulator visible, not replace it with the partial server-side
      // history. The "isStreaming" flag is the canonical guard.
      // If the store already has messages (e.g. thinking tokens + tool cards
      // accumulated during a previous stream this session), preserve them —
      // server history only carries user/assistant text and would discard the
      // richer client-side rows on re-navigation.
      setSession(body.session_id, (prev) => {
        if (prev.isStreaming) return prev
        if (prev.messages.length > 0) return { ...prev, hasUnread: false, hasError: false }
        return {
          messages: body.messages.map((msg) => ({
            role: msg.role as MessageType,
            content: msg.content,
          })),
          isAwaitingFirstChunk: false,
          isStreaming: false,
          hasUnread: false,
          hasError: false,
        }
      })
      return true
    } catch {
      return false
    }
  }, [])

  useEffect(() => {
    // D-21: read provider_settings (new key). If absent, one-shot migrate from
    // the legacy 'llm_provider_config' key (Phase 4.1/4.2). If neither exists
    // (cold first run), use ollama/qwen3:4b with null base_url + api_key so
    // the backend factory falls back to its env-var precedence (D-08).
    //
    // Re-runs whenever `?n=<token>` or `?session=<id>` changes:
    //   - ?session=<id> → fetch history, replay messages, adopt the session's
    //     bound provider/model (no new POST /api/chat/session). Falls through
    //     to the new-chat path on 404 so a stale Sidebar link can't soft-lock
    //     the chat.
    //   - ?n=<token>    → clear messages and POST /api/chat/session with the
    //     user's currently-selected provider/model (Sidebar's "New chat").
    //
    // Bail when the URL already names a session this hook just created or
    // resumed — initSession replaces the URL with /app?session=<new_id> so
    // the new chat row highlights, and we'd otherwise re-fetch its empty
    // history and wipe the local state moments after creating it.
    if (resumeSessionId && resumeSessionId === ownedSessionIdRef.current) {
      return
    }

    // Drop the local sessionId so the snapshot reads as empty until the
    // resume / create finishes. The store entry for the OLD session is
    // intentionally NOT cleared — it might still be streaming in the
    // background and we want the user to see its progress when they
    // navigate back. The store keeps each session's snapshot for the
    // lifetime of the page (or until the user reloads).
    setSessionId(null)
    setInitFailureMessage(null)

    let cancelled = false
    void (async () => {
      if (resumeSessionId) {
        const ok = await resumeSession(resumeSessionId)
        if (cancelled) return
        if (ok) return
        // 404 / cross-user → fall through to a fresh session below.
      }

      if (cancelled) return
      const settings = loadProviderSettings()
      if (settings === null) {
        void initSession('ollama', 'qwen3:4b', null, null)
        return
      }
      const selection = resolveSelection(settings)
      void initSession(selection.provider, selection.model, selection.baseUrl, selection.apiKey)
    })()

    return () => {
      cancelled = true
    }
  }, [initSession, resumeSession, newChatToken, resumeSessionId])

  const handleProviderChange = useCallback(
    (provider: string, model: string) => {
      setProviderError(null)
      // Guard: if provider and model haven't changed AND the session is empty,
      // there's nothing to do — skip the redundant initSession call that would
      // create a second new session for the same config on an empty session.
      if (
        provider === currentProvider &&
        model === currentModel &&
        sessionId !== null &&
        getSessionSnapshot(sessionId).messages.length === 0
      ) {
        return
      }
      // initSession will seed a fresh empty store entry for the new session
      // id; the previous session's entry stays put so a background stream
      // there can keep updating the Sidebar indicator.
      // Re-read provider_settings so a fresh paste of api_key / base_url on the
      // settings page is picked up at session-create time (D-21 + D-08).
      const settings = loadProviderSettings() ?? DEFAULT_PROVIDER_SETTINGS
      const merged: ProviderSettings = {
        ...settings,
        selected: {
          provider: provider as ProviderSettings['selected']['provider'],
          model,
        },
      }
      const selection = resolveSelection(merged)
      void initSession(selection.provider, selection.model, selection.baseUrl, selection.apiKey)
    },
    [initSession, currentProvider, currentModel, sessionId]
  )

  const retryProvider = useCallback(() => {
    setProviderError(null)
    const settings = loadProviderSettings() ?? DEFAULT_PROVIDER_SETTINGS
    const merged: ProviderSettings = {
      ...settings,
      selected: {
        provider: currentProvider as ProviderSettings['selected']['provider'],
        model: currentModel,
      },
    }
    const selection = resolveSelection(merged)
    void initSession(selection.provider, selection.model, selection.baseUrl, selection.apiKey)
  }, [currentProvider, currentModel, initSession])

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || !sessionId) return
      // Per-session re-entrancy: if this session is already streaming,
      // refuse a second submission. Other sessions can stream concurrently.
      if (getSessionSnapshot(sessionId).isStreaming) return

      // Capture the submit-time session id. Every store write inside the
      // SSE loop targets THIS id, even if the user navigates away and the
      // hook's `sessionId` state moves on. That's how a switch from conv A
      // → B mid-stream keeps A's accumulator filling in the background and
      // why a Sidebar indicator on A's row stays accurate.
      const submitSessionId = sessionId

      setSession(submitSessionId, (prev) => ({
        messages: [...prev.messages, { role: 'user', content: text }],
        isAwaitingFirstChunk: true,
        isStreaming: true,
        hasUnread: false,
        hasError: false,
      }))

      // Track stream state outside React — these are only read/written
      // during the synchronous SSE event loop.
      let isStreamingAssistant = false
      let isStreamingThinking = false
      let firstChunkSeen = false
      const markFirstChunk = () => {
        if (firstChunkSeen) return
        firstChunkSeen = true
        setSession(submitSessionId, (prev) => ({
          ...prev,
          isAwaitingFirstChunk: false,
        }))
      }

      const appendThinkingChunk = (chunk: string) => {
        setSession(submitSessionId, (prev) => {
          if (!isStreamingThinking) {
            return {
              ...prev,
              messages: [...prev.messages, { role: 'thinking' as MessageType, content: chunk }],
            }
          }
          // Append to the last thinking message (walk back to find it).
          for (let i = prev.messages.length - 1; i >= 0; i--) {
            if (prev.messages[i].role === 'thinking') {
              return {
                ...prev,
                messages: prev.messages.map((msg, idx) =>
                  idx === i ? { ...msg, content: msg.content + chunk } : msg
                ),
              }
            }
          }
          return prev
        })
      }

      const appendContentChunk = (chunk: string) => {
        setSession(submitSessionId, (prev) => {
          if (!isStreamingAssistant) {
            return {
              ...prev,
              messages: [...prev.messages, { role: 'assistant' as MessageType, content: chunk }],
            }
          }
          for (let i = prev.messages.length - 1; i >= 0; i--) {
            if (prev.messages[i].role === 'assistant') {
              return {
                ...prev,
                messages: prev.messages.map((msg, idx) =>
                  idx === i ? { ...msg, content: msg.content + chunk } : msg
                ),
              }
            }
          }
          return prev
        })
      }

      const appendToolCall = (toolName: string, toolArgs: Record<string, unknown>) => {
        setSession(submitSessionId, (prev) => ({
          ...prev,
          messages: [
            ...prev.messages,
            {
              role: 'tool_execution' as MessageType,
              content: '',
              toolExecution: {
                callMetadata: {
                  tool_name: toolName,
                  arguments: toolArgs,
                  started_at: Date.now(),
                  status: 'executing',
                },
              },
            },
          ],
        }))
      }

      const updateToolResult = (toolResult: string, elapsedMs: number) => {
        setSession(submitSessionId, (prev) => {
          let lastToolIndex = -1
          for (let i = prev.messages.length - 1; i >= 0; i--) {
            if (prev.messages[i].role === 'tool_execution') {
              lastToolIndex = i
              break
            }
          }
          if (lastToolIndex === -1) return prev
          return {
            ...prev,
            messages: prev.messages.map((msg, i) =>
              i === lastToolIndex && msg.toolExecution
                ? {
                    ...msg,
                    toolExecution: {
                      ...msg.toolExecution,
                      resultMetadata: {
                        summary: toolResult,
                        full_result: toolResult,
                        status: 'completed',
                        elapsed_ms: elapsedMs,
                      },
                    },
                  }
                : msg
            ),
          }
        })
      }

      // updateToolError mirrors updateToolResult: walks backwards through messages to
      // find the last tool_execution row and immutably attaches the ErrorEvent to it.
      // Called only for retryable=true errors per D-10.
      const updateToolError = (errorEvent: ErrorEvent) => {
        setSession(submitSessionId, (prev) => {
          let lastToolIndex = -1
          for (let i = prev.messages.length - 1; i >= 0; i--) {
            if (prev.messages[i].role === 'tool_execution') {
              lastToolIndex = i
              break
            }
          }
          if (lastToolIndex === -1) {
            // No tool_execution to attach to — fall back to a toast so the error is
            // not silently swallowed (belt-and-suspenders guard; unlikely in practice).
            toaster.create({ title: errorEvent.message, type: 'error', duration: 5000 })
            return prev
          }
          return {
            ...prev,
            messages: prev.messages.map((msg, i) =>
              i === lastToolIndex && msg.toolExecution
                ? {
                    ...msg,
                    toolExecution: {
                      ...msg.toolExecution,
                      errorEvent,
                    },
                  }
                : msg
            ),
          }
        })
      }

      // handleStreamEvent is the single switch dispatcher for SSE events.
      // Extracted so retryLastTool can reuse the exact same routing logic
      // without duplicating the branch tree.
      const handleStreamEvent = (event: ChatStreamEvent) => {
        // `done` is not in the ChatStreamEvent union; the backend may still emit it
        // as a stream-end signal. Skip it safely via a cast so the union remains
        // exhaustive for all declared members.
        if ((event.type as string) === 'done') return

        switch (event.type) {
          case 'content':
            markFirstChunk()
            if (event.chunk) appendContentChunk(event.chunk)
            isStreamingAssistant = true
            break

          case 'thinking':
            markFirstChunk()
            if (event.chunk) appendThinkingChunk(event.chunk)
            isStreamingThinking = true
            break

          case 'tool_call':
            markFirstChunk()
            appendToolCall(event.tool_name, event.tool_args ?? {})
            break

          case 'tool_result':
            updateToolResult(event.tool_result ?? '', event.elapsed_ms ?? 0)
            // Allow a fresh assistant bubble for the post-tool response.
            isStreamingAssistant = false
            // Reset thinking flag so a new ThinkingCard is opened if the LLM
            // reasons again after the tool result (double-think fix).
            isStreamingThinking = false
            break

          case 'error':
            if (event.retryable) {
              // retryable=true (D-10): attach ErrorEvent to the last tool_execution
              // row so ToolExecutionCard can render the inline error + Retry button.
              updateToolError(event)
              // Mark hasError so the Sidebar can show a "!" indicator if the user
              // navigated away before seeing the inline error state.
              setSession(submitSessionId, (prev) => ({ ...prev, hasError: true }))
            } else {
              // retryable=false (D-10): surface as a toast so the chat stays usable.
              toaster.create({ title: event.message, type: 'error', duration: 5000})
              setSession(submitSessionId, (prev) => ({ ...prev, hasError: true }))

              if (event.error_code === 'session_error') {
                // D-12: session_error is always non-retryable. After toasting, silently
                // re-create the session so the next user message has a valid session_id.
                // Re-read provider_settings so any recent api_key / base_url edits are
                // picked up — same pattern as handleProviderChange.
                const settings = loadProviderSettings() ?? DEFAULT_PROVIDER_SETTINGS
                const merged: ProviderSettings = {
                  ...settings,
                  selected: {
                    provider: currentProvider as ProviderSettings['selected']['provider'],
                    model: currentModel,
                  },
                }
                const selection = resolveSelection(merged)
                void initSession(
                  selection.provider,
                  selection.model,
                  selection.baseUrl,
                  selection.apiKey
                )
              }
            }
            break

          default: {
            // TypeScript exhaustiveness guard: if a new event type is added to the
            // ChatStreamEvent union without a matching case, the compile will fail here.
            const _exhaustive: never = event
            void _exhaustive
          }
        }
      }

      try {
        const response = await apiFetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session_id: submitSessionId }),
        })

        if (!response.ok) {
          throw new Error('Failed to get response')
        }

        if (!response.body) {
          throw new Error('No response body')
        }

        await readSSEStream(response.body, handleStreamEvent)
      } catch {
        setSession(submitSessionId, (prev) => ({
          ...prev,
          messages: [
            ...prev.messages,
            { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
          ],
        }))
      } finally {
        const wasAwayDuringStream = activeSessionIdRef.current !== submitSessionId
        setSession(submitSessionId, (prev) => ({
          ...prev,
          isStreaming: false,
          isAwaitingFirstChunk: false,
          // Mark unread when the user was looking at a different chat while
          // this stream completed. Cleared when the user navigates back.
          hasUnread: wasAwayDuringStream && !prev.hasError,
        }))
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessionId, currentProvider, currentModel, initSession]
  )

  // retryLastTool replays the last tool invocation via POST /api/chat/retry.
  // Re-uses the same readSSEStream + handleStreamEvent pipeline as sendMessage
  // so the tool card transitions through executing → completed/error exactly
  // as it would in a fresh message turn (D-09).
  const retryLastTool = useCallback(async () => {
    if (!sessionId) return
    if (getSessionSnapshot(sessionId).isStreaming) return

    const submitSessionId = sessionId

    setSession(submitSessionId, (prev) => {
      // Clear the error state on the last tool_execution message so the card
      // returns to the executing (blue spinner) state before re-streaming.
      let lastToolIndex = -1
      for (let i = prev.messages.length - 1; i >= 0; i--) {
        if (prev.messages[i].role === 'tool_execution') {
          lastToolIndex = i
          break
        }
      }
      const messages =
        lastToolIndex >= 0
          ? prev.messages.map((msg, i) =>
              i === lastToolIndex && msg.toolExecution
                ? { ...msg, toolExecution: { callMetadata: msg.toolExecution.callMetadata } }
                : msg
            )
          : prev.messages
      return {
        ...prev,
        messages,
        isStreaming: true,
        isAwaitingFirstChunk: true,
        hasError: false,
      }
    })

    // Track per-call stream state so retryLastTool doesn't bleed into the
    // outer sendMessage closures.
    let isStreamingAssistant = false
    let isStreamingThinking = false
    let firstChunkSeen = false

    const markFirstChunk = () => {
      if (firstChunkSeen) return
      firstChunkSeen = true
      setSession(submitSessionId, (prev) => ({ ...prev, isAwaitingFirstChunk: false }))
    }

    const appendThinkingChunk = (chunk: string) => {
      setSession(submitSessionId, (prev) => {
        if (!isStreamingThinking) {
          return {
            ...prev,
            messages: [...prev.messages, { role: 'thinking' as MessageType, content: chunk }],
          }
        }
        for (let i = prev.messages.length - 1; i >= 0; i--) {
          if (prev.messages[i].role === 'thinking') {
            return {
              ...prev,
              messages: prev.messages.map((msg, idx) =>
                idx === i ? { ...msg, content: msg.content + chunk } : msg
              ),
            }
          }
        }
        return prev
      })
    }

    const appendContentChunk = (chunk: string) => {
      setSession(submitSessionId, (prev) => {
        if (!isStreamingAssistant) {
          return {
            ...prev,
            messages: [...prev.messages, { role: 'assistant' as MessageType, content: chunk }],
          }
        }
        for (let i = prev.messages.length - 1; i >= 0; i--) {
          if (prev.messages[i].role === 'assistant') {
            return {
              ...prev,
              messages: prev.messages.map((msg, idx) =>
                idx === i ? { ...msg, content: msg.content + chunk } : msg
              ),
            }
          }
        }
        return prev
      })
    }

    const appendToolCall = (toolName: string, toolArgs: Record<string, unknown>) => {
      setSession(submitSessionId, (prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          {
            role: 'tool_execution' as MessageType,
            content: '',
            toolExecution: {
              callMetadata: {
                tool_name: toolName,
                arguments: toolArgs,
                started_at: Date.now(),
                status: 'executing',
              },
            },
          },
        ],
      }))
    }

    const updateToolResult = (toolResult: string, elapsedMs: number) => {
      setSession(submitSessionId, (prev) => {
        let lastToolIndex = -1
        for (let i = prev.messages.length - 1; i >= 0; i--) {
          if (prev.messages[i].role === 'tool_execution') {
            lastToolIndex = i
            break
          }
        }
        if (lastToolIndex === -1) return prev
        return {
          ...prev,
          messages: prev.messages.map((msg, i) =>
            i === lastToolIndex && msg.toolExecution
              ? {
                  ...msg,
                  toolExecution: {
                    ...msg.toolExecution,
                    resultMetadata: {
                      summary: toolResult,
                      full_result: toolResult,
                      status: 'completed',
                      elapsed_ms: elapsedMs,
                    },
                  },
                }
              : msg
          ),
        }
      })
    }

    const updateToolError = (errorEvent: ErrorEvent) => {
      setSession(submitSessionId, (prev) => {
        let lastToolIndex = -1
        for (let i = prev.messages.length - 1; i >= 0; i--) {
          if (prev.messages[i].role === 'tool_execution') {
            lastToolIndex = i
            break
          }
        }
        if (lastToolIndex === -1) {
          toaster.create({ title: errorEvent.message, type: 'error', duration: 5000 })
          return prev
        }
        return {
          ...prev,
          messages: prev.messages.map((msg, i) =>
            i === lastToolIndex && msg.toolExecution
              ? {
                  ...msg,
                  toolExecution: {
                    ...msg.toolExecution,
                    errorEvent,
                  },
                }
              : msg
          ),
        }
      })
    }

    const handleStreamEvent = (event: ChatStreamEvent) => {
      if ((event.type as string) === 'done') return

      switch (event.type) {
        case 'content':
          markFirstChunk()
          if (event.chunk) appendContentChunk(event.chunk)
          isStreamingAssistant = true
          break

        case 'thinking':
          markFirstChunk()
          if (event.chunk) appendThinkingChunk(event.chunk)
          isStreamingThinking = true
          break

        case 'tool_call':
          markFirstChunk()
          appendToolCall(event.tool_name, event.tool_args ?? {})
          break

        case 'tool_result':
          updateToolResult(event.tool_result ?? '', event.elapsed_ms ?? 0)
          isStreamingAssistant = false
          // Reset thinking flag so a new ThinkingCard is opened if the LLM
          // reasons again after the tool result (double-think fix).
          isStreamingThinking = false
          break

        case 'error':
          if (event.retryable) {
            updateToolError(event)
          } else {
            toaster.create({ title: event.message, type: 'error', duration: 5000 })
            if (event.error_code === 'session_error') {
              const settings = loadProviderSettings() ?? DEFAULT_PROVIDER_SETTINGS
              const merged: ProviderSettings = {
                ...settings,
                selected: {
                  provider: currentProvider as ProviderSettings['selected']['provider'],
                  model: currentModel,
                },
              }
              const selection = resolveSelection(merged)
              void initSession(
                selection.provider,
                selection.model,
                selection.baseUrl,
                selection.apiKey
              )
            }
          }
          break

        default: {
          const _exhaustive: never = event
          void _exhaustive
        }
      }
    }

    try {
      const response = await apiFetch('/api/chat/retry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: submitSessionId }),
      })

      if (!response.ok || !response.body) {
        toaster.create({ title: 'Could not retry', type: 'error', duration: 5000 })
        return
      }

      await readSSEStream(response.body, handleStreamEvent)
    } catch {
      toaster.create({ title: 'Could not retry', type: 'error', duration: 5000 })
    } finally {
      setSession(submitSessionId, (prev) => ({
        ...prev,
        isStreaming: false,
        isAwaitingFirstChunk: false,
        hasError: false,
      }))
    }
  }, [sessionId, currentProvider, currentModel, initSession])

  return {
    messages,
    isLoading,
    isAwaitingFirstChunk,
    sessionId,
    currentProvider,
    currentModel,
    providerError,
    sendMessage,
    handleProviderChange,
    retryProvider,
    retryLastTool,
  }
}
