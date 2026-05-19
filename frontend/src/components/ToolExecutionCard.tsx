import { Box, Flex, Text, Spinner, Button, Collapsible, Code, Table } from '@chakra-ui/react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
// Import as ErrorEventData to avoid shadowing the global lib.dom.d.ts ErrorEvent.
import type { FlightSearchResultData, FlightResultData, ToolCallMetadata, ToolResultMetadata, ErrorEvent as ErrorEventData } from '../types/chat'

interface ToolExecutionCardProps {
  callMetadata: ToolCallMetadata
  resultMetadata?: ToolResultMetadata
  /** True while the tool call is being executed (no result yet). Spinner shown. */
  isLoading?: boolean
  /** Populated on retryable=true ErrorEvent — renders error state + optional Retry button. */
  errorEvent?: ErrorEventData
  /** Called when the user clicks the Retry button. Only rendered when provided. */
  onRetry?: () => void
}

function isFlightSearchResult(value: unknown): value is FlightSearchResultData {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.status === 'string' &&
    Array.isArray(v.results) &&
    typeof v.count === 'number' &&
    typeof v.query === 'object' &&
    v.query !== null
  )
}

function FlightResultsTable({ data }: { data: FlightSearchResultData }) {
  const { query, results, count } = data

  return (
    <Box>
      <Box mb={2}>
        <Text fontSize="sm" color="gray.600">
          {query.origin} &rarr; {query.destination}, {query.departure_date},{' '}
          {query.passengers} passenger(s)
        </Text>
        <Text fontSize="sm" color="gray.600">
          {count} result(s)
        </Text>
      </Box>

      {results.length === 0 ? (
        <Text fontSize="sm" color="gray.600">
          No flights matched the search criteria.
        </Text>
      ) : (
        <Table.Root size="sm" variant="line">
          <Table.Header>
            <Table.Row>
              <Table.ColumnHeader>Route</Table.ColumnHeader>
              <Table.ColumnHeader>Departure</Table.ColumnHeader>
              <Table.ColumnHeader>Arrival</Table.ColumnHeader>
              <Table.ColumnHeader>Carrier</Table.ColumnHeader>
              <Table.ColumnHeader>Duration</Table.ColumnHeader>
              <Table.ColumnHeader>Price</Table.ColumnHeader>
              <Table.ColumnHeader>Class</Table.ColumnHeader>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {results.map((r: FlightResultData) => {
              const seg = r.segments[0]
              return (
                <Table.Row key={r.id}>
                  <Table.Cell>
                    {seg.departure.iata_code} &rarr; {seg.arrival.iata_code}
                  </Table.Cell>
                  <Table.Cell>{new Date(seg.departure.at).toLocaleTimeString()}</Table.Cell>
                  <Table.Cell>{new Date(seg.arrival.at).toLocaleTimeString()}</Table.Cell>
                  <Table.Cell>
                    {seg.carrier.name} ({seg.carrier.iata_code})
                  </Table.Cell>
                  <Table.Cell>{r.total_duration.replace('PT', '').toLowerCase()}</Table.Cell>
                  <Table.Cell>
                    {r.price.currency} {r.price.amount}
                  </Table.Cell>
                  <Table.Cell>{r.booking_class}</Table.Cell>
                </Table.Row>
              )
            })}
          </Table.Body>
        </Table.Root>
      )}
    </Box>
  )
}

export function ToolExecutionCard({
  callMetadata,
  resultMetadata,
  isLoading: _isLoading,
  errorEvent,
  onRetry,
}: ToolExecutionCardProps) {
  const [isArgsOpen, setIsArgsOpen] = useState(false)
  const [isResultOpen, setIsResultOpen] = useState(false)

  // Three-state derivation (executing → completed | error).
  const hasError = !!errorEvent
  // isComplete is only true when there is a result AND no error overrides it.
  const isComplete = !!resultMetadata && !hasError

  // Color token sets per state: red (error), green (complete), blue (executing).
  const bgColor = hasError ? 'red.50' : isComplete ? 'green.50' : 'blue.50'
  const borderColor = hasError ? 'red.200' : isComplete ? 'green.200' : 'blue.200'
  const textColor = hasError ? 'red.800' : isComplete ? 'green.800' : 'blue.800'
  const accentColor = hasError ? 'red' : isComplete ? 'green' : 'blue'

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
          {/* Exactly one icon per state */}
          {!isComplete && !hasError && <Spinner size="sm" color={`${accentColor}.500`} />}
          {isComplete && <Text fontSize="xl">✓</Text>}
          {hasError && <Text fontSize="xl">✗</Text>}
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

      {/* Error Section (only when hasError) */}
      {hasError && errorEvent && (
        <Box
          bg="red.50"
          rounded="md"
          borderWidth="1px"
          borderColor="red.200"
          p={2}
          mt={2}
        >
          <Text
            fontSize="sm"
            color="red.700"
            mb={onRetry ? 2 : 0}
          >
            {errorEvent.message}
          </Text>
          {onRetry && (
            <Button size="xs" colorScheme="red" variant="outline" onClick={onRetry}>
              Retry
            </Button>
          )}
        </Box>
      )}

      {/* Result Section (only when complete and no error) */}
      {!hasError && isComplete && resultMetadata && (
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
                {(() => {
                  try {
                    const parsed: unknown = JSON.parse(resultMetadata.full_result)
                    if (isFlightSearchResult(parsed)) {
                      return <FlightResultsTable data={parsed} />
                    }
                  } catch {
                    // Fall through to ReactMarkdown for non-JSON content
                  }
                  return (
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
                  )
                })()}
              </Box>
            </Collapsible.Content>
          </Collapsible.Root>
        </>
      )}
    </Box>
  )
}
