#!/usr/bin/env python3
"""Live two-party sync check — the functional ground truth, run by the EVALUATOR.

Why this exists: a model can write tests against a mock homeserver, get them green, and claim
features "work" while the app does nothing useful against the REAL server (this happened — a
submission passed its own suite but never delivered real-time sync to the provided test user).
Static metrics (coverage, complexity, regressions) cannot see this. Only a live check against the
real homeserver, independent of the model's own code, can.

This script is deliberately stack-agnostic and SDK-free: it talks to Matrix over raw HTTP using
two real test accounts you provide, so it does not depend on anything the model built. It performs
two independent checks:

  CHECK 1 — SERVER TRUTH (no model code involved):
    Log in as both users via the real homeserver. Ensure they share a room (create + invite +
    auto-join if needed). User B sends a unique message. The probe's OWN /sync (as user A) must
    receive it within the timeout. This proves the test infrastructure is real and federating —
    if this fails, the homeserver/credentials are the problem, not the model.

  CHECK 2 — MODEL TUI RECEIVE (the actual pass/fail for the submission):
    Launch the model's app as user A (via `make run` or a configured command) in a pty, send a
    fresh unique message as user B, and assert the model's TUI displays it within the timeout by
    scanning the terminal output for the unique token. This is what a mock cannot fake.

Usage:
  # Credentials are read from .env.local by default (the same file the model used).
  python eval/scripts/live_sync_check.py [--timeout 30] [--tui-cmd "make run"] [--server-only]

  # To grade with a SEPARATE evaluator pair (not the model's accounts), override via env vars,
  # which take precedence over .env.local:
  MATRIX_USER_A=@evaluator1:matrix.org MATRIX_PASSWORD_A=... \
  MATRIX_USER_B=@evaluator2:matrix.org MATRIX_PASSWORD_B=... \
  python eval/scripts/live_sync_check.py

  # Or point at a different dotenv file:
  python eval/scripts/live_sync_check.py --env-file .env.evaluator

Expected keys (in .env.local or the environment): MATRIX_HOMESERVER, MATRIX_USER_A,
MATRIX_PASSWORD_A, MATRIX_USER_B, MATRIX_PASSWORD_B.

Exit code 0 only if all selected checks pass. Writes live_sync_check.json.
"""
import argparse
import json
import os
import re
import select
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def load_dotenv(path=".env.local"):
    """Minimal .env parser (stdlib only). Returns {key: value}. Does not override real env vars.

    Handles KEY=value, optional `export ` prefix, # comments, and single/double quotes. Ignores
    blank lines and malformed entries.
    """
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key:
                env[key] = val
    return env


