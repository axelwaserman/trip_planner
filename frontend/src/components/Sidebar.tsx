/**
 * Sidebar — the app-shell navigation column for /app and /settings/providers.
 *
 * Layout (UI-SPEC §"Sidebar (new)"):
 *   - Logo + "Trip Planner" wordmark.
 *   - "+ New chat" full-width primary button.
 *   - RECENT CHATS eyebrow + chat list (one row per conversation).
 *   - Helper text: `Sessions reset when the server restarts.` (D-22 honest framing).
 *   - Settings nav link with a 3px accent left-border when active.
 *   - User pill (re-uses UserMenu verbatim).
 *
 * Conversations come from `useConversations()` which calls
 * GET /api/chat/conversations (per-user filtered server-side, Plan 06b output).
 *
 * Active-conversation highlight: 3px `accent.solid` left border on the matching
 * chat item — the indicator the UI-SPEC §"Color" reserved-for list dedicates
 * to active list items (item 3).
 *
 * Mobile (base breakpoint): the Sidebar is rendered inside a hand-rolled
 * fixed overlay by AppShell, gated by an `isOpen` prop. Desktop (lg): a
 * 260px persistent column.
 *
 * The `?session=<id>` URL search-param key is preserved to keep bookmarked
 * chat links stable across the Phase 6 rename — the wire-level conversation
 * rename covers request bodies and SSE field names, not URL routing keys.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { Box, Button, Flex, Heading, Spinner, Stack, Text } from '@chakra-ui/react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { MessageSquarePlus, Settings as SettingsIcon } from 'lucide-react'
import {
  getStreamingConversationIds,
  getUnreadConversationIds,
  getErrorConversationIds,
  subscribe as subscribeToStore,
} from '../lib/chatConversationStore'
import { useConversations } from '../hooks/useConversations'
import { UserMenu } from './chat/UserMenu'

export interface SidebarProps {
  username?: string
  activeConversationId?: string
  onNewChat?: () => void
  onNavigate?: () => void
}

export function Sidebar({
  username,
  activeConversationId,
  onNewChat,
  onNavigate,
}: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { conversations, error, refetch } = useConversations()
  // Live "this row is generating" set, sourced from the same store useChat
  // writes to. Background streams (user switched away mid-response) keep
  // their flag on so the Sidebar dot stays visible until the stream ends.
  const streamingConversationIds = useSyncExternalStore(
    subscribeToStore,
    useCallback(() => getStreamingConversationIds(), [])
  )
  const unreadConversationIds = useSyncExternalStore(
    subscribeToStore,
    useCallback(() => getUnreadConversationIds(), [])
  )
  const errorConversationIds = useSyncExternalStore(
    subscribeToStore,
    useCallback(() => getErrorConversationIds(), [])
  )

  const settingsActive = location.pathname === '/settings/providers'

  // Track how many conversations were streaming on the previous render.
  // When the count drops (a stream finished), refetch so the sidebar
  // re-orders by latest message.
  const prevStreamingSizeRef = useRef(streamingConversationIds.size)
  useEffect(() => {
    const prev = prevStreamingSizeRef.current
    prevStreamingSizeRef.current = streamingConversationIds.size
    if (streamingConversationIds.size < prev) {
      refetch()
    }
  }, [streamingConversationIds, refetch])

  // Refetch the conversations list whenever the active conversation changes
  // — picks up new conversations useChat just created (it replaces the URL
  // with /app?session=<new_id> on success) and ensures the new row appears
  // alongside its highlight. Refetch is a no-op when activeConversationId is
  // still undefined.
  useEffect(() => {
    if (!activeConversationId) return
    if (conversations.some((c) => c.conversation_id === activeConversationId)) return
    refetch()
  }, [activeConversationId, conversations, refetch])

  function handleNewChat() {
    if (onNewChat) {
      onNewChat()
    }
    if (onNavigate) onNavigate()
    // Bump `?n=<token>` so useChat's effect re-runs and creates a fresh
    // conversation. Plain `navigate('/app')` was a no-op when already on /app
    // — useChat only initialises once per mount, so the messages list and
    // conversation_id stuck around. The token's value is irrelevant; it just
    // has to differ from whatever's currently in the URL.
    navigate(`/app?n=${Date.now()}`)
  }

  function handleConversationClick(id: string) {
    if (onNavigate) onNavigate()
    navigate(`/app?session=${id}`)
  }

  return (
    <Box
      as="aside"
      w={{ base: '280px', lg: '260px' }}
      bg="bg.surface"
      borderRightWidth="1px"
      borderRightColor="border.subtle"
      h="100dvh"
      display="flex"
      flexDirection="column"
    >
      {/* Logo block */}
      <Box p="6">
        <Heading
          as="h1"
          fontFamily="display"
          fontSize="18px"
          fontWeight="400"
          letterSpacing="-0.01em"
          color="fg.primary"
        >
          Trip Planner
        </Heading>
      </Box>

      <Box borderBottomWidth="1px" borderBottomColor="border.subtle" />

      {/* + New chat CTA */}
      <Box p="4">
        <Button
          colorPalette="accent"
          w="full"
          size="md"
          onClick={handleNewChat}
          type="button"
        >
          <MessageSquarePlus size={16} />
          <Box as="span" ml="2">
            New chat
          </Box>
        </Button>
      </Box>

      <Box borderBottomWidth="1px" borderBottomColor="border.subtle" />

      {/* RECENT CHATS list */}
      <Box flex="1" overflowY="auto">
        <Text
          textTransform="uppercase"
          letterSpacing="0.04em"
          fontSize="13px"
          fontWeight="500"
          color="fg.secondary"
          px="4"
          pt="4"
          pb="2"
        >
          RECENT CHATS
        </Text>

        {conversations.length === 0 ? (
          <Stack gap="1" px="4" py="2">
            <Text fontSize="13px" color="fg.muted">
              No chats yet. Start one below.
            </Text>
            {error && (
              <Text fontSize="13px" color="fg.muted">
                {error}
              </Text>
            )}
          </Stack>
        ) : (
          <Stack gap="0">
            {conversations.map((c) => {
              const isActive = activeConversationId === c.conversation_id
              const isStreaming = streamingConversationIds.has(c.conversation_id)
              const hasUnread = !isActive && unreadConversationIds.has(c.conversation_id)
              const hasError = !isActive && errorConversationIds.has(c.conversation_id)
              const preview =
                c.first_message_preview && c.first_message_preview.trim().length > 0
                  ? c.first_message_preview
                  : 'New chat'
              return (
                <Box
                  key={c.conversation_id}
                  as="button"
                  onClick={() => handleConversationClick(c.conversation_id)}
                  w="full"
                  h="48px"
                  overflow="hidden"
                  px="4"
                  display="flex"
                  flexDirection="column"
                  justifyContent="center"
                  textAlign="left"
                  borderLeftWidth="3px"
                  borderLeftColor={isActive ? 'accent.solid' : 'transparent'}
                  bg="transparent"
                  cursor="pointer"
                  _hover={{ bg: 'accent.muted' }}
                >
                  <Flex align="center" gap="2" minW="0">
                    {isStreaming && (
                      <Spinner
                        aria-label="Generating"
                        flexShrink="0"
                        size="xs"
                        color="accent.solid"
                      />
                    )}
                    <Text
                      fontSize="14px"
                      color="fg.primary"
                      overflow="hidden"
                      textOverflow="ellipsis"
                      whiteSpace="nowrap"
                      flex="1"
                    >
                      {preview}
                    </Text>
                    {hasError && (
                      <Text fontSize="12px" color="red.500" flexShrink="0" aria-label="Error">
                        !
                      </Text>
                    )}
                    {hasUnread && !hasError && (
                      <Box
                        as="span"
                        aria-label="Unread reply"
                        flexShrink="0"
                        w="6px"
                        h="6px"
                        borderRadius="full"
                        bg="accent.solid"
                      />
                    )}
                  </Flex>
                  <Text
                    fontSize="13px"
                    color="fg.muted"
                    mt="0.5"
                    overflow="hidden"
                    textOverflow="ellipsis"
                    whiteSpace="nowrap"
                  >
                    {`${c.provider} · ${c.model}`}
                  </Text>
                </Box>
              )
            })}
          </Stack>
        )}

        <Text fontSize="13px" color="fg.muted" px="4" py="3">
          Sessions reset when the server restarts.
        </Text>
      </Box>

      <Box borderBottomWidth="1px" borderBottomColor="border.subtle" />

      {/* Settings nav */}
      <Box>
        <Box
          as={Link}
          // @ts-expect-error react-router Link `to` prop on Box-as is fine at runtime
          to="/settings/providers"
          display="flex"
          alignItems="center"
          gap="3"
          h="48px"
          px="4"
          borderLeftWidth="3px"
          borderLeftColor={settingsActive ? 'accent.solid' : 'transparent'}
          color={settingsActive ? 'accent.solid' : 'fg.primary'}
          fontSize="14px"
          fontWeight={settingsActive ? '500' : '400'}
          _hover={{ bg: 'accent.muted' }}
          onClick={() => {
            if (onNavigate) onNavigate()
          }}
        >
          <SettingsIcon size={20} />
          <Box as="span">Settings</Box>
        </Box>
      </Box>

      <Box borderBottomWidth="1px" borderBottomColor="border.subtle" />

      {/* User pill — re-uses the existing UserMenu */}
      {username && (
        <Box p="4">
          <Flex justify="flex-start">
            <UserMenu username={username} />
          </Flex>
        </Box>
      )}
    </Box>
  )
}
