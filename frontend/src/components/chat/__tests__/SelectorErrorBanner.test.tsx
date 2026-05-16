import { ChakraProvider } from '@chakra-ui/react'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { system } from '../../../theme'
import type { ProviderErrorView } from '../../../lib/providerErrors'
import { SelectorErrorBanner } from '../SelectorErrorBanner'

function renderWithChakra(ui: ReactElement) {
  return render(<ChakraProvider value={system}>{ui}</ChakraProvider>)
}

function makeError(overrides: Partial<ProviderErrorView> = {}): ProviderErrorView {
  return {
    code: 'provider_unreachable',
    message: "Can't reach Ollama at http://localhost:11434",
    hint: 'Run ollama serve in another terminal.',
    inlineCode: ['ollama serve'],
    ...overrides,
  }
}

describe('SelectorErrorBanner', () => {
  it('returns null when error prop is null', () => {
    const { container } = renderWithChakra(
      <SelectorErrorBanner error={null} onRetry={vi.fn()} />
    )

    expect(container.firstChild).toBeNull()
  })

  it('renders the error message and a Retry button when error is provided', () => {
    renderWithChakra(<SelectorErrorBanner error={makeError()} onRetry={vi.fn()} />)

    expect(
      screen.getByText("Can't reach Ollama at http://localhost:11434")
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('calls onRetry when Retry button is clicked', () => {
    const onRetry = vi.fn()
    renderWithChakra(<SelectorErrorBanner error={makeError()} onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: /retry/i }))

    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('has aria-live=polite and role=status on the container', () => {
    renderWithChakra(<SelectorErrorBanner error={makeError()} onRetry={vi.fn()} />)

    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })

  it('renders inlineCode chips for each entry in error.inlineCode', () => {
    const { container, rerender } = renderWithChakra(
      <SelectorErrorBanner
        error={makeError({ inlineCode: ['ollama serve', 'ollama pull qwen3:4b'] })}
        onRetry={vi.fn()}
      />
    )

    const chips = container.querySelectorAll('code')
    expect(chips).toHaveLength(2)
    expect(chips[0]).toHaveTextContent('ollama serve')
    expect(chips[1]).toHaveTextContent('ollama pull qwen3:4b')

    rerender(
      <ChakraProvider value={system}>
        <SelectorErrorBanner error={makeError({ inlineCode: [] })} onRetry={vi.fn()} />
      </ChakraProvider>
    )

    expect(container.querySelectorAll('code')).toHaveLength(0)
  })
})
