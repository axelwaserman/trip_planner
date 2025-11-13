import { Box, Text, Collapsible } from '@chakra-ui/react'
import { useState } from 'react'

interface ThinkingCardProps {
  content: string
}

export function ThinkingCard({ content }: ThinkingCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Show first 2 lines as preview
  const lines = content.split('\n')
  const preview = lines.slice(0, 2).join('\n')
  const hasMore = lines.length > 2

  return (
    <Box
      bg="purple.50"
      borderWidth="1px"
      borderColor="purple.200"
      borderLeftWidth="4px"
      rounded="lg"
      p={3}
      my={2}
      maxW="80%"
    >
      {/* Header */}
      <Text fontSize="sm" fontWeight="semibold" color="purple.700" mb={1}>
        💭 Thinking...
      </Text>

      {/* Preview or Full Content */}
      {!isExpanded && hasMore ? (
        <Text fontSize="sm" color="gray.600" fontStyle="italic" mb={1}>
          {preview}
        </Text>
      ) : (
        <Text fontSize="sm" color="gray.600" fontStyle="italic" mb={1} whiteSpace="pre-wrap">
          {content}
        </Text>
      )}

      {/* Expand/Collapse */}
      {hasMore && (
        <Collapsible.Root open={isExpanded} onOpenChange={(e) => setIsExpanded(e.open)}>
          <Collapsible.Trigger asChild>
            <Box
              as="button"
              fontSize="xs"
              color="purple.600"
              _hover={{ color: 'purple.700', textDecoration: 'underline' }}
              cursor="pointer"
            >
              {isExpanded ? '▲ Show less' : '▼ Show more'}
            </Box>
          </Collapsible.Trigger>
        </Collapsible.Root>
      )}
    </Box>
  )
}
