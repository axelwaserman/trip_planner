import { Box, Heading, Text, Stack } from '@chakra-ui/react'

function App() {
  return (
    <Box minH="100vh" bg="gray.50">
      <Stack gap={8} py={20} align="center">
        <Heading size="2xl">Trip Planner</Heading>
        <Text fontSize="lg" color="gray.600">
          AI-powered trip planning assistant
        </Text>
        <Text fontSize="sm" color="gray.500">
          Frontend ready! Backend health check: Coming soon...
        </Text>
      </Stack>
    </Box>
  )
}

export default App
