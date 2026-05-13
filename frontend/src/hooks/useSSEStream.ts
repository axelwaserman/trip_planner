import { parseSSELine } from '../lib/parseSSE'
import type { StreamEvent } from '../types/chat'

/**
 * Reads an SSE response body and calls onEvent for each parsed StreamEvent.
 * Resolves when the stream is fully consumed.
 */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')

      for (const line of lines) {
        const event = parseSSELine(line)
        if (event !== null) {
          onEvent(event)
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
