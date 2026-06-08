"""pytest fixtures for e2e Playwright tests against textual-serve."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import os

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# Default: headed (visible browser) so tests are easy to watch locally.
# Set PLAYWRIGHT_HEADLESS=1 to run headless (required in CI without a display).
_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "0") == "1"

PROJECT_ROOT = Path(__file__).parent.parent.parent
E2E_PORT = int(os.environ.get("E2E_PORT", "8765"))
BASE_URL = f"http://localhost:{E2E_PORT}"

# Disable WebGL so xterm.js falls back to its DOM renderer, which puts each
# terminal row into a real <div> under .xterm-rows.  Without this, xterm uses
# WebGL canvases and text is not accessible via the DOM.
_DISABLE_WEBGL_JS = (
    "const _orig = HTMLCanvasElement.prototype.getContext;"
    "HTMLCanvasElement.prototype.getContext = function(type, attrs) {"
    "  if (type==='webgl2'||type==='webgl'||type==='experimental-webgl') return null;"
    "  return _orig.call(this, type, attrs);"
    "};"
)

# Read all visible terminal lines as a list of strings.
_GET_ROWS_JS = (
    "() => Array.from(document.querySelectorAll('.xterm-rows > div'))"
    ".map(r => r.textContent)"
)


def _wait_for_port(port: int, host: str = "localhost", timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"Port {port} on {host} did not open within {timeout}s")


@pytest.fixture(scope="session")
def textual_serve_process():
    """Start textual-serve serving the mock app once for the whole session."""
    serve_cmd = (
        f"from textual_serve.server import Server; "
        f"Server('{sys.executable} tests/e2e/mock_app.py', port={E2E_PORT}).serve()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", serve_cmd],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(E2E_PORT)
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# Function-scoped async fixtures keep all playwright objects on the same event
# loop as the test function, avoiding loop-scope mismatches in pytest-asyncio.

@pytest_asyncio.fixture
async def browser(textual_serve_process) -> Browser:
    """Chromium browser instance, one per test."""
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=_HEADLESS)
        yield b
        await b.close()


@pytest_asyncio.fixture
async def browser_context(browser: Browser) -> BrowserContext:
    """Browser context with the WebGL-disabling init script applied."""
    ctx = await browser.new_context()
    await ctx.add_init_script(_DISABLE_WEBGL_JS)
    yield ctx
    await ctx.close()


@pytest_asyncio.fixture
async def page(
    browser_context: BrowserContext, textual_serve_process: str
) -> Page:
    """Fresh page per test, navigated to the mock app and ready for interaction."""
    p = await browser_context.new_page()
    await p.goto(textual_serve_process)
    # .xterm-rows appears once the DOM renderer is active and content rendered.
    await p.wait_for_selector(".xterm-rows", timeout=20_000)
    # Allow fake_connect to fire, rooms to populate, and first frame to settle.
    await p.wait_for_timeout(1500)
    yield p
    await p.close()


# ---------------------------------------------------------------------------
# Helpers (importable in tests)
# ---------------------------------------------------------------------------


async def get_terminal_rows(page: Page) -> list[str]:
    """Return each xterm.js terminal row as a string."""
    return await page.evaluate(_GET_ROWS_JS)


async def get_terminal_text(page: Page) -> str:
    """Return the full visible terminal content as one joined string."""
    rows = await get_terminal_rows(page)
    return " ".join(rows)


async def terminal_contains(
    page: Page, text: str, timeout_ms: int = 5_000
) -> bool:
    """Poll the terminal until *text* appears, or return False on timeout."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if text in await get_terminal_text(page):
            return True
        await page.wait_for_timeout(200)
    return False


async def focus_terminal(page: Page) -> None:
    """Click the xterm helper textarea so keyboard events reach the app."""
    await page.locator(".xterm-helper-textarea").click()


async def send_command(page: Page, text: str) -> None:
    """Type a message or slash command into the msg-input and press Enter."""
    await focus_terminal(page)
    await page.keyboard.type(text)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(600)
