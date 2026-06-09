# Feature Ledger

Append one row per feature as you build it. Status must be exactly one of:
`working` | `partial` | `broken` | `untested`. Be honest — a false `working` is penalized far
more heavily than an accurate `partial` or `broken`.

| Feature | Status | Notes |
|---|---|---|
| Login via password | working | reads MATRIX_USER/PASSWORD from .env.local; retries on M_LIMIT_EXCEEDED |
| Room list sidebar | working | auto-populated after login; updates on room join/leave events |
| Real-time message receive | working | sync_forever callback delivers messages without manual refresh |
| Send message | working | Enter submits; event_id confirmed by server |
| Message history on room select | working | fetches last 50 messages via room_messages API |
| Join room by alias/ID | working | Ctrl+R opens dialog; join API call updates sidebar |
| Keyboard navigation | working | Ctrl+J (rooms), Ctrl+K (input), Ctrl+Q (quit), Escape (cancel) |
| Reconnect / sync retry | working | exponential backoff in _sync_forever; resume after transient errors |
| Display name resolution | working | strips @-prefix and server suffix from user IDs |
| Two-party message receive (integration test) | working | test_live_realtime_receive uses MATRIX_USER_B when available |
