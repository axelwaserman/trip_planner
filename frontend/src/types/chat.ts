export type MessageType = 'user' | 'assistant' | 'tool_execution' | 'thinking'

export interface ToolCallMetadata {
  tool_name: string
  arguments: Record<string, unknown>
  started_at: number
  status: string
}

export interface ToolResultMetadata {
  summary: string
  full_result: string
  status: string
  elapsed_ms: number
}

export interface ToolExecutionData {
  callMetadata: ToolCallMetadata
  resultMetadata?: ToolResultMetadata
  // Populated when an ErrorEvent with retryable=true arrives for this tool call.
  // ToolExecutionCard reads this to render the error-state UI + Retry button.
  errorEvent?: ErrorEvent
}

export interface Message {
  role: MessageType
  content: string
  toolExecution?: ToolExecutionData
}

// Discriminated union replacing the flat StreamEvent interface (Phase 4.7 REQ-streamevent-hierarchy).
// Each member has a required literal `type` field so TypeScript can narrow exhaustively.
//
// Field ordering note (Phase 6 / Plan 06-05a + 06-05b): `conversation_id` is
// declared LAST in every event interface to mirror the Pydantic per-subclass
// JSON serialisation order on the backend (StreamEvent subclasses in
// `backend/app/chat/models.py`). Any code that does ordered key iteration
// observes the same wire-byte order on both sides.

export interface ContentEvent {
  type: 'content'
  chunk: string
  conversation_id: string
}

export interface ThinkingEvent {
  type: 'thinking'
  chunk: string
  conversation_id: string
}

export interface ToolCallEvent {
  type: 'tool_call'
  tool_name: string
  tool_args: Record<string, unknown>
  conversation_id: string
}

export interface ToolResultEvent {
  type: 'tool_result'
  tool_name: string
  tool_result: string
  elapsed_ms: number
  conversation_id: string
}

// `session_error` is retained verbatim — wire-level snake_case error codes
// are part of the contract per CLAUDE.md and are exempt from the D-03 rename.
export type ErrorCode = 'session_error' | 'tool_error' | 'stream_error'

export interface ErrorEvent {
  type: 'error'
  error_code: ErrorCode
  message: string
  retryable: boolean
  tool_name?: string
  raw_detail?: string
  conversation_id: string
}

export type ChatStreamEvent =
  | ContentEvent
  | ThinkingEvent
  | ToolCallEvent
  | ToolResultEvent
  | ErrorEvent

// ----------------------------------------------------------------------
// Structured tool-result types (REQ-tool-json-output)
// Backend search_flights() now returns FlightSearchResult.model_dump_json();
// these mirror the Pydantic models in backend/app/models.py.
// ----------------------------------------------------------------------

export interface FlightEndpointData {
  iata_code: string
  city: string
  terminal: string | null
  at: string
}

export interface CarrierInfoData {
  iata_code: string
  name: string
}

export interface PriceInfoData {
  amount: string
  currency: string
}

export interface FlightSegmentData {
  id: string
  departure: FlightEndpointData
  arrival: FlightEndpointData
  carrier: CarrierInfoData
  flight_number: string
  duration: string
  number_of_stops: number
}

export interface FlightResultData {
  id: string
  segments: FlightSegmentData[]
  total_duration: string
  price: PriceInfoData
  booking_class: string
}

export interface FlightSearchQueryData {
  origin: string
  destination: string
  departure_date: string
  passengers: number
}

export interface FlightSearchResultData {
  status: string
  query: FlightSearchQueryData
  results: FlightResultData[]
  count: number
}
