import { useCallback, useEffect, useState } from 'react'
import type { Message, MessageType } from '../types/chat'
import { apiFetch } from '../lib/auth'
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
import { readSSEStream } from './useSSEStream'

interface UseChatReturn {
  messages: Message[]
  isLoading: boolean
  sessionId: string | null
  currentProvider: string
  currentModel: string
  providerError: ProviderErrorView | null
  sendMessage: (text: string) => Promise<void>
  handleProviderChange: (provider: string, model: string) => void
  retryProvider: () => void
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
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [currentProvider, setCurrentProvider] = useState('ollama')
  const [currentModel, setCurrentModel] = useState('qwen3:4b')
  const [providerError, setProviderError] = useState<ProviderErrorView | null>(null)

  const initSession = useCallback(
    async (provider: string, model: string, baseUrl: string | null, apiKey: string | null) => {
      setProviderError(null)
      setCurrentProvider(provider)
      setCurrentModel(model)

      try {
        const result = await createSession(provider, model, baseUrl, apiKey)

        if (result.ok) {
          setSessionId(result.data.session_id)
          setCurrentProvider(result.data.provider)
          setCurrentModel(result.data.model)
          return
        }

        if (result.probeError) {
          setProviderError(result.probeError)
          return
        }

        setMessages([
          {
            role: 'assistant',
            content: '❌ Failed to initialize chat session. Please refresh the page.',
          },
        ])
      } catch {
        // apiFetch's 401 handler already redirected; nothing to do here.
      }
    },
    []
  )

  useEffect(() => {
    // D-21: read provider_settings (new key). If absent, one-shot migrate from
    // the legacy 'llm_provider_config' key (Phase 4.1/4.2). If neither exists
    // (cold first run), use ollama/qwen3:4b with null base_url + api_key so
    // the backend factory falls back to its env-var precedence (D-08).
    const settings = loadProviderSettings()
    if (settings === null) {
      void initSession('ollama', 'qwen3:4b', null, null)
      return
    }
    const selection = resolveSelection(settings)
    void initSession(selection.provider, selection.model, selection.baseUrl, selection.apiKey)
  }, [initSession])

  const handleProviderChange = useCallback(
    (provider: string, model: string) => {
      setMessages([])
      setProviderError(null)
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
    [initSession]
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
      if (!text.trim() || isLoading || !sessionId) return

      setIsLoading(true)
      setMessages((prev) => [...prev, { role: 'user', content: text }])

      try {
        const response = await apiFetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session_id: sessionId }),
        })

        if (!response.ok) {
          throw new Error('Failed to get response')
        }

        if (!response.body) {
          throw new Error('No response body')
        }

        // Track stream state outside React — these are only read/written during
        // the synchronous SSE event loop, before React flushes any batched updates.
        let isStreamingAssistant = false
        let isStreamingThinking = false

        await readSSEStream(response.body, (event) => {
          if (event.type === 'error') {
            throw new Error(event.error ?? 'Stream error')
          }

          if (event.type === 'done') {
            if (event.session_id) setSessionId(event.session_id)
            return
          }

          if (event.type === 'thinking' && event.chunk) {
            if (event.session_id) setSessionId(event.session_id)
            const chunk = event.chunk
            if (!isStreamingThinking) {
              isStreamingThinking = true
              setMessages((prev) => [...prev, { role: 'thinking' as MessageType, content: chunk }])
            } else {
              setMessages((prev) => {
                const lastIdx = prev.length - 1
                // Walk backwards to find the last thinking message
                for (let i = lastIdx; i >= 0; i--) {
                  if (prev[i].role === 'thinking') {
                    return prev.map((msg, idx) =>
                      idx === i ? { ...msg, content: msg.content + chunk } : msg
                    )
                  }
                }
                return prev
              })
            }
          }

          if (event.type === 'content' && event.chunk) {
            if (event.session_id) setSessionId(event.session_id)
            const chunk = event.chunk
            if (!isStreamingAssistant) {
              isStreamingAssistant = true
              setMessages((prev) => [...prev, { role: 'assistant' as MessageType, content: chunk }])
            } else {
              setMessages((prev) => {
                // Walk backwards to find the last assistant message
                for (let i = prev.length - 1; i >= 0; i--) {
                  if (prev[i].role === 'assistant') {
                    return prev.map((msg, idx) =>
                      idx === i ? { ...msg, content: msg.content + chunk } : msg
                    )
                  }
                }
                return prev
              })
            }
          }

          if (event.type === 'tool_call' && event.tool_name) {
            if (event.session_id) setSessionId(event.session_id)
            setMessages((prev) => [
              ...prev,
              {
                role: 'tool_execution' as MessageType,
                content: '',
                toolExecution: {
                  callMetadata: {
                    tool_name: event.tool_name!,
                    arguments: event.tool_args ?? {},
                    started_at: Date.now(),
                    status: 'executing',
                  },
                },
              },
            ])
          }

          if (event.type === 'tool_result' && event.tool_name) {
            if (event.session_id) setSessionId(event.session_id)
            setMessages((prev) => {
              let lastToolIndex = -1
              for (let i = prev.length - 1; i >= 0; i--) {
                if (prev[i].role === 'tool_execution') {
                  lastToolIndex = i
                  break
                }
              }

              if (lastToolIndex === -1) return prev

              return prev.map((msg, i) =>
                i === lastToolIndex && msg.toolExecution
                  ? {
                      ...msg,
                      toolExecution: {
                        ...msg.toolExecution,
                        resultMetadata: {
                          summary: event.tool_result ?? '',
                          full_result: event.tool_result ?? '',
                          status: 'completed',
                          elapsed_ms: event.elapsed_ms ?? 0,
                        },
                      },
                    }
                  : msg
              )
            })
            // Reset for the next assistant response after tool execution
            isStreamingAssistant = false
          }
        })
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
        ])
      } finally {
        setIsLoading(false)
      }
    },
    [isLoading, sessionId]
  )

  return {
    messages,
    isLoading,
    sessionId,
    currentProvider,
    currentModel,
    providerError,
    sendMessage,
    handleProviderChange,
    retryProvider,
  }
}
