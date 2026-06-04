/**
 * Component tests for ToolExecutionCard structured renderer (REQ-tool-json-output).
 * Covers:
 *   - structured table render when full_result is valid FlightSearchResult JSON
 *   - empty results array fallback message
 *   - ReactMarkdown fallback for non-JSON full_result
 *   - ReactMarkdown fallback for JSON that lacks the FlightSearchResult shape
 *   - loading state (no resultMetadata)
 */

import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChakraProvider } from '@chakra-ui/react'
import type React from 'react'
import { system } from '../../theme'
import { ToolExecutionCard } from '../ToolExecutionCard'

function renderWithChakra(ui: React.ReactElement) {
  return render(<ChakraProvider value={system}>{ui}</ChakraProvider>)
}

const FLIGHT_RESULT_JSON = JSON.stringify({
  status: 'ok',
  query: {
    origin: 'LAX',
    destination: 'JFK',
    departure_date: '2026-06-15',
    passengers: 1,
  },
  results: [
    {
      id: 'fl-1',
      segments: [
        {
          id: 'seg-1',
          departure: {
            iata_code: 'LAX',
            city: 'LAX',
            terminal: null,
            at: '2026-06-15T08:00:00+00:00',
          },
          arrival: {
            iata_code: 'JFK',
            city: 'JFK',
            terminal: null,
            at: '2026-06-15T13:25:00+00:00',
          },
          carrier: { iata_code: 'DL', name: 'Delta Air Lines' },
          flight_number: 'DL412',
          duration: 'PT5H25M',
          number_of_stops: 0,
        },
      ],
      total_duration: 'PT5H25M',
      price: { amount: '450.50', currency: 'USD' },
      booking_class: 'ECONOMY',
    },
    {
      id: 'fl-2',
      segments: [
        {
          id: 'seg-2',
          departure: {
            iata_code: 'LAX',
            city: 'LAX',
            terminal: null,
            at: '2026-06-15T10:00:00+00:00',
          },
          arrival: {
            iata_code: 'JFK',
            city: 'JFK',
            terminal: null,
            at: '2026-06-15T15:10:00+00:00',
          },
          carrier: { iata_code: 'AA', name: 'American Airlines' },
          flight_number: 'AA200',
          duration: 'PT5H10M',
          number_of_stops: 0,
        },
      ],
      total_duration: 'PT5H10M',
      price: { amount: '375.00', currency: 'USD' },
      booking_class: 'ECONOMY',
    },
  ],
  count: 2,
})

const EMPTY_RESULT_JSON = JSON.stringify({
  status: 'ok',
  query: {
    origin: 'LAX',
    destination: 'JFK',
    departure_date: '2026-06-15',
    passengers: 1,
  },
  results: [],
  count: 0,
})

const CALL_META = {
  tool_name: 'search_flights',
  arguments: { origin: 'LAX', destination: 'JFK', departure_date: '2026-06-15', passengers: 1 },
  started_at: 0,
  status: 'executing',
}

