import { Box, Flex, Text, Badge, Collapsible, Button } from '@chakra-ui/react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface ToolResultMetadata {
  summary: string
  full_result: string
  status: string
  elapsed_ms: number
}

interface ToolResultCardProps {
  metadata: ToolResultMetadata
}

export function ToolResultCard({ metadata }: ToolResultCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(metadata.full_result)
  }

  return (
    <Box
      bg="green.50"
      borderWidth="1px"
      borderColor="green.200"
      rounded="lg"
      p={3}
      my={2}
      maxW="80%"
    >
      {/* Header */}
      <Flex align="center" justify="space-between" mb={2}>
        <Flex align="center" gap={2}>
          <Text fontSize="xl">✓</Text>
          <Text fontWeight="semibold" color="green.800">
            Result
          </Text>
          <Badge colorScheme="green" size="sm">
            {metadata.status}
          </Badge>
          <Text fontSize="xs" color="gray.600">
            {metadata.elapsed_ms}ms
          </Text>
        </Flex>
        <Button size="xs" onClick={handleCopy} colorScheme="green" variant="ghost">
          Copy
        </Button>
      </Flex>

      {/* Summary Preview */}
      {!isExpanded && (
        <Text fontSize="sm" color="gray.700" mb={2}>
          {metadata.summary}
        </Text>
      )}

      {/* Expandable Full Result */}
      <Collapsible.Root open={isExpanded} onOpenChange={(e) => setIsExpanded(e.open)}>
        <Collapsible.Trigger asChild>
          <Box
            as="button"
            fontSize="sm"
            color="green.600"
            _hover={{ color: 'green.700', textDecoration: 'underline' }}
            cursor="pointer"
          >
            {isExpanded ? '▼' : '▶'} {isExpanded ? 'Hide' : 'Show'} full results
          </Box>
        </Collapsible.Trigger>
        <Collapsible.Content>
          <Box
            mt={2}
            p={3}
            bg="white"
            rounded="md"
            borderWidth="1px"
            borderColor="green.100"
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
              {metadata.full_result}
            </ReactMarkdown>
          </Box>
        </Collapsible.Content>
      </Collapsible.Root>
    </Box>
  )
}
