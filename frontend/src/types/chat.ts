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
}

export interface Message {
  role: MessageType
  content: string
  toolExecution?: ToolExecutionData
}

export type StreamEventType =
  | 'content'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'done'
  | 'error'

export interface StreamEvent {
  type: StreamEventType
  chunk?: string
  session_id?: string
  tool_name?: string
  tool_args?: Record<string, unknown>
  tool_result?: string
  elapsed_ms?: number
  error?: string
}

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
