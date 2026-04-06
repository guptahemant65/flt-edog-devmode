"""Thin Python wrapper around the agent-browser CLI.

Provides typed helpers for navigation, interaction, waiting, network
capture, and JavaScript evaluation.  Every command runs in the
``edog`` session so cookies and state persist across calls.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class AgentBrowserError(Exception):
    """Raised when an agent-browser command fails."""


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------

_BINARY: Optional[str] = None

_WELL_KNOWN_PATHS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "bin", "agent-browser.exe"),
    os.path.join(os.path.expanduser("~"), ".local", "bin", "agent-browser.exe"),
]


def _find_binary() -> Optional[str]:
    """Return the first existing agent-browser binary path, or *None*."""
    for path in _WELL_KNOWN_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _get_binary() -> str:
    """Return the cached binary path, resolving it lazily on first call."""
    global _BINARY  # noqa: PLW0603
    if _BINARY is None:
        _BINARY = _find_binary()
    if _BINARY is None:
        raise AgentBrowserError(
            "agent-browser.exe not found. "
            "Searched: " + ", ".join(_WELL_KNOWN_PATHS)
        )
    return _BINARY


# ---------------------------------------------------------------------------
# Edge path detection
# ---------------------------------------------------------------------------

_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_edge() -> Optional[str]:
    """Return the path to Edge if installed, or *None*."""
    for path in _EDGE_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Core subprocess runner
# ---------------------------------------------------------------------------

def run(
    *args: str,
    use_json: bool = False,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Run an agent-browser CLI command and return parsed output.

    Parameters
    ----------
    *args:
        Positional arguments passed to the CLI after the binary name.
    use_json:
        Append ``--json`` and parse stdout as JSON.
    timeout:
        Subprocess timeout in seconds.

    Returns
    -------
    dict
        ``{"stdout": str, "stderr": str}`` when *use_json* is False.
        The parsed JSON object when *use_json* is True.

    Raises
    ------
    AgentBrowserError
        On non-zero exit code or JSON-level ``success: false``.
    """
    cmd: List[str] = [_get_binary(), "--session", "edog", *args]
    if use_json:
        cmd.append("--json")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentBrowserError(
            f"agent-browser timed out after {timeout}s: {' '.join(cmd)}"
        ) from exc

    if result.returncode != 0:
        raise AgentBrowserError(
            f"agent-browser exited {result.returncode}\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}\n"
            f"stdout: {result.stdout.strip()}"
        )

    if not use_json:
        return {"stdout": result.stdout, "stderr": result.stderr}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AgentBrowserError(
            f"Failed to parse JSON from agent-browser\n"
            f"stdout: {result.stdout[:500]}"
        ) from exc

    if isinstance(data, dict) and data.get("success") is False:
        error_msg = data.get("error", data.get("message", "unknown error"))
        raise AgentBrowserError(f"agent-browser reported failure: {error_msg}")

    return data


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def open_url(
    url: str,
    *,
    headed: bool = True,
    chrome_args: Optional[List[str]] = None,
    timeout: int = 90,
) -> Dict[str, Any]:
    """Navigate to *url*, opening the browser if needed.

    Uses ``--session-name edog`` for cookie persistence.
    """
    args: List[str] = ["open", url, "--session-name", "edog"]
    if headed:
        args.append("--headed")

    edge = _find_edge()
    if edge:
        args.extend(["--executable-path", edge])

    if chrome_args:
        args.extend(["--args", ",".join(chrome_args)])

    return run(*args, use_json=True, timeout=timeout)


def close_browser() -> Dict[str, Any]:
    """Close the browser session."""
    return run("close", use_json=True)


def connect_cdp(port: int) -> Dict[str, Any]:
    """Connect to a browser via Chrome DevTools Protocol."""
    return run("connect", str(port), use_json=True, timeout=90)


def get_url() -> str:
    """Return the current page URL."""
    data = run("get", "url", use_json=True)
    if isinstance(data, dict) and "data" in data:
        return str(data["data"])
    return str(data)


