import { Box, Button, Flex, Input, Menu, Portal, Stack, Text } from '@chakra-ui/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, Cpu } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ToolExecutionCard } from './ToolExecutionCard'
import { ThinkingCard } from './ThinkingCard'
import { SelectorErrorBanner } from './chat/SelectorErrorBanner'
import { useChat } from '../hooks/useChat'
import { apiFetch } from '../lib/auth'

interface QuickSwitchOption {
  provider: string
  model: string
  label: string
}

// Discriminated union published by Plan 06-05a (REQ-p5-provider-info-split):
// local entries carry a required `base_url`; cloud entries carry only
// `api_key_configured: boolean` (api_key never crosses the wire — D-09).
// Switch on `entry.type` to narrow safely. ChatInterface only consumes the
// ollama models list; the rest of the discriminated payload is forwarded
// unmodified to the buildQuickSwitchOptions reader below.
interface LocalProviderInfo {
  type: 'local'
  available: boolean
  models: string[]
  base_url: string
}

interface CloudProviderInfo {
  type: 'cloud'
  available: boolean
  models: string[]
  api_key_configured: boolean
}

type ProviderInfoResponse = LocalProviderInfo | CloudProviderInfo
type ProvidersResponse = Record<string, ProviderInfoResponse>

function isProviderInfoResponse(value: unknown): value is ProviderInfoResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (!Array.isArray(v.models)) return false
  if (typeof v.available !== 'boolean') return false
  if (v.type === 'local') return typeof v.base_url === 'string'
  if (v.type === 'cloud') return typeof v.api_key_configured === 'boolean'
  return false
}

function isProvidersResponse(value: unknown): value is ProvidersResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  const ollama = v.ollama
  return isProviderInfoResponse(ollama)
}

/**
 * Project provider_settings + the live discovery list from GET /api/providers
 * into a flat {provider, model} list the active-model badge popover renders.
 *
 * For Ollama, every discovered model becomes its own row. If discovery hasn't
 * run yet (cold first load before /api/providers resolves), fall back to the
 * saved default so the popover always has at least one row.
 *
 * For OpenAI / Anthropic, configured providers get a single row built from
 * the saved {api_key, model}. Plan 08 doesn't render their settings cards;
 * the lib layer still drives them and useChat sends their api_key when the
 * user has saved one out-of-band, so we honor that here.
 */
function buildQuickSwitchOptions(
  liveOllamaModels: string[] | null
): QuickSwitchOption[] {
  let parsed: {
    ollama?: { base_url?: string; models?: string[] }
    lmstudio?: { base_url?: string; models?: string[] }
    openai?: { api_key?: string; model?: string }
    anthropic?: { api_key?: string; model?: string }
  } = {}
  try {
    const raw = localStorage.getItem('provider_settings')
    if (raw) parsed = JSON.parse(raw)
  } catch {
    // Corrupt JSON — treat as empty.
  }

  const opts: QuickSwitchOption[] = []

  // Ollama: prefer the live discovery list when it has loaded; otherwise fall
  // back to whatever the user-saved settings record carries.
  const ollamaBaseUrl = parsed.ollama?.base_url?.trim() ?? ''
  const ollamaModels =
    liveOllamaModels !== null && liveOllamaModels.length > 0
      ? liveOllamaModels
      : (parsed.ollama?.models ?? [])
  // Show Ollama rows whenever a base_url is configured OR the live discovery
  // returned models — covers the cold-run case where localStorage is empty
  // but the daemon is reachable through the backend default.
  if (ollamaBaseUrl.length > 0 || ollamaModels.length > 0) {
    if (ollamaModels.length === 0) {
      opts.push({ provider: 'ollama', model: 'qwen3:4b', label: 'ollama · qwen3:4b' })
    } else {
      for (const m of ollamaModels) {
        opts.push({ provider: 'ollama', model: m, label: `ollama · ${m}` })
      }
    }
  }

  // LM Studio: show all saved models when a base_url is configured.
  const lmstudioBaseUrl = parsed.lmstudio?.base_url?.trim() ?? ''
  const lmstudioModels = parsed.lmstudio?.models ?? []
  if (lmstudioBaseUrl.length > 0 || lmstudioModels.length > 0) {
    if (lmstudioModels.length === 0) {
      opts.push({ provider: 'lmstudio', model: '', label: 'lmstudio · (no models)' })
    } else {
      for (const m of lmstudioModels) {
        opts.push({ provider: 'lmstudio', model: m, label: `lmstudio · ${m}` })
      }
    }
  }

  if (parsed.openai?.api_key && parsed.openai.api_key.trim().length > 0) {
    const m = parsed.openai.model ?? 'gpt-4o-mini'
    opts.push({ provider: 'openai', model: m, label: `openai · ${m}` })
  }
  if (parsed.anthropic?.api_key && parsed.anthropic.api_key.trim().length > 0) {
    const m = parsed.anthropic.model ?? 'claude-3-5-sonnet-20241022'
    opts.push({ provider: 'anthropic', model: m, label: `anthropic · ${m}` })
  }
  return opts
}

