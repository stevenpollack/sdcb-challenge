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
| Non-text message types | working | Images, files, video, audio shown as [type: filename]; emotes prefixed with *; notices dimmed |
| Typing indicators | working | Status line below messages shows "alice is typing…" updated via TypingNoticeEvent |
| Member count in room title | working | Room title bar shows (N) member count after display name |
| Read receipts | working | Sent automatically on room switch for the last visible message |
| Room filter / search | working | Ctrl+F focuses filter box; typing hides non-matching rooms live |
| Redacted message display | working | Redacted events show as [redacted] in-place; no crash on unknown event_id |
| Message edits (m.replace) | working | Edited messages append [edited] and show new content in-place |
| Room join via slash command | working | /join #alias:server joins room and updates room list |
| Room leave via slash command | working | /leave leaves current room, removes from sidebar and clears pane |
| Message search | working | /search <query> searches all loaded messages by body or sender, shows results in pane |
| Room member list | working | /members lists all current members of the active room |
| Mention highlighting | working | Messages containing local username shown with bold red background |
| In-app help | working | /help displays all keybindings and slash commands in the message pane |
| Session persistence | working | Login token saved to ~/.config/matrixtui/session.json (mode 0o600); restored on next start |
| Invite notifications | working | Incoming invites shown in status bar with /join prompt; stored in client.invites dict |
