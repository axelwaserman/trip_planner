import { useCallback, useEffect, useState } from 'react'
import type { Message, MessageType } from '../types/chat'
import { apiFetch } from '../lib/auth'
import {
  mapProbeError,
  type BackendProbeError,
  type ProviderErrorView,
} from '../lib/providerErrors'
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
  model: string
): Promise<CreateSessionResult> {
  const response = await apiFetch('/api/chat/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
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

  const initSession = useCallback(async (provider: string, model: string) => {
    setProviderError(null)
    setCurrentProvider(provider)
    setCurrentModel(model)

    try {
      const result = await createSession(provider, model)

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
  }, [])

  useEffect(() => {
    const saved = localStorage.getItem('llm_provider_config')
    if (saved) {
      const { provider, model } = JSON.parse(saved) as { provider: string; model: string }
      void initSession(provider, model)
    } else {
      void initSession('ollama', 'qwen3:4b')
    }
  }, [initSession])

  const handleProviderChange = useCallback(
    (provider: string, model: string) => {
      setMessages([])
      setProviderError(null)
      void initSession(provider, model)
    },
    [initSession]
  )

  const retryProvider = useCallback(() => {
    setProviderError(null)
    void initSession(currentProvider, currentModel)
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