describe('ToolExecutionCard', () => {
  it('renders a table with carrier and route when full_result is valid FlightSearchResult JSON', () => {
    // Arrange
    const resultMetadata = {
      summary: 'Found 2 flights',
      full_result: FLIGHT_RESULT_JSON,
      status: 'completed',
      elapsed_ms: 123,
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} resultMetadata={resultMetadata} />)

    // Open the expandable result section
    const showResultsBtn = screen.getByText(/show full results/i)
    act(() => {
      fireEvent.click(showResultsBtn)
    })

    // Assert — query with hidden:true to include Chakra Collapsible content
    expect(screen.getByRole('table', { hidden: true })).toBeInTheDocument()
    expect(screen.getByText('Delta Air Lines (DL)')).toBeInTheDocument()
    // Multiple LAX → JFK rows exist (two flights); use getAllByText
    expect(screen.getAllByText(/LAX → JFK/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/USD\s*450\.50/).length).toBeGreaterThan(0)
  })

  it('renders empty-results message when results array is empty', () => {
    // Arrange
    const resultMetadata = {
      summary: 'No flights found',
      full_result: EMPTY_RESULT_JSON,
      status: 'completed',
      elapsed_ms: 50,
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} resultMetadata={resultMetadata} />)

    // Open the expandable result section
    const showResultsBtn = screen.getByText(/show full results/i)
    act(() => {
      fireEvent.click(showResultsBtn)
    })

    // Assert
    expect(screen.queryByRole('table', { hidden: true })).not.toBeInTheDocument()
    expect(screen.getByText(/no flights matched/i)).toBeInTheDocument()
  })

  it('falls back to ReactMarkdown when full_result is non-JSON text', () => {
    // Arrange
    const resultMetadata = {
      summary: 'Error occurred',
      full_result: 'Flight search error: API timeout after 30s',
      status: 'error',
      elapsed_ms: 30000,
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} resultMetadata={resultMetadata} />)

    // Open the expandable result section
    const showResultsBtn = screen.getByText(/show full results/i)
    act(() => {
      fireEvent.click(showResultsBtn)
    })

    // Assert
    expect(screen.queryByRole('table', { hidden: true })).not.toBeInTheDocument()
    expect(screen.getByText(/api timeout after 30s/i)).toBeInTheDocument()
  })

  it('falls back to ReactMarkdown when JSON lacks the FlightSearchResult shape', () => {
    // Arrange
    const resultMetadata = {
      summary: 'Unexpected result',
      full_result: '{"foo":"bar"}',
      status: 'completed',
      elapsed_ms: 10,
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} resultMetadata={resultMetadata} />)

    // Open the expandable result section
    const showResultsBtn = screen.getByText(/show full results/i)
    act(() => {
      fireEvent.click(showResultsBtn)
    })

    // Assert
    expect(screen.queryByRole('table', { hidden: true })).not.toBeInTheDocument()
    expect(screen.getByText(/foo/i)).toBeInTheDocument()
  })

  it('renders loading state when resultMetadata is absent', () => {
    // Arrange: no resultMetadata passed

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} />)

    // Assert
    expect(screen.queryByRole('table', { hidden: true })).not.toBeInTheDocument()
    expect(screen.queryByText(/show full results/i)).not.toBeInTheDocument()
    expect(screen.getByText(/search flights/i)).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Phase 4.7 Plan 04: three-state UI (executing / completed / error)
  // ---------------------------------------------------------------------------

  it('renders Spinner when executing (no resultMetadata and no errorEvent)', () => {
    // Arrange: no resultMetadata, no errorEvent → executing state

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} />)

    // Assert: spinner is present (role="status" for Chakra Spinner)
    // and the result section is absent
    const spinnerEl = document.querySelector('[data-state]') ?? screen.queryByRole('status')
    // Chakra Spinner renders a visible spinner element; just verify no ✓ or ✗ icon
    expect(screen.queryByText('✓')).not.toBeInTheDocument()
    expect(screen.queryByText('✗')).not.toBeInTheDocument()
    expect(screen.queryByText(/show full results/i)).not.toBeInTheDocument()
    // The tool name is still visible in the header
    expect(screen.getByText(/search flights/i)).toBeInTheDocument()
    // Suppress unused variable lint warning
    void spinnerEl
  })

  it('renders checkmark and Result section when completed (resultMetadata present, no errorEvent)', () => {
    // Arrange
    const resultMetadata = {
      summary: 'Found 2 flights',
      full_result: FLIGHT_RESULT_JSON,
      status: 'completed',
      elapsed_ms: 123,
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} resultMetadata={resultMetadata} />)

    // Assert: ✓ is visible, result section trigger is present
    expect(screen.getByText('✓')).toBeInTheDocument()
    expect(screen.queryByText('✗')).not.toBeInTheDocument()
    expect(screen.getByText(/show full results/i)).toBeInTheDocument()
  })

  it('renders error state with message and Retry button when errorEvent + onRetry provided', () => {
    // Arrange
    const errorEvent = {
      type: 'error' as const,
      error_code: 'tool_error' as const,
      message: 'Tool search_flights failed: simulated outage',
      retryable: true,
      conversation_id: 'conv-1',
    }
    const onRetry = vi.fn()

    // Act
    renderWithChakra(
      <ToolExecutionCard callMetadata={CALL_META} errorEvent={errorEvent} onRetry={onRetry} />
    )

    // Assert: ✗ icon, error message, and Retry button visible
    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(screen.queryByText('✓')).not.toBeInTheDocument()
    expect(screen.getByText(/Tool search_flights failed: simulated outage/)).toBeInTheDocument()
    const retryBtn = screen.getByRole('button', { name: /retry/i })
    expect(retryBtn).toBeInTheDocument()

    // Clicking Retry calls onRetry
    fireEvent.click(retryBtn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders error state without Retry button when errorEvent provided but onRetry is absent', () => {
    // Arrange: errorEvent present, no onRetry
    const errorEvent = {
      type: 'error' as const,
      error_code: 'tool_error' as const,
      message: 'Tool search_flights failed: bad request param',
      retryable: false,
      conversation_id: 'conv-1',
    }

    // Act
    renderWithChakra(<ToolExecutionCard callMetadata={CALL_META} errorEvent={errorEvent} />)

    // Assert: error message visible, NO retry button
    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(screen.getByText(/Tool search_flights failed: bad request param/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('does NOT render the Result Collapsible when both resultMetadata and errorEvent are set', () => {
    // Arrange: error trumps result
    const resultMetadata = {
      summary: 'Found 2 flights',
      full_result: FLIGHT_RESULT_JSON,
      status: 'completed',
      elapsed_ms: 123,
    }
    const errorEvent = {
      type: 'error' as const,
      error_code: 'tool_error' as const,
      message: 'Tool failed after result',
      retryable: true,
      conversation_id: 'conv-1',
    }

    // Act
    renderWithChakra(
      <ToolExecutionCard
        callMetadata={CALL_META}
        resultMetadata={resultMetadata}
        errorEvent={errorEvent}
      />
    )

    // Assert: result trigger is NOT rendered (hasError=true suppresses it)
    expect(screen.queryByText(/show full results/i)).not.toBeInTheDocument()
    // Error is shown
    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(screen.getByText(/Tool failed after result/)).toBeInTheDocument()
  })
})
