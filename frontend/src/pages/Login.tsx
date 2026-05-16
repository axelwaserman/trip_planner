import { Box, Grid, GridItem, Heading, Text } from '@chakra-ui/react'
import { LoginForm } from '../components/auth/LoginForm'
import { SessionExpiredFlash } from '../components/auth/SessionExpiredFlash'

export function Login() {
  return (
    <Grid
      minH="100dvh"
      templateColumns={{ base: '1fr', lg: '1.4fr 1fr' }}
    >
      <GridItem
        bg="bg.canvas"
        px={{ base: '8', lg: '16' }}
        py={{ base: '12', lg: '16' }}
        display="flex"
        flexDirection="column"
        justifyContent="center"
      >
        <Box
          as="span"
          color="accent.solid"
          textTransform="uppercase"
          letterSpacing="0.04em"
          fontSize="13px"
          fontWeight="500"
          mb="6"
          display={{ base: 'none', lg: 'inline-block' }}
        >
          Welcome
        </Box>
        <Heading
          as="h1"
          fontFamily="display"
          fontSize={{
            base: 'clamp(40px, 6vw + 16px, 56px)',
            lg: 'clamp(64px, 4vw + 32px, 96px)',
          }}
          lineHeight="0.95"
          letterSpacing="-0.02em"
          color="fg.primary"
        >
          Conversations
          <br />
          that actually
          <br />
          go{' '}
          <Box
            as="span"
            textDecoration="underline"
            textDecorationColor="accent.solid"
            textUnderlineOffset="4px"
          >
            somewhere.
          </Box>
        </Heading>
        <Text
          mt="6"
          maxW="36ch"
          color="fg.secondary"
          fontSize="15px"
        >
          Trip Planner is a chat agent that calls real travel tools live —
          flights, prices, the works.
        </Text>
      </GridItem>

      <GridItem
        bg="bg.surface"
        borderLeft={{ base: 'none', lg: '1px solid' }}
        borderTop={{ base: '1px solid', lg: 'none' }}
        borderColor="border.subtle"
        px={{ base: '6', lg: '16' }}
        py={{ base: '10', lg: '16' }}
        display="flex"
        alignItems="center"
        justifyContent="center"
      >
        <Box w="100%" maxW="360px">
          <Heading
            id="signin-heading"
            as="h2"
            fontFamily="display"
            fontSize="32px"
            mb="8"
            color="fg.primary"
          >
            Sign in
          </Heading>
          <SessionExpiredFlash />
          <LoginForm />
        </Box>
      </GridItem>
    </Grid>
  )
}
