import type { StreamEvent } from '../types/chat'

/**
 * Parse a single SSE line into a typed StreamEvent.
 * Returns null for lines that are not valid SSE data events.
 */
export function parseSSELine(line: string): StreamEvent | null {
  if (!line.startsWith('data: ')) {
    return null
  }

  const raw = line.slice(6)

  try {
    const parsed: unknown = JSON.parse(raw)

    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      !('type' in parsed) ||
      typeof (parsed as Record<string, unknown>).type !== 'string'
    ) {
      return null
    }

    return parsed as StreamEvent
  } catch {
    return null
  }
}
