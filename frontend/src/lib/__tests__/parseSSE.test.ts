import { describe, expect, it } from 'vitest'
import { parseSSELine } from '../parseSSE'

describe('parseSSELine', () => {
  // --- Branch: line does not start with "data: " ---

  it('returns null for an empty string', () => {
    expect(parseSSELine('')).toBeNull()
  })

  it('returns null for a comment line', () => {
    expect(parseSSELine(': keep-alive')).toBeNull()
  })

  it('returns null for an event line', () => {
    expect(parseSSELine('event: message')).toBeNull()
  })

  it('returns null for a whitespace-only line', () => {
    expect(parseSSELine('   ')).toBeNull()
  })

  // --- Branch: line starts with "data: " but JSON is invalid ---

  it('returns null when the data payload is not valid JSON', () => {
    expect(parseSSELine('data: not-json')).toBeNull()
  })

  it('returns null when the data payload is a bare string', () => {
    expect(parseSSELine('data: hello world')).toBeNull()
  })

  // --- Branch: parsed JSON is not an object ---

  it('returns null when the payload is a JSON number', () => {
    expect(parseSSELine('data: 42')).toBeNull()
  })

  it('returns null when the payload is a JSON array', () => {
    expect(parseSSELine('data: [1,2,3]')).toBeNull()
  })

  it('returns null when the payload is JSON null', () => {
    expect(parseSSELine('data: null')).toBeNull()
  })

  it('returns null when the payload is a JSON boolean', () => {
    expect(parseSSELine('data: true')).toBeNull()
  })

  // --- Branch: parsed JSON is an object but missing "type" ---

  it('returns null when the object has no type field', () => {
    expect(parseSSELine('data: {"chunk":"hello"}')).toBeNull()
  })

  // --- Branch: parsed JSON has a non-string "type" ---

  it('returns null when type is a number', () => {
    expect(parseSSELine('data: {"type":1}')).toBeNull()
  })

  it('returns null when type is null', () => {
    expect(parseSSELine('data: {"type":null}')).toBeNull()
  })

  // --- Branch: valid StreamEvent shapes ---

  it('parses a content event', () => {
    const event = parseSSELine('data: {"type":"content","chunk":"Hello","session_id":"abc"}')
    expect(event).toEqual({ type: 'content', chunk: 'Hello', session_id: 'abc' })
  })

  it('parses a thinking event', () => {
    const event = parseSSELine('data: {"type":"thinking","chunk":"...", "session_id":"s1"}')
    expect(event).toEqual({ type: 'thinking', chunk: '...', session_id: 's1' })
  })

  it('parses a done event', () => {
    const event = parseSSELine('data: {"type":"done","session_id":"s2"}')
    expect(event).toEqual({ type: 'done', session_id: 's2' })
  })

  it('parses an error event', () => {
    const event = parseSSELine('data: {"type":"error","error":"something failed"}')
    expect(event).toEqual({ type: 'error', error: 'something failed' })
  })

  it('parses a tool_call event', () => {
    const event = parseSSELine(
      'data: {"type":"tool_call","tool_name":"search","tool_args":{"q":"Paris"},"session_id":"s3"}'
    )
    expect(event).toEqual({
      type: 'tool_call',
      tool_name: 'search',
      tool_args: { q: 'Paris' },
      session_id: 's3',
    })
  })

  it('parses a tool_result event', () => {
    const event = parseSSELine(
      'data: {"type":"tool_result","tool_name":"search","tool_result":"found it","elapsed_ms":42,"session_id":"s4"}'
    )
    expect(event).toEqual({
      type: 'tool_result',
      tool_name: 'search',
      tool_result: 'found it',
      elapsed_ms: 42,
      session_id: 's4',
    })
  })

  it('parses an event with only a type field', () => {
    const event = parseSSELine('data: {"type":"done"}')
    expect(event).toEqual({ type: 'done' })
  })
})
