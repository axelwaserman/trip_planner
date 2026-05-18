/**
 * Sidebar — the app-shell navigation column for /app and /settings/providers.
 *
 * Layout (UI-SPEC §"Sidebar (new)"):
 *   - Logo + "Trip Planner" wordmark.
 *   - "+ New chat" full-width primary button.
 *   - RECENT CHATS eyebrow + chat list (one row per session).
 *   - Helper text: `Sessions reset when the server restarts.` (D-22 honest framing).
 *   - Settings nav link with a 3px accent left-border when active.
 *   - User pill (re-uses UserMenu verbatim).
 *
 * Sessions come from `useSessions()` which calls GET /api/chat/sessions
 * (per-user filtered server-side, Plan 06b output).
 *
 * Active-session highlight: 3px `accent.solid` left border on the matching
 * chat item — the indicator the UI-SPEC §"Color" reserved-for list dedicates
 * to active list items (item 3).
 *
 * Mobile (base breakpoint): the Sidebar is rendered inside a hand-rolled
 * fixed overlay by AppShell, gated by an `isOpen` prop. Desktop (lg): a
 * 260px persistent column.
 */

import { Box, Button, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { MessageSquarePlus, Settings as SettingsIcon } from 'lucide-react'
import { useSessions } from '../hooks/useSessions'
import { UserMenu } from './chat/UserMenu'

export interface SidebarProps {
  username?: string
  activeSessionId?: string
  onNewChat?: () => void
  onNavigate?: () => void
}

export function Sidebar({
  username,
  activeSessionId,
  onNewChat,
  onNavigate,
}: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { sessions, error } = useSessions()

  const settingsActive = location.pathname === '/settings/providers'

  function handleNewChat() {
    if (onNewChat) {
      onNewChat()
    }
    if (onNavigate) onNavigate()
    // Bump `?n=<token>` so useChat's effect re-runs and creates a fresh
    // session. Plain `navigate('/app')` was a no-op when already on /app —
    // useChat only initialises once per mount, so the messages list and
    // session_id stuck around. The token's value is irrelevant; it just
    // has to differ from whatever's currently in the URL.
    navigate(`/app?n=${Date.now()}`)
  }

  function handleSessionClick(id: string) {
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

        {sessions.length === 0 ? (
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
            {sessions.map((s) => {
              const isActive = activeSessionId === s.session_id
              const preview =
                s.first_message_preview && s.first_message_preview.trim().length > 0
                  ? s.first_message_preview
                  : 'New chat'
              return (
                <Box
                  key={s.session_id}
                  as="button"
                  onClick={() => handleSessionClick(s.session_id)}
                  h="48px"
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
                  <Text
                    fontSize="14px"
                    color="fg.primary"
                    overflow="hidden"
                    textOverflow="ellipsis"
                    whiteSpace="nowrap"
                  >
                    {preview}
                  </Text>
                  <Text fontSize="13px" color="fg.muted" mt="0.5">
                    {s.provider} · {s.model}
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