export function ChatInterface() {
  const {
    messages,
    isLoading,
    isAwaitingFirstChunk,
    currentProvider,
    currentModel,
    providerError,
    sendMessage,
    handleProviderChange,
    retryProvider,
    retryLastTool,
  } = useChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [quickSwitchTick, setQuickSwitchTick] = useState(0)
  const [liveOllamaModels, setLiveOllamaModels] = useState<string[] | null>(null)

  // Discover the live Ollama model list on mount (lazy-discovery in the
  // backend means this triggers a one-shot daemon probe on first call) so the
  // active-model popover lists every installed model — not just whichever
  // single model the saved settings happened to remember. Falls back silently
  // if the call fails; the popover still renders from saved settings.
  useEffect(() => {
    let cancelled = false
    apiFetch('/api/providers')
      .then((response) => {
        if (cancelled || !response.ok) return null
        return response.json() as Promise<unknown>
      })
      .then((payload) => {
        if (cancelled || !payload || !isProvidersResponse(payload)) return
        setLiveOllamaModels(payload.ollama.models)
      })
      .catch(() => {
        // apiFetch handles 401; everything else is non-fatal here.
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Re-read saved settings every time the badge is opened so the list reflects
  // edits the user just made on /settings/providers without a remount. The
  // live discovery list is mixed in too — once it has loaded it's the source
  // of truth for Ollama's row set.
  const quickSwitchOptions = useMemo(
    () => buildQuickSwitchOptions(liveOllamaModels),
    [liveOllamaModels, quickSwitchTick]
  )

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const inputEl = form.elements.namedItem('message') as HTMLInputElement
    const text = inputEl.value.trim()
    if (!text) return
    inputEl.value = ''
    void sendMessage(text)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const text = e.currentTarget.value.trim()
      if (!text) return
      e.currentTarget.value = ''
      void sendMessage(text)
    }
  }

  return (
    <Flex direction="column" h="100vh" bg="bg.canvas">
      {/* Header */}
      <Box bg="bg.surface" borderBottom="1px" borderColor="border.subtle" p={4}>
        <Flex justify="space-between" align="center" mb={2}>
          <Box>
            <Text fontSize="xl" fontWeight="bold">
              Trip Planning Assistant
            </Text>
            <Text fontSize="sm" color="fg.secondary">
              Ask me anything about planning your trip!
            </Text>
          </Box>
          <Flex align="center" gap="2">
            {/* Active-model quick-switcher. The badge opens a popover listing
                providers the user has already configured (Ready in saved
                settings). Selecting one switches without leaving the chat —
                handleProviderChange re-reads provider_settings under the
                hood (Plan 07) so the api_key/base_url for the picked
                provider is what travels on the next session. The gear icon
                to the right is the only path to the full settings page. */}
            <Menu.Root
              onOpenChange={(details) => {
                if (details.open) setQuickSwitchTick((t) => t + 1)
              }}
              onSelect={(details) => {
                if (details.value === '__settings__') return
                const [provider, ...modelParts] = details.value.split('::')
                const model = modelParts.join('::')
                if (!provider || !model) return
                handleProviderChange(provider, model)
              }}
            >
              <Menu.Trigger asChild>
                <Box
                  as="button"
                  bg="bg.canvas"
                  borderWidth="1px"
                  borderColor="border.subtle"
                  borderRadius="full"
                  px="3"
                  py="1"
                  fontSize="13px"
                  color="fg.secondary"
                  display="inline-flex"
                  alignItems="center"
                  gap="2"
                  cursor="pointer"
                  title={`This conversation is using ${currentProvider} · ${currentModel}. Click to switch.`}
                >
                  <Cpu size={14} />
                  {currentProvider} · {currentModel}
                  <ChevronDown size={12} />
                </Box>
              </Menu.Trigger>
              <Portal>
                <Menu.Positioner>
                  <Menu.Content
                    bg="bg.surface"
                    borderWidth="1px"
                    borderColor="border.subtle"
                    borderRadius="md"
                    boxShadow="md"
                    p="1"
                    minW="240px"
                  >
                    {quickSwitchOptions.length > 0 ? (
                      quickSwitchOptions.map((opt) => {
                        const isActive =
                          opt.provider === currentProvider &&
                          opt.model === currentModel
                        return (
                          <Menu.Item
                            key={`${opt.provider}::${opt.model}`}
                            value={`${opt.provider}::${opt.model}`}
                            fontSize="14px"
                            px="3"
                            py="2"
                            borderRadius="sm"
                            color={isActive ? 'accent.solid' : 'fg.primary'}
                            fontWeight={isActive ? '500' : '400'}
                          >
                            {opt.label}
                            {isActive && (
                              <Box as="span" ml="2" fontSize="12px" color="fg.secondary">
                                · current
                              </Box>
                            )}
                          </Menu.Item>
                        )
                      })
                    ) : (
                      <Box px="3" py="2" fontSize="13px" color="fg.secondary">
                        No providers configured yet.
                      </Box>
                    )}
                    <Box height="1px" bg="border.subtle" my="1" />
                    <Menu.Item
                      value="__settings__"
                      fontSize="13px"
                      px="3"
                      py="2"
                      borderRadius="sm"
                      color="accent.solid"
                      asChild
                    >
                      <Link to="/settings/providers">Manage providers…</Link>
                    </Menu.Item>
                  </Menu.Content>
                </Menu.Positioner>
              </Portal>
            </Menu.Root>
            {/* Plan 08b: the standalone Settings IconButton was removed —
                the app-shell Sidebar is now the single nav surface. The
                "Manage providers…" entry inside the active-model popover
                remains as a secondary path to /settings/providers. */}
          </Flex>
        </Flex>
        <SelectorErrorBanner error={providerError} onRetry={retryProvider} />
      </Box>

      {/* Messages */}
      <Box flex={1} overflowY="auto" p={4}>
        <Stack gap={4} maxW="4xl" mx="auto">
          {messages.length === 0 ? (
            <Box textAlign="center" py={20}>
              <Text fontSize="lg" color="fg.secondary" mb={2}>
                Welcome! How can I help you plan your trip today?
              </Text>
              <Text fontSize="sm" color="fg.muted">
                Try asking about destinations, activities, or travel tips!
              </Text>
            </Box>
          ) : (
            messages.map((msg, idx) => {
              if (msg.role === 'assistant' && !msg.content.trim()) return null

              if (msg.role === 'tool_execution' && msg.toolExecution) {
                return (
                  <ToolExecutionCard
                    key={idx}
                    callMetadata={msg.toolExecution.callMetadata}
                    resultMetadata={msg.toolExecution.resultMetadata}
                    errorEvent={msg.toolExecution.errorEvent}
                    onRetry={
                      msg.toolExecution.errorEvent?.retryable ? retryLastTool : undefined
                    }
                  />
                )
              }

              if (msg.role === 'thinking' && msg.content) {
                return <ThinkingCard key={idx} content={msg.content} />
              }

              return (
                <Flex key={idx} justify={msg.role === 'user' ? 'flex-end' : 'flex-start'}>
                  <Box
                    bg={msg.role === 'user' ? 'accent.solid' : 'bg.surface'}
                    color={msg.role === 'user' ? 'white' : 'fg.primary'}
                    px={4}
                    py={3}
                    rounded="lg"
                    maxW="80%"
                    boxShadow="sm"
                    borderWidth={msg.role === 'assistant' ? '1px' : '0'}
                    borderColor="border.subtle"
                  >
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: ({ children }) => (
                            <Box as="table" w="full" my={2} borderWidth="1px" borderColor="border.subtle">
                              {children}
                            </Box>
                          ),
                          thead: ({ children }) => <Box as="thead" bg="bg.canvas">{children}</Box>,
                          th: ({ children }) => (
                            <Box as="th" px={3} py={2} borderWidth="1px" borderColor="border.subtle" fontWeight="semibold" textAlign="left">
                              {children}
                            </Box>
                          ),
                          td: ({ children }) => (
                            <Box as="td" px={3} py={2} borderWidth="1px" borderColor="border.subtle">
                              {children}
                            </Box>
                          ),
                          p: ({ children }) => <Text mb={2}>{children}</Text>,
                          ul: ({ children }) => <Box as="ul" pl={5} my={2}>{children}</Box>,
                          ol: ({ children }) => <Box as="ol" pl={5} my={2}>{children}</Box>,
                          li: ({ children }) => <Text as="li" mb={1}>{children}</Text>,
                          code: ({ children }) => (
                            <Box as="code" bg="bg.canvas" px={1} rounded="sm" fontFamily="mono" fontSize="sm">
                              {children}
                            </Box>
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    ) : (
                      <Text whiteSpace="pre-wrap">{msg.content}</Text>
                    )}
                  </Box>
                </Flex>
              )
            })
          )}
          {isAwaitingFirstChunk && (
            <Flex justify="flex-start">
              <Box bg="bg.surface" px={4} py={3} rounded="lg" borderWidth="1px" borderColor="border.subtle">
                <Text color="fg.secondary">Thinking...</Text>
              </Box>
            </Flex>
          )}
          <div ref={messagesEndRef} />
        </Stack>
      </Box>

      {/* Input */}
      <Box bg="bg.surface" borderTop="1px" borderColor="border.subtle" p={4}>
        <form onSubmit={handleSubmit}>
          <Flex gap={2} maxW="4xl" mx="auto">
            <Input
              name="message"
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              size="lg"
              disabled={isLoading}
              bg="bg.surface"
            />
            <Button
              type="submit"
              colorPalette="accent"
              size="lg"
              loading={isLoading}
              disabled={isLoading}
            >
              Send
            </Button>
          </Flex>
        </form>
      </Box>
    </Flex>
  )
}
