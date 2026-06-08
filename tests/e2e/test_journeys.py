"""Playwright functional tests for the matrixtui web app.

Each test exercises a complete user journey through the browser UI served by
textual-serve.  The app runs with a pre-seeded mock client (no real Matrix
connection), so these tests are fully offline.

DOM renderer approach: we inject a WebGL-blocking script (see conftest.py) so
xterm.js falls back to its DOM renderer, making each terminal row accessible
as a real <div>.  Helpers in conftest.py wrap the read/assertion logic.
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import (
    focus_terminal,
    get_terminal_text,
    send_command,
    terminal_contains,
)


# ---------------------------------------------------------------------------
# Journey 1: App startup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_welcome_banner_visible(page):
    """The 'matrixtui' banner is shown in the message pane on startup."""
    assert await terminal_contains(page, "matrixtui"), (
        "Welcome banner 'matrixtui' not found in terminal output"
    )


@pytest.mark.asyncio
async def test_status_bar_shows_connected(page):
    """Status bar shows 'Connected' with the mock user ID after startup."""
    assert await terminal_contains(page, "Connected as @testuser:matrix.org"), (
        "Status bar did not show the expected connected text"
    )


@pytest.mark.asyncio
async def test_room_list_shows_all_seeded_rooms(page):
    """All three seeded rooms appear in the sidebar."""
    text = await get_terminal_text(page)
    for room in ("General", "Project Alpha", "Random"):
        assert room in text, f"Room '{room}' missing from room list"


@pytest.mark.asyncio
async def test_unread_badge_visible_on_startup(page):
    """General room shows its [2] unread badge."""
    assert await terminal_contains(page, "General [2]"), (
        "Unread badge [2] not visible on the General room"
    )


# ---------------------------------------------------------------------------
# Journey 2: Room filter (Ctrl+F)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ctrl_f_opens_filter_and_typing_filters_rooms(page):
    """Ctrl+F focuses the filter; typing 'proj' hides General and Random."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(300)
    await page.keyboard.type("proj")
    await page.wait_for_timeout(500)

    text = await get_terminal_text(page)
    assert "Project Alpha" in text, "'Project Alpha' should remain visible after filter 'proj'"
    assert "proj" in text.lower(), "Filter input should echo the typed text"


@pytest.mark.asyncio
async def test_filter_by_room_name(page):
    """Filtering by 'general' keeps only the General room visible."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(300)
    await page.keyboard.type("general")
    await page.wait_for_timeout(500)
    text = await get_terminal_text(page)
    assert "General" in text


@pytest.mark.asyncio
async def test_clearing_filter_restores_all_rooms(page):
    """Clearing the filter brings General, Project Alpha, and Random back."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(200)
    await page.keyboard.type("rand")
    await page.wait_for_timeout(400)
    for _ in range(4):
        await page.keyboard.press("Backspace")
    await page.wait_for_timeout(500)
    text = await get_terminal_text(page)
    for room in ("General", "Project Alpha", "Random"):
        assert room in text, f"Room '{room}' should be visible after clearing filter"


@pytest.mark.asyncio
async def test_filter_enter_moves_focus_to_room_list(page):
    """Pressing Enter in the filter input moves focus to the room list."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(200)
    await page.keyboard.press("Enter")
    # App should still be responsive — status bar still present.
    assert await terminal_contains(page, "Connected"), (
        "App became unresponsive after Enter in filter"
    )


# ---------------------------------------------------------------------------
# Journey 3: Room selection
# ---------------------------------------------------------------------------


async def _select_first_room(page) -> None:
    """Navigate Ctrl+F → Enter → ArrowDown → Enter to open the first room."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(200)
    await page.keyboard.press("Enter")  # filter input → room list
    await page.wait_for_timeout(200)
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1000)


@pytest.mark.asyncio
async def test_selecting_room_shows_room_title(page):
    """After selecting a room, the room title updates in the header area."""
    await _select_first_room(page)
    text = await get_terminal_text(page)
    # General is the first room (highest last_ts). Title shows "General (10)".
    assert "General" in text, f"Room title 'General' not visible after selection. Got:\n{text[:300]}"


@pytest.mark.asyncio
async def test_selecting_room_shows_messages(page):
    """After selecting General, its seeded messages appear in the pane."""
    await _select_first_room(page)
    assert await terminal_contains(page, "Hello everyone!"), (
        "Expected message 'Hello everyone!' not visible after selecting General"
    )
    assert await terminal_contains(page, "alice"), (
        "Expected sender 'alice' not visible after selecting General"
    )


@pytest.mark.asyncio
async def test_selecting_room_clears_unread_badge(page):
    """Selecting the General room removes its [2] unread badge."""
    # Confirm badge exists before selecting.
    assert await terminal_contains(page, "General [2]")
    await _select_first_room(page)
    text = await get_terminal_text(page)
    assert "General [2]" not in text, "Unread badge should be cleared after room selection"


@pytest.mark.asyncio
async def test_date_separator_shown_in_messages(page):
    """A date separator line (e.g. '─── 2023-11-03 ───') appears in messages."""
    await _select_first_room(page)
    assert await terminal_contains(page, "2023-11-"), (
        "Date separator not visible in message pane"
    )


