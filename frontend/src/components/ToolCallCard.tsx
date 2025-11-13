import { Box, Flex, Text, Spinner, Badge, Collapsible, Code } from '@chakra-ui/react'
import { useState } from 'react'

interface ToolCallMetadata {
  tool_name: string
  arguments: Record<string, unknown>
  started_at: number
  status: string
}

interface ToolCallCardProps {
  metadata: ToolCallMetadata
}

export function ToolCallCard({ metadata }: ToolCallCardProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Box
      bg="blue.50"
      borderWidth="1px"
      borderColor="blue.200"
      rounded="lg"
      p={3}
      my={2}
      maxW="80%"
    >
      {/* Header */}
      <Flex align="center" gap={2} mb={isOpen ? 2 : 0}>
        {metadata.status === 'running' && <Spinner size="sm" color="blue.500" />}
        {metadata.status === 'success' && <Text fontSize="xl">✓</Text>}
        <Text fontWeight="semibold" color="blue.800">
          {metadata.tool_name.replace(/_/g, ' ')}
        </Text>
        <Badge colorScheme="blue" size="sm">
          {metadata.status}
        </Badge>
      </Flex>

      {/* Expandable Arguments Section */}
      <Collapsible.Root open={isOpen} onOpenChange={(e) => setIsOpen(e.open)}>
        <Collapsible.Trigger asChild>
          <Box
            as="button"
            fontSize="sm"
            color="blue.600"
            _hover={{ color: 'blue.700', textDecoration: 'underline' }}
            cursor="pointer"
            mt={1}
          >
            {isOpen ? '▼' : '▶'} {isOpen ? 'Hide' : 'Show'} arguments
          </Box>
        </Collapsible.Trigger>
        <Collapsible.Content>
          <Box mt={2} p={2} bg="white" rounded="md" borderWidth="1px" borderColor="blue.100">
            <Code asChild>
              <pre style={{ margin: 0, fontSize: '0.875rem' }}>
                {JSON.stringify(metadata.arguments, null, 2)}
              </pre>
            </Code>
          </Box>
        </Collapsible.Content>
      </Collapsible.Root>
    </Box>
  )
}
