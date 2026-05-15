import { Box, Button, Flex, Input, Stack, Text } from '@chakra-ui/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ToolExecutionCard } from './ToolExecutionCard'
import { ThinkingCard } from './ThinkingCard'
import { ProviderSelector } from './ProviderSelector'
import { UserMenu } from './chat/UserMenu'
import { useChat } from '../hooks/useChat'
import { apiFetch } from '../lib/auth'

export function ChatInterface() {
  const { messages, isLoading, currentProvider, currentModel, sendMessage, handleProviderChange } =
    useChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [username, setUsername] = useState<string>('')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/auth/me')
      .then((response) => {
        if (cancelled || !response.ok) return
        return response.json()
      })
      .then((payload: unknown) => {
        if (cancelled || !payload) return
        if (typeof payload === 'object' && payload !== null && 'username' in payload) {
          const value = (payload as { username: unknown }).username
          if (typeof value === 'string') setUsername(value)
        }
      })
      .catch(() => {
        // apiFetch already handles the 401 redirect; swallow other errors so the
        // header just renders without a username rather than breaking the chat.
      })
    return () => {
      cancelled = true
    }
  }, [])

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
    <Flex direction="column" h="100vh" bg="gray.50">
      {/* Header */}
      <Box bg="white" borderBottom="1px" borderColor="gray.200" p={4}>
        <Flex justify="space-between" align="center" mb={2}>
          <Box>
            <Text fontSize="xl" fontWeight="bold">
              Trip Planning Assistant
            </Text>
            <Text fontSize="sm" color="gray.600">
              Ask me anything about planning your trip!
            </Text>
          </Box>
          <Box>
            <ProviderSelector
              onProviderChange={handleProviderChange}
              initialProvider={currentProvider}
              initialModel={currentModel}
            />
          </Box>
        </Flex>
        <Flex justify="space-between" align="center">
          <Text fontSize="xs" color="gray.500">
            Using: {currentProvider} / {currentModel}
          </Text>
          {username && <UserMenu username={username} />}
        </Flex>
      </Box>

      {/* Messages */}
      <Box flex={1} overflowY="auto" p={4}>
        <Stack gap={4} maxW="4xl" mx="auto">
          {messages.length === 0 ? (
            <Box textAlign="center" py={20}>
              <Text fontSize="lg" color="gray.500" mb={2}>
                Welcome! How can I help you plan your trip today?
              </Text>
              <Text fontSize="sm" color="gray.400">
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
                  />
                )
              }

              if (msg.role === 'thinking' && msg.content) {
                return <ThinkingCard key={idx} content={msg.content} />
              }

              return (
                <Flex key={idx} justify={msg.role === 'user' ? 'flex-end' : 'flex-start'}>
                  <Box
                    bg={msg.role === 'user' ? 'blue.500' : 'white'}
                    color={msg.role === 'user' ? 'white' : 'gray.800'}
                    px={4}
                    py={3}
                    rounded="lg"
                    maxW="80%"
                    boxShadow="sm"
                    borderWidth={msg.role === 'assistant' ? '1px' : '0'}
                    borderColor="gray.200"
                  >
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: ({ children }) => (
                            <Box as="table" w="full" my={2} borderWidth="1px" borderColor="gray.300">
                              {children}
                            </Box>
                          ),
                          thead: ({ children }) => <Box as="thead" bg="gray.50">{children}</Box>,
                          th: ({ children }) => (
                            <Box as="th" px={3} py={2} borderWidth="1px" borderColor="gray.300" fontWeight="semibold" textAlign="left">
                              {children}
                            </Box>
                          ),
                          td: ({ children }) => (
                            <Box as="td" px={3} py={2} borderWidth="1px" borderColor="gray.300">
                              {children}
                            </Box>
                          ),
                          p: ({ children }) => <Text mb={2}>{children}</Text>,
                          ul: ({ children }) => <Box as="ul" pl={5} my={2}>{children}</Box>,
                          ol: ({ children }) => <Box as="ol" pl={5} my={2}>{children}</Box>,
                          li: ({ children }) => <Text as="li" mb={1}>{children}</Text>,
                          code: ({ children }) => (
                            <Box as="code" bg="gray.100" px={1} rounded="sm" fontFamily="mono" fontSize="sm">
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
          {isLoading && (
            <Flex justify="flex-start">
              <Box bg="white" px={4} py={3} rounded="lg" borderWidth="1px" borderColor="gray.200">
                <Text color="gray.500">Thinking...</Text>
              </Box>
            </Flex>
          )}
          <div ref={messagesEndRef} />
        </Stack>
      </Box>

      {/* Input */}
      <Box bg="white" borderTop="1px" borderColor="gray.200" p={4}>
        <form onSubmit={handleSubmit}>
          <Flex gap={2} maxW="4xl" mx="auto">
            <Input
              name="message"
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              size="lg"
              disabled={isLoading}
              bg="white"
            />
            <Button
              type="submit"
              colorScheme="blue"
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
