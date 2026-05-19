---
title: Migrate /api/chat route from StreamingResponse to EventSourceResponse
created: 2026-05-18
source: PR #15 review (axelwaserman, 2026-05-18)
priority: medium
type: refactor
---

## Why

The current `/api/chat` route uses `StreamingResponse` with
`media_type="text/event-stream"` and manually formats `data: …\n\n` frames.
This is option-2-dressed-as-option-3: it mimics SSE on the wire but loses
all SSE-native benefits:

- No browser-native reconnect (`retry:` frame support)
- No `Last-Event-ID` tracking
- No typed `event:` field per frame (requires manual parsing on the client)
- Error frames have no standard shape

`sse-starlette`'s `EventSourceResponse` + `ServerSentEvent` gives all of
the above for free and aligns the implementation with what we already
describe in architecture docs.

## What

1. Add `sse-starlette` to `backend/pyproject.toml` dependencies.
2. Refactor `app/api/routes/routes.py`:
   - Replace `StreamingResponse` import with `EventSourceResponse` from
     `sse_starlette.sse`.
   - Yield `ServerSentEvent(data=json, event=stream_event.type)` instead of
     raw `f"data: {json}\n\n"` strings.
3. Update `ChatService.chat_stream()` if it currently yields raw strings —
   it should yield `StreamEvent` objects and let the route handle SSE framing.
4. Update the React `ChatInterface.tsx` SSE client to use named `event`
   types for dispatch instead of parsing `type` from the JSON body.
5. Update integration tests to assert on `ServerSentEvent` shape.

## Natural fit

Phase 4.7 (Error Handling + StreamEvent Hierarchy) — proper SSE error frames
(`event: error\ndata: {…}`) require native SSE semantics to be useful. Do
this migration at the start of that phase so error frames get the right shape
from day one.

## Acceptance criteria

- [ ] `response_class=EventSourceResponse` on the `/api/chat` route
- [ ] All `StreamEvent` types emitted as named SSE events (`event: content`,
  `event: tool_call`, etc.)
- [ ] Browser reconnect works without client-side polling fallback
- [ ] `just test` passes; integration tests updated
- [ ] React client dispatches on `event.type` (SSE named event), not JSON body `type`
