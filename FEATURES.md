# Feature Ledger

Append one row per feature as you build it. Status must be exactly one of:
`working` | `partial` | `broken` | `untested`. Be honest — a false `working` is penalized far
more heavily than an accurate `partial` or `broken`.

| Feature | Status | Notes |
|---|---|---|
| Password login | working | Authenticates against matrix.org via matrix-nio; session token held in memory |
| Room list display | working | Sidebar shows all joined rooms sorted by most-recent message; live-updates on sync |
| Message history view | working | Scrollable RichLog pane; timestamps and sender names; loads on room select |
| Send text messages | working | Input bar submits on Enter; event_id returned confirms server acceptance |
| Real-time sync loop | working | Background asyncio task; 30 s long-poll; auto-reconnects on error |
| Load older history | working | Ctrl+R fetches prior page via /messages; prepends to message list |
| Display names & timestamps | working | Sender localpart shown; UTC HH:MM timestamp per message |
| Unread count badge | partial | Count shown in room list when server reports unread_notifications; resets only on server side |
