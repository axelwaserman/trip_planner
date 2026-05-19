import { parseSSELine } from '../lib/parseSSE'
import type { ChatStreamEvent } from '../types/chat'

/**
 * Reads an SSE response body and calls onEvent for each parsed ChatStreamEvent.
 * Resolves when the stream is fully consumed.
 *
 * Buffers across chunk boundaries so a `data: {...}\n\n` event split across two
 * reader.read() calls is assembled before parsing. Without the buffer, the
 * second fragment fails JSON.parse and the event is silently dropped — reproduces
 * under slow connections or with large tool-argument payloads.
 */
export async function readSSEStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last (potentially incomplete) line in the buffer.
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const event = parseSSELine(line)
        if (event !== null) {
          onEvent(event)
        }
      }
    }

    // Flush any remaining buffered content after the stream ends.
    if (buffer.trim()) {
      const event = parseSSELine(buffer)
      if (event !== null) {
        onEvent(event)
      }
    }
  } finally {
    reader.releaseLock()
  }
}
