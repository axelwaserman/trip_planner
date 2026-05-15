import { Box, Button, Flex, Text } from '@chakra-ui/react'
import { AlertCircle } from 'lucide-react'
import type { ProviderErrorView } from '../../lib/providerErrors'

interface SelectorErrorBannerProps {
  error: ProviderErrorView | null
  onRetry: () => void
}

export function SelectorErrorBanner({ error, onRetry }: SelectorErrorBannerProps) {
  if (!error) return null

  return (
    <Box
      role="status"
      aria-live="polite"
      bg="danger.muted"
      borderWidth="1px"
      borderStyle="solid"
      borderColor="danger.solid"
      borderRadius="md"
      px="4"
      py="3"
      mt="4"
    >
      <Flex direction="row" gap="3" align="center">
        <Box color="danger.solid" lineHeight="0" flexShrink={0}>
          <AlertCircle size={18} />
        </Box>
        <Box flex="1">
          <Text fontSize="15px" color="fg.primary">
            {error.message}
          </Text>
          {error.hint && (
            <Text fontSize="13px" color="fg.secondary" mt="1">
              {error.hint}
            </Text>
          )}
          {error.inlineCode.length > 0 && (
            <Flex gap="1" wrap="wrap" mt="1">
              {error.inlineCode.map((snippet) => (
                <Box
                  key={snippet}
                  as="code"
                  bg="bg.canvas"
                  borderWidth="1px"
                  borderStyle="solid"
                  borderColor="border.subtle"
                  borderRadius="sm"
                  px="1"
                  fontFamily="mono"
                  fontSize="13px"
                >
                  {snippet}
                </Box>
              ))}
            </Flex>
          )}
        </Box>
        <Button
          variant="ghost"
          size="sm"
          color="accent.solid"
          marginLeft="auto"
          onClick={onRetry}
        >
          Retry
        </Button>
      </Flex>
    </Box>
  )
}