def _req(method, url, token=None, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


class MatrixClient:
    """Minimal raw-HTTP Matrix client — enough to log in, manage a room, send, and sync."""

    def __init__(self, homeserver, user, password):
        self.hs = homeserver.rstrip("/")
        self.user = user
        self.password = password
        self.token = None
        self.next_batch = None

    def base(self, path):
        return f"{self.hs}/_matrix/client/v3{path}"

    def login(self):
        status, resp = _req("POST", self.base("/login"), body={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": self.user},
            "password": self.password,
        })
        if status != 200 or "access_token" not in resp:
            raise RuntimeError(f"login failed for {self.user}: {status} {resp.get('error','')}")
        self.token = resp["access_token"]
        return self

    def create_room_with(self, invite_user):
        status, resp = _req("POST", self.base("/createRoom"), self.token, body={
            "preset": "private_chat", "invite": [invite_user],
        })
        if status != 200:
            raise RuntimeError(f"createRoom failed: {status} {resp}")
        return resp["room_id"]

    def join(self, room_id):
        rid = urllib.parse.quote(room_id)
        return _req("POST", self.base(f"/rooms/{rid}/join"), self.token, body={})

    def send_text(self, room_id, body):
        rid = urllib.parse.quote(room_id)
        txn = uuid.uuid4().hex
        status, resp = _req(
            "PUT", self.base(f"/rooms/{rid}/send/m.room.message/{txn}"), self.token,
            body={"msgtype": "m.text", "body": body})
        if status != 200:
            raise RuntimeError(f"send failed: {status} {resp}")
        return resp.get("event_id")

    def sync_once(self, timeout_ms=1000):
        params = {"timeout": str(timeout_ms)}
        if self.next_batch:
            params["since"] = self.next_batch
        url = self.base("/sync") + "?" + urllib.parse.urlencode(params)
        status, resp = _req("GET", url, self.token, timeout=(timeout_ms / 1000) + 20)
        if status == 200:
            self.next_batch = resp.get("next_batch", self.next_batch)
        return resp

    def prime_sync(self):
        """Initial sync to establish a since-token, so we only see NEW events afterward."""
        self.sync_once(timeout_ms=0)

    def wait_for_message(self, body_token, deadline):
        """Poll /sync until an event whose body contains body_token arrives, or deadline passes."""
        while time.time() < deadline:
            resp = self.sync_once(timeout_ms=2000)
            rooms = resp.get("rooms", {}).get("join", {})
            for _rid, rdata in rooms.items():
                for ev in rdata.get("timeline", {}).get("events", []):
                    if ev.get("type") == "m.room.message":
                        if body_token in (ev.get("content", {}).get("body", "")):
                            return True
        return False


def ensure_shared_room(a, b):
    """Return a room_id both A and B have joined. Create + invite + join if needed."""
    room_id = a.create_room_with(b.user)
    # B accepts the invite (poll briefly for it to land, then join)
    deadline = time.time() + 30
    while time.time() < deadline:
        resp = b.sync_once(timeout_ms=2000)
        invites = resp.get("rooms", {}).get("invite", {})
        if room_id in invites or any(room_id == r for r in invites):
            break
    status, resp = b.join(room_id)
    if status != 200:
        # try once more after a short wait
        time.sleep(3)
        status, resp = b.join(room_id)
        if status != 200:
            raise RuntimeError(f"user B could not join room: {status} {resp}")
    return room_id


def server_truth_check(a, b, timeout):
    """CHECK 1: B sends, the probe's own sync (as A) receives. No model code involved."""
    room_id = ensure_shared_room(a, b)
    a.prime_sync()
    token = f"probe-truth-{uuid.uuid4().hex[:12]}"
    b.send_text(room_id, token)
    ok = a.wait_for_message(token, time.time() + timeout)
    return {"check": "server_truth", "passed": ok, "room_id": room_id, "token": token}


def tui_receive_check(a, b, timeout, tui_cmd, env_for_tui):
    """CHECK 2: launch the model's app as A, B sends, assert the TUI shows the message."""
    room_id = ensure_shared_room(a, b)
    token = f"probe-tui-{uuid.uuid4().hex[:12]}"

    # Launch the model's app in a pseudo-terminal so a TUI renders.
    import pty
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        tui_cmd, shell=True, stdin=slave, stdout=slave, stderr=slave,
        env={**os.environ, **env_for_tui}, preexec_fn=os.setsid,
    )
    os.close(slave)

    captured = []
    found = False
    sent = False
    deadline = time.time() + timeout
    startup_grace = time.time() + min(15, timeout / 2)  # let the app log in / initial sync first

    try:
        while time.time() < deadline:
            if not sent and time.time() > startup_grace:
                b.send_text(room_id, token)  # send only after the app has had time to come up
                sent = True
            r, _, _ = select.select([master], [], [], 1.0)
            if r:
                try:
                    chunk = os.read(master, 4096).decode(errors="replace")
                except OSError:
                    break
                captured.append(chunk)
                if token in "".join(captured)[-8000:]:
                    found = True
                    break
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except ProcessLookupError:
            pass
        os.close(master)

    text = "".join(captured)
    return {
        "check": "tui_receive", "passed": found, "room_id": room_id, "token": token,
        "message_was_sent": sent,
        "tui_output_tail": text[-2000:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=30, help="seconds to wait for a message")
    ap.add_argument("--tui-cmd", default="make run", help="command that launches the model's TUI")
    ap.add_argument("--server-only", action="store_true",
                    help="run only CHECK 1 (verify infra), skip launching the model's app")
    ap.add_argument("--env-file", default=".env.local",
                    help="dotenv file to read credentials from (default: .env.local)")
    args = ap.parse_args()

    # Credentials resolve from .env.local by default; any real exported env var overrides the file.
    dot = load_dotenv(args.env_file)
    def cred(key):
        return os.environ.get(key) or dot.get(key)

    hs = cred("MATRIX_HOMESERVER") or "https://matrix.org"
    ua, pa = cred("MATRIX_USER_A"), cred("MATRIX_PASSWORD_A")
    ub, pb = cred("MATRIX_USER_B"), cred("MATRIX_PASSWORD_B")
    if not all([ua, pa, ub, pb]):
        sys.exit(f"missing credentials: need MATRIX_USER_A/PASSWORD_A and "
                 f"MATRIX_USER_B/PASSWORD_B in {args.env_file} or the environment")

    a = MatrixClient(hs, ua, pa).login()
    b = MatrixClient(hs, ub, pb).login()

    results = []
    truth = server_truth_check(a, b, args.timeout)
    results.append(truth)
    print(f"CHECK 1 server_truth: {'PASS' if truth['passed'] else 'FAIL'}")
    if not truth["passed"]:
        print("  -> the real homeserver did not deliver B's message to the probe. The test "
              "infrastructure or credentials are the problem; fix before judging the model.",
              file=sys.stderr)

    # The model's app reads credentials from .env.local under these exact names (see
    # .env.local.example). Feed the evaluator's accounts through the same contract so the app
    # launches as user A with user B available exactly as during the run.
    env_for_tui = {
        "MATRIX_HOMESERVER": hs,
        "MATRIX_USER_A": ua, "MATRIX_PASSWORD_A": pa,
        "MATRIX_USER_B": ub, "MATRIX_PASSWORD_B": pb,
    }
    if not args.server_only:
        if not truth["passed"]:
            print("Skipping CHECK 2 because CHECK 1 failed (infra not trustworthy).")
        else:
            tui = tui_receive_check(a, b, args.timeout, args.tui_cmd, env_for_tui)
            results.append(tui)
            print(f"CHECK 2 tui_receive: {'PASS' if tui['passed'] else 'FAIL'}")
            if not tui["passed"]:
                print("  -> the model's TUI did NOT display a message that the real server "
                      "delivered. This is a functional FAIL regardless of test-suite results.",
                      file=sys.stderr)

    overall = all(r["passed"] for r in results)
    with open("live_sync_check.json", "w") as f:
        json.dump({"overall_passed": overall, "homeserver": hs, "checks": results}, f, indent=2)
    print(f"\nOVERALL: {'PASS' if overall else 'FAIL'}  (wrote live_sync_check.json)")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()