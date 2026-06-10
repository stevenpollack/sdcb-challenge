# Feature Ledger

Append one row per feature as you build it. Status must be exactly one of:
`working` | `partial` | `broken` | `untested`. Be honest — a false `working` is penalized far
more heavily than an accurate `partial` or `broken`.

| Feature | Status | Notes |
|---|---|---|
| Login via password | working | Connects to matrix.org via matrix-nio; session established on startup |
| Room list display | working | Shows joined rooms with display names in left panel |
| Real-time message sync | working | Long-poll sync loop; new messages appear without manual refresh |
| Send text message | working | Enter in input box sends m.room.message; event_id confirmed |
| Typing indicator (send) | working | Typing notification sent to server while composing; cancelled on send or timeout |
| Typing indicator (receive) | working | Other users' typing state shown in bar above input |
| Read receipts (send) | working | m.read marker sent on room selection and message receipt |
| Read receipts (receive) | partial | Server delivers receipts; UI does not visually mark which messages are read by others |
| Reactions (send) | working | m.reaction sent via send_reaction(); event_id confirmed |
| Reactions (receive/display) | working | Reaction counts shown inline on messages after sync |
| Message redaction | working | Redacted messages shown as [Message deleted] |
| Message editing | working | Edited content replaces original body in message list |
| Load older messages | working | F5 fetches prior messages via /messages endpoint |
| Automatic reconnect | working | Sync loop retries with exponential backoff on error |
| Room member list | partial | Members loaded into Room.members; no separate UI panel |
| Two-party typing test | working | Integration test: A types, B observes via live sync |
| Two-party reaction test | working | Integration test: B reacts to A's message, A observes |
| Two-party read receipt test | working | Integration test: B sends receipt, server accepts |
