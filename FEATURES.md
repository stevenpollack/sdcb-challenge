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
| Unread count badge | working | Count shown in room list; zeroed locally and badge removed immediately when room is selected |
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
| Room topic display | working | /topic shows current room topic in the message pane; shows "No topic set" when absent |
| Display name change | working | /nick <name> sets the user's global Matrix display name via profile API |
| Emote sending | working | /me <action> sends m.emote type; renders as "* username action" in-line |
| Date separators | working | Day-boundary separators (─── 2024-01-15 ───) shown between messages from different days |
| User profile lookup | working | /whois <@user:srv> fetches and displays display name and avatar URL via profile API |
| Clear message pane | working | /clear empties the message pane without affecting stored messages |
| Total unread in status bar | working | Status bar shows "[N unread]" count across all rooms; updates live on sync |
| Room member invite | working | /invite <@user:srv> sends room invite via Matrix API; success/failure shown in status bar |
| Room member kick | working | /kick <@user:srv> kicks a user from current room via Matrix API; success/failure shown in status bar |
| Room member ban | working | /ban <@user:srv> bans a user from current room via Matrix API; success/failure shown in status bar |
| Room creation | working | /create <name> creates a new private room; room_id shown in status bar on success |
| Set room topic | working | /settopic <text> updates the room topic via state event; confirms in status bar and message pane |
| Room member unban | working | /unban <@user:srv> lifts a ban via Matrix API; success/failure shown in status bar |
| Message reactions | working | /react <emoji> sends m.reaction (m.annotation) targeting the last visible message |
| Power level display | working | /powerlevel [<@user>] shows numeric power level and role (Admin/Moderator) from room state |
| Logout | working | /logout invalidates server session, clears ~/.config/matrixtui/session.json, and exits |
| Direct message | working | /dm <@user:srv> creates a private is_direct=True room and invites the target user |
| Presence control | working | /presence online|offline|unavailable sets global Matrix presence |
| Rename room | working | /rename <name> updates current room's m.room.name state event |
| Jump to next unread | working | Ctrl+N jumps to the next room with unread messages, skipping the current room |
| Forget room | working | /forget removes a previously left room from server history; clears it from the sidebar |
| Room alias management | working | /alias #alias:srv publishes a local alias for the current room via Matrix API |
| User presence lookup | working | /getpresence <@user> fetches and displays online/offline status and status message |
| Alias resolution | working | /resolve #alias:srv resolves a room alias to its internal room ID |
| Avatar update | working | /setavatar <mxc://> sets the user's global avatar to an mxc:// URI |
| Live member list | working | /joined fetches current room members live from server (vs. cached /members) |
| Media URL conversion | working | /mxcurl <mxc://> converts a Matrix media URI to an HTTP download URL |
| Local cache stats | working | /stats shows rooms loaded, messages cached, pending invites, and active typists |
| Own profile lookup | working | /myprofile fetches your current display name and avatar from the server |
| Send permission check | working | /canisend shows whether you have permission to send messages in current room |
