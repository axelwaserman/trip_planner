import { useEffect, useState } from 'react'
import { Box, Heading, Text, Stack, Spinner } from '@chakra-ui/react'

function App() {
  const [backendStatus, setBackendStatus] = useState<'loading' | 'healthy' | 'error'>('loading')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => {
        if (data.status === 'healthy') {
          setBackendStatus('healthy')
        } else {
          setBackendStatus('error')
        }
      })
      .catch(() => {
        setBackendStatus('error')
      })
  }, [])

  const getStatusDisplay = () => {
    switch (backendStatus) {
      case 'loading':
        return (
          <Text fontSize="sm" color="gray.500">
            <Spinner size="xs" mr={2} />
            Checking backend...
          </Text>
        )
      case 'healthy':
        return (
          <Text fontSize="sm" color="green.600">
            ✓ Backend connected
          </Text>
        )
      case 'error':
        return (
          <Text fontSize="sm" color="red.600">
            ✗ Backend not responding (is it running on :8000?)
          </Text>
        )
    }
  }

  return (
    <Box minH="100vh" bg="gray.50">
      <Stack gap={8} py={20} align="center">
        <Heading size="2xl">Trip Planner</Heading>
        <Text fontSize="lg" color="gray.600">
          AI-powered trip planning assistant
        </Text>
        {getStatusDisplay()}
      </Stack>
    </Box>
  )
}

export default App