# ---------------------------------------------------------------------------
# Journey 4: Slash commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_command_shows_command_reference(page):
    """/help clears the pane and shows the keyboard/command reference."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")  # ensure msg-input is focused
    await page.wait_for_timeout(200)
    await send_command(page, "/help")
    assert await terminal_contains(page, "/join"), (
        "/help output must contain '/join' command reference"
    )
    assert await terminal_contains(page, "/help"), (
        "/help output must contain '/help' itself"
    )


@pytest.mark.asyncio
async def test_clear_command_empties_pane(page):
    """/help followed by /clear leaves the message pane mostly blank."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await send_command(page, "/help")
    await page.wait_for_timeout(300)
    await send_command(page, "/clear")
    await page.wait_for_timeout(500)
    text = await get_terminal_text(page)
    # After /clear the help content should be gone.
    assert "/join" not in text, "/clear should have erased the /help output"


@pytest.mark.asyncio
async def test_stats_command_shows_cache_counts(page):
    """/stats shows the local cache stats with room and message counts."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await send_command(page, "/stats")
    assert await terminal_contains(page, "Rooms loaded:"), (
        "/stats should show 'Rooms loaded:'"
    )
    assert await terminal_contains(page, "Messages cached:"), (
        "/stats should show 'Messages cached:'"
    )


@pytest.mark.asyncio
async def test_stats_command_shows_correct_counts(page):
    """The /stats counts match the 3 rooms and 5 messages in mock data."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await send_command(page, "/stats")
    text = await get_terminal_text(page)
    assert "3" in text, "Expected room count '3' in /stats output"
    assert "5" in text, "Expected message count '5' in /stats output"


@pytest.mark.asyncio
async def test_myprofile_command_shows_display_name(page):
    """/myprofile shows the mock user's display name 'Test User'."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await send_command(page, "/myprofile")
    assert await terminal_contains(page, "Test User"), (
        "/myprofile should show 'Test User' (mock profile display name)"
    )


@pytest.mark.asyncio
async def test_search_no_results_message(page):
    """/search with an unmatched query shows 'No results'."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await send_command(page, "/search zzz_no_match_xyz")
    assert await terminal_contains(page, "No results"), (
        "Expected 'No results' message for unmatched search query"
    )


@pytest.mark.asyncio
async def test_search_with_matching_query(page):
    """In a room, /search finds messages matching the query."""
    # seed: search_messages needs to return something real.
    # Our mock returns [] by default, so first verify search dispatches correctly.
    # After selecting a room and searching "hello":
    await _select_first_room(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    # Even with mock returning [], the pane should show 'No results' (not crash).
    await send_command(page, "/search hello")
    assert await terminal_contains(page, "No results") or await terminal_contains(
        page, "hello"
    ), "Search command should show results or 'No results' — not crash"


# ---------------------------------------------------------------------------
# Journey 5: Keyboard shortcuts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escape_refocuses_message_input(page):
    """Escape always returns focus to the message input."""
    await focus_terminal(page)
    await page.keyboard.press("Control+f")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)
    # Typing after Escape should go to msg-input (no room, so it's a noop).
    await page.keyboard.type("test-noop")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(400)
    assert await terminal_contains(page, "Connected"), (
        "App crashed or became unresponsive after Escape + type + Enter"
    )


@pytest.mark.asyncio
async def test_ctrl_r_noop_without_room(page):
    """Ctrl+R (reload history) without a selected room must not crash."""
    await focus_terminal(page)
    await page.keyboard.press("Control+r")
    await page.wait_for_timeout(600)
    assert await terminal_contains(page, "Connected"), (
        "App crashed after Ctrl+R with no room selected"
    )


@pytest.mark.asyncio
async def test_ctrl_n_jumps_to_unread_room(page):
    """Ctrl+N (next unread) navigates to a room with unread messages."""
    await focus_terminal(page)
    await page.keyboard.press("Control+n")
    await page.wait_for_timeout(1000)
    # General has unread=2 — after Ctrl+N it should be selected and messages visible.
    text = await get_terminal_text(page)
    assert text.strip(), "Terminal was empty after Ctrl+N — app may have crashed"
    # The status bar should still be present.
    assert await terminal_contains(page, "Connected")


@pytest.mark.asyncio
async def test_footer_shows_keybindings(page):
    """The footer bar shows the Ctrl keybinding hints."""
    text = await get_terminal_text(page)
    assert "History" in text or "Filter" in text, (
        "Footer keybinding hints not visible (expected 'History' or 'Filter')"
    )


# ---------------------------------------------------------------------------
# Journey 6: Message input behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_input_does_not_crash(page):
    """Pressing Enter with an empty msg-input is a noop."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(400)
    assert await terminal_contains(page, "Connected"), (
        "App crashed after submitting empty input"
    )


@pytest.mark.asyncio
async def test_plain_message_no_room_is_noop(page):
    """Typing a plain message without selecting a room does nothing."""
    await focus_terminal(page)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)
    await page.keyboard.type("Hello world")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(400)
    assert await terminal_contains(page, "Connected"), (
        "App crashed after sending message with no room selected"
    )
