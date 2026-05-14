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
