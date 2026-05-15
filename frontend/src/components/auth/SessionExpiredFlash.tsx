import { useEffect } from 'react'
import { Box, Flex, Text } from '@chakra-ui/react'
import { Clock } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

export function SessionExpiredFlash() {
  const [searchParams, setSearchParams] = useSearchParams()
  const isExpired = searchParams.get('flash') === 'session_expired'

  useEffect(() => {
    if (!isExpired) return
    const next = new URLSearchParams(searchParams)
    next.delete('flash')
    setSearchParams(next, { replace: true })
  }, [isExpired, searchParams, setSearchParams])

  if (!isExpired) return null

  return (
    <Box
      role="status"
      aria-live="polite"
      bg="danger.muted"
      borderWidth="1px"
      borderStyle="solid"
      borderColor="danger.solid"
      borderRadius="md"
      px="3"
      py="3"
      mb="5"
    >
      <Flex direction="row" gap="3" align="center">
        <Box color="danger.solid" lineHeight="0">
          <Clock size={16} />
        </Box>
        <Text fontSize="15px" color="fg.primary">
          Your session expired — sign in to continue.
        </Text>
      </Flex>
    </Box>
  )
}
