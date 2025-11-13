import { Box, Button, Flex, Input, Stack, Text } from '@chakra-ui/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ToolCallCard } from './ToolCallCard'
import { ToolResultCard } from './ToolResultCard'

type MessageType = 'user' | 'assistant' | 'tool_call' | 'tool_result'

interface ToolCallMetadata {
  tool_name: string
  arguments: Record<string, unknown>
  started_at: number
  status: string
}

interface ToolResultMetadata {
  summary: string
  full_result: string
  status: string
  elapsed_ms: number
}

interface Message {
  role: MessageType
  content: string
  metadata?: ToolCallMetadata | ToolResultMetadata
}

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, isLoading])

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput('')
    setIsLoading(true)

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])

    try {
      console.log('Sending message:', userMessage)
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
        }),
      })

      console.log('Response status:', response.status)

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body')
      }

      let accumulatedContent = ''
      let currentAssistantIndex = -1

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'error') {
              throw new Error(data.error)
            }

            if (data.type === 'done') {
              // Stream complete
              setSessionId(data.session_id)
              break
            }

            if (data.type === 'content' && data.chunk) {
              // If we don't have an assistant message yet, create one
              if (currentAssistantIndex === -1) {
                setMessages((prev) => {
                  const newMessages = [...prev, { role: 'assistant' as MessageType, content: data.chunk }]
                  currentAssistantIndex = newMessages.length - 1
                  return newMessages
                })
                accumulatedContent = data.chunk
              } else {
                // Update existing assistant message
                accumulatedContent += data.chunk
                setMessages((prev) =>
                  prev.map((msg, idx) =>
                    idx === currentAssistantIndex
                      ? { ...msg, content: accumulatedContent }
                      : msg
                  )
                )
              }
              setSessionId(data.session_id)
            }

            if (data.type === 'tool_call' && data.metadata) {
              // Add tool_call message
              setMessages((prev) => [
                ...prev,
                { role: 'tool_call', content: '', metadata: data.metadata },
              ])
              setSessionId(data.session_id)
            }

            if (data.type === 'tool_result' && data.metadata) {
              // Add tool_result message
              setMessages((prev) => [
                ...prev,
                { role: 'tool_result', content: '', metadata: data.metadata },
              ])
              // Reset for next assistant response
              accumulatedContent = ''
              currentAssistantIndex = -1
              setSessionId(data.session_id)
            }
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    sendMessage()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <Flex direction="column" h="100vh" bg="gray.50">
      {/* Header */}
      <Box bg="white" borderBottom="1px" borderColor="gray.200" p={4}>
        <Text fontSize="xl" fontWeight="bold">
          Trip Planning Assistant
        </Text>
        <Text fontSize="sm" color="gray.600">
          Ask me anything about planning your trip!
        </Text>
      </Box>

      {/* Messages */}
      <Box flex={1} overflowY="auto" p={4}>
        <Stack gap={4} maxW="4xl" mx="auto">
          {messages.length === 0 ? (
            <Box textAlign="center" py={20}>
              <Text fontSize="lg" color="gray.500" mb={2}>
                👋 Welcome! How can I help you plan your trip today?
              </Text>
              <Text fontSize="sm" color="gray.400">
                Try asking about destinations, activities, or travel tips!
              </Text>
            </Box>
          ) : (
            messages.map((msg, idx) => {
              // Skip empty assistant messages
              if (msg.role === 'assistant' && !msg.content.trim()) {
                return null
              }

              // Tool messages render inline without flex wrapper
              if (msg.role === 'tool_call' && msg.metadata) {
                return <ToolCallCard key={idx} metadata={msg.metadata as ToolCallMetadata} />
              }
              if (msg.role === 'tool_result' && msg.metadata) {
                return <ToolResultCard key={idx} metadata={msg.metadata as ToolResultMetadata} />
              }

              // User and assistant messages
              return (
                <Flex
                  key={idx}
                  justify={msg.role === 'user' ? 'flex-end' : 'flex-start'}
                >
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
                        thead: ({ children }) => (
                          <Box as="thead" bg="gray.50">
                            {children}
                          </Box>
                        ),
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
              value={input}
              onChange={(e) => setInput(e.target.value)}
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
              disabled={!input.trim() || isLoading}
            >
              Send
            </Button>
          </Flex>
        </form>
      </Box>
    </Flex>
  )
}
