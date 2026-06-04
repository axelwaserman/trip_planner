/**
 * useConversations — fetches the per-user filtered conversation list from
 * GET /api/chat/conversations (Plan 06b output) for the app-shell Sidebar.
 *
 * The endpoint is auth-protected (uses apiFetch which carries the JWT) AND
 * server-side filtered to the authenticated user — the frontend trusts the
 * backend's `metadata.user_id` partition. A leak there is a Plan 06b bug, not
 * a UI bug.
 *
 * The hook does NOT auto-poll. Refetch fires when:
 *   - the hook mounts (initial load)
 *   - the consumer calls `refetch()` (e.g. after "+ New chat" or after
 *     returning to /app from /settings/providers)
 *
 * Errors are surfaced as a string the Sidebar renders as a single-line
 * `Couldn't load recent chats.` note under the empty-state copy.
 */

import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/auth'

export interface ChatConversation {
  // Backend wire shape (app/chat/models.py::ChatConversationInfo). The frontend
  // matches the backend names verbatim — no transform layer.
  conversation_id: string
  created_at: string
  provider: string
  model: string
  first_message_preview?: string | null
}

interface ConversationsResponse {
  conversations: ChatConversation[]
}

function isConversationsResponse(value: unknown): value is ConversationsResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return Array.isArray(v.conversations)
}

export interface UseConversationsResult {
  conversations: ChatConversation[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const FETCH_FAILED_MESSAGE = "Couldn't load recent chats."

export function useConversations(): UseConversationsResult {
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    setIsLoading(true)
    setError(null)
    apiFetch('/api/chat/conversations')
      .then(async (response) => {
        if (!response.ok) {
          setError(FETCH_FAILED_MESSAGE)
          setIsLoading(false)
          return
        }
        const body: unknown = await response.json()
        if (!isConversationsResponse(body)) {
          setError(FETCH_FAILED_MESSAGE)
          setIsLoading(false)
          return
        }
        // Deduplicate by conversation_id — guards against any transient double-send
        // during new-conversation creation races.
        const seen = new Set<string>()
        const unique = body.conversations.filter((c) => {
          if (seen.has(c.conversation_id)) return false
          seen.add(c.conversation_id)
          return true
        })
        setConversations(unique)
        setIsLoading(false)
      })
      .catch(() => {
        // apiFetch already handles 401 redirects; everything else is a
        // soft failure the Sidebar surfaces inline.
        setError(FETCH_FAILED_MESSAGE)
        setIsLoading(false)
      })
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { conversations, isLoading, error, refetch }
}
