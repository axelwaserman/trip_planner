import { Box, Flex, Text, Spinner, Button, Collapsible, Code } from '@chakra-ui/react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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

interface ToolExecutionCardProps {
  callMetadata: ToolCallMetadata
  resultMetadata?: ToolResultMetadata
}

export function ToolExecutionCard({ callMetadata, resultMetadata }: ToolExecutionCardProps) {
  const [isArgsOpen, setIsArgsOpen] = useState(false)
  const [isResultOpen, setIsResultOpen] = useState(false)

  const isComplete = !!resultMetadata
  const bgColor = isComplete ? 'green.50' : 'blue.50'
  const borderColor = isComplete ? 'green.200' : 'blue.200'
  const textColor = isComplete ? 'green.800' : 'blue.800'
  const accentColor = isComplete ? 'green' : 'blue'

  const handleCopy = async () => {
    if (resultMetadata) {
      await navigator.clipboard.writeText(resultMetadata.full_result)
    }
  }

  return (
    <Box
      bg={bgColor}
      borderWidth="1px"
      borderColor={borderColor}
      rounded="lg"
      p={3}
      my={2}
      maxW="80%"
    >
      {/* Header */}
      <Flex align="center" justify="space-between" mb={2}>
        <Flex align="center" gap={2}>
          {!isComplete && <Spinner size="sm" color={`${accentColor}.500`} />}
          {isComplete && <Text fontSize="xl">✓</Text>}
          <Text fontWeight="semibold" color={textColor}>
            {callMetadata.tool_name.replace(/_/g, ' ')}
          </Text>
          {isComplete && resultMetadata && (
            <Text fontSize="xs" color="gray.600">
              {resultMetadata.elapsed_ms}ms
            </Text>
          )}
        </Flex>
        {isComplete && (
          <Button size="xs" onClick={handleCopy} colorScheme={accentColor} variant="ghost">
            Copy
          </Button>
        )}
      </Flex>

      {/* Arguments Section */}
      <Collapsible.Root open={isArgsOpen} onOpenChange={(e) => setIsArgsOpen(e.open)}>
        <Collapsible.Trigger asChild>
          <Box
            as="button"
            fontSize="sm"
            color={`${accentColor}.600`}
            _hover={{ color: `${accentColor}.700`, textDecoration: 'underline' }}
            cursor="pointer"
            mb={1}
          >
            {isArgsOpen ? '▼' : '▶'} {isArgsOpen ? 'Hide' : 'Show'} arguments
          </Box>
        </Collapsible.Trigger>
        <Collapsible.Content>
          <Box mt={2} p={2} bg="white" rounded="md" borderWidth="1px" borderColor={`${accentColor}.100`}>
            <Code asChild>
              <pre style={{ margin: 0, fontSize: '0.875rem' }}>
                {JSON.stringify(callMetadata.arguments, null, 2)}
              </pre>
            </Code>
          </Box>
        </Collapsible.Content>
      </Collapsible.Root>

      {/* Result Section (only when complete) */}
      {isComplete && resultMetadata && (
        <>
          {/* Summary Preview */}
          {!isResultOpen && (
            <Text fontSize="sm" color="gray.700" mt={2} mb={1}>
              {resultMetadata.summary}
            </Text>
          )}

          {/* Expandable Full Result */}
          <Collapsible.Root open={isResultOpen} onOpenChange={(e) => setIsResultOpen(e.open)}>
            <Collapsible.Trigger asChild>
              <Box
                as="button"
                fontSize="sm"
                color={`${accentColor}.600`}
                _hover={{ color: `${accentColor}.700`, textDecoration: 'underline' }}
                cursor="pointer"
              >
                {isResultOpen ? '▼' : '▶'} {isResultOpen ? 'Hide' : 'Show'} full results
              </Box>
            </Collapsible.Trigger>
            <Collapsible.Content>
              <Box
                mt={2}
                p={3}
                bg="white"
                rounded="md"
                borderWidth="1px"
                borderColor={`${accentColor}.100`}
                maxH="400px"
                overflowY="auto"
              >
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
                      <Box
                        as="th"
                        px={3}
                        py={2}
                        borderWidth="1px"
                        borderColor="gray.300"
                        fontWeight="semibold"
                        textAlign="left"
                      >
                        {children}
                      </Box>
                    ),
                    td: ({ children }) => (
                      <Box as="td" px={3} py={2} borderWidth="1px" borderColor="gray.300">
                        {children}
                      </Box>
                    ),
                    p: ({ children }) => <Text mb={2}>{children}</Text>,
                    ul: ({ children }) => (
                      <Box as="ul" pl={5} my={2}>
                        {children}
                      </Box>
                    ),
                    ol: ({ children }) => (
                      <Box as="ol" pl={5} my={2}>
                        {children}
                      </Box>
                    ),
                    li: ({ children }) => (
                      <Text as="li" mb={1}>
                        {children}
                      </Text>
                    ),
                    code: ({ children }) => (
                      <Box
                        as="code"
                        bg="gray.100"
                        px={1}
                        rounded="sm"
                        fontFamily="mono"
                        fontSize="sm"
                      >
                        {children}
                      </Box>
                    ),
                  }}
                >
                  {resultMetadata.full_result}
                </ReactMarkdown>
              </Box>
            </Collapsible.Content>
          </Collapsible.Root>
        </>
      )}
    </Box>
  )
}