# ---------------------------------------------------------------------------
# Snapshot / element lookup
# ---------------------------------------------------------------------------

def snapshot_interactive(timeout: int = 60) -> Dict[str, Any]:
    """Return the interactive accessibility snapshot (refs included)."""
    return run("snapshot", "-i", use_json=True, timeout=timeout)


def find_ref(
    snapshot_data: Dict[str, Any],
    *,
    role: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    """Find an element ref in *snapshot_data* by role and/or name.

    Matching is case-insensitive substring.  Returns the first matching
    ref string (e.g. ``"e12"``), or *None*.
    """
    refs = snapshot_data.get("data", {}).get("refs", {})
    if not isinstance(refs, dict):
        return None

    role_lower = role.lower() if role else None
    name_lower = name.lower() if name else None

    for ref_id, info in refs.items():
        if not isinstance(info, dict):
            continue
        ref_role = str(info.get("role", "")).lower()
        ref_name = str(info.get("name", "")).lower()

        if role_lower and role_lower not in ref_role:
            continue
        if name_lower and name_lower not in ref_name:
            continue
        return f"@{ref_id}"

    return None


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------

def click(ref: str, timeout: int = 60) -> Dict[str, Any]:
    """Click on element identified by *ref*."""
    return run("click", ref, use_json=True, timeout=timeout)


def fill(ref: str, value: str, timeout: int = 60) -> Dict[str, Any]:
    """Fill a text field identified by *ref* with *value*."""
    return run("fill", ref, value, use_json=True, timeout=timeout)


def press(key: str, timeout: int = 60) -> Dict[str, Any]:
    """Press a keyboard key (e.g. ``"Enter"``, ``"Tab"``)."""
    return run("press", key, use_json=True, timeout=timeout)


# ---------------------------------------------------------------------------
# Waiting
# ---------------------------------------------------------------------------

def wait_ms(ms: int) -> Dict[str, Any]:
    """Wait for a fixed number of milliseconds."""
    return run("wait", str(ms), use_json=True)


def wait_text(text: str, timeout: int = 60) -> Dict[str, Any]:
    """Wait until *text* appears on the page."""
    return run("wait", "--text", text, use_json=True, timeout=timeout)


def wait_load(state: str = "networkidle", timeout: int = 90) -> Dict[str, Any]:
    """Wait for the page to reach *state* (load, domcontentloaded, networkidle)."""
    return run("wait", "--load", state, use_json=True, timeout=timeout)


def wait_fn(js_expression: str, timeout: int = 60) -> Dict[str, Any]:
    """Wait until a JS expression evaluates to truthy."""
    return run("wait", "--fn", js_expression, use_json=True, timeout=timeout)


# ---------------------------------------------------------------------------
# Network capture
# ---------------------------------------------------------------------------

def get_network_requests(timeout: int = 60) -> Dict[str, Any]:
    """Return captured network requests."""
    return run("network", "requests", use_json=True, timeout=timeout)


def clear_network(timeout: int = 60) -> Dict[str, Any]:
    """Clear captured network requests."""
    return run("network", "requests", "--clear", use_json=True, timeout=timeout)


def extract_bearer_token() -> Optional[str]:
    """Extract a Bearer token from captured network request headers.

    Scans all captured requests for an ``Authorization`` header that
    starts with ``Bearer ey``.  Returns the token value only (without
    the ``Bearer `` prefix), or *None* if not found.
    """
    data = get_network_requests()
    requests_list = (
        data.get("data", {}).get("requests", [])
        if isinstance(data, dict)
        else []
    )
    for req in requests_list:
        headers = req.get("headers", {})
        auth = headers.get("Authorization") or headers.get("authorization")
        if auth and auth.startswith("Bearer ey"):
            return auth[len("Bearer "):]
    return None


# ---------------------------------------------------------------------------
# JavaScript evaluation
# ---------------------------------------------------------------------------

def eval_js(expression: str, timeout: int = 60) -> Dict[str, Any]:
    """Evaluate *expression* in the browser context."""
    return run("eval", expression, use_json=True, timeout=timeout)
