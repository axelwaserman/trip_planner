import { Box, Button, Flex, Input, Stack, Text } from '@chakra-ui/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

interface Message {
  role: 'user' | 'assistant'
  content: string
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
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput('')
    setIsLoading(true)

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to get response')
      }

      const data = await response.json()
      
      // Store session ID for conversation continuity
      setSessionId(data.session_id)
      
      // Add assistant response
      setMessages((prev) => [...prev, { role: 'assistant', content: data.response }])
    } catch (error) {
      console.error('Chat error:', error)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
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
            messages.map((msg, idx) => (
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
                  <Text whiteSpace="pre-wrap">{msg.content}</Text>
                </Box>
              </Flex>
            ))
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
