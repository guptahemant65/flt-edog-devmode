"""
EDOG DevMode — FabricLiveTable Development Tool

Automates bearer token management, code patching, and service lifecycle
for local FLT development on EDOG (PPE) environments.

Commands:
  edog                       Start daemon + auto-launch FLT service
  edog --no-launch           Token management only (no service)
  edog --revert              Revert all EDOG code changes
  edog --status              Check if changes are applied
  edog --logs                Open web log viewer in browser
  edog --doctor              Run diagnostic checks
  edog --config              View or update configuration
  edog --install-hook        Install git pre-commit safety hook
  edog --uninstall-hook      Remove git pre-commit hook

Token Architecture:
  - Bearer token (PowerBI API audience) → written to live file → C# service
    reads it to POST /generatemwctoken → generates MWC tokens at runtime
  - UserAuthorizationToken (MwcFrontendBaseEndpoint audience) → injected into
    workload-dev-mode.json → WCL SDK skips browser popup
  - Both tokens acquired via Silent CBA (certificate-based, zero interaction)
  - Auto-refresh daemon monitors both expiries independently
"""

import json
import sys
import os
import re
import base64
import subprocess
import urllib.request
import urllib.error
import uuid
import time
import argparse
import threading
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding for emoji/unicode characters
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# rich — optional, used for polished CLI output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.theme import Theme
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ============================================================================
# UI Abstraction Layer
# ============================================================================
EDOG_VERSION = "3.0.0"

_edog_theme = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "dim": "dim",
    "header": "bold cyan",
    "value": "white",
    "label": "dim cyan",
}) if RICH_AVAILABLE else None

console = Console(theme=_edog_theme) if RICH_AVAILABLE else None


def ui_print(msg, style=None):
    """Print with optional rich styling. Falls back to plain print."""
    if console and style:
        console.print(msg, style=style)
    elif console:
        console.print(msg)
    else:
        # Strip rich markup for plain output
        clean = re.sub(r'\[/?[a-z_ ]+\]', '', str(msg)) if '[' in str(msg) else str(msg)
        print(clean)


def ui_info(msg):
    ui_print(f"  [info]ℹ[/info]  {msg}")

def ui_success(msg):
    ui_print(f"  [success]✔[/success]  {msg}")

def ui_warn(msg):
    ui_print(f"  [warning]⚠[/warning]  {msg}")

def ui_error(msg):
    ui_print(f"  [error]✖[/error]  {msg}")

def ui_step(step_or_msg, total=None, msg=None):
    if total is not None and msg is not None:
        ui_print(f"  [header]\\[{step_or_msg}/{total}][/header] {msg}")
    else:
        ui_print(f"  [header]▸[/header] {step_or_msg}")

def ui_dim(msg):
    ui_print(f"        [dim]{msg}[/dim]")

def ui_log(msg, level="info"):
    """Timestamped log line for daemon output."""
    ts = datetime.now().strftime('%I:%M:%S %p')
    style_map = {"info": "info", "success": "success", "warn": "warning", "error": "error"}
    style = style_map.get(level, "info")
    ui_print(f"  [{style}]{ts}[/{style}]  {msg}")


def show_banner():
    """Display the EDOG banner."""
    if RICH_AVAILABLE:
        banner_text = Text()
        banner_text.append("🐕  EDOG DevMode", style="bold cyan")
        banner_text.append(f"  v{EDOG_VERSION}\n", style="dim")
        banner_text.append("FabricLiveTable Development Tool", style="dim white")
        console.print(Panel(banner_text, border_style="cyan", padding=(0, 2)))
    else:
        print(f"\n  🐕  EDOG DevMode  v{EDOG_VERSION}")
        print(f"  FabricLiveTable Development Tool\n")


def set_terminal_title(title):
    """Set terminal window title via ANSI escape."""
    try:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()
    except Exception:
        pass

def reset_terminal_title():
    """Reset terminal title to default."""
    set_terminal_title("")


def show_config_table(config):
    """Display config as a rich table."""
    # Resolve cert info from username
    cert_cn = config.get('username', '').replace('@', '.')
    cert_tp = _thumbprint_cache.get(cert_cn, '')
    cert_display = f"{cert_cn} ({cert_tp[:8]}...)" if cert_tp else cert_cn or '[dim]unknown[/dim]'
    
    if RICH_AVAILABLE:
        table = Table(show_header=False, border_style="dim", padding=(0, 2))
        table.add_column("Field", style="label", min_width=12)
        table.add_column("Value", style="value")
        table.add_row("Username", config.get('username', DEFAULT_USERNAME + ' [dim](default)[/dim]'))
        table.add_row("Certificate", cert_display)
        table.add_row("Workspace", config.get('workspace_id', '[dim]not set[/dim]'))
        table.add_row("Artifact", config.get('artifact_id', '[dim]not set[/dim]'))
        table.add_row("Capacity", config.get('capacity_id', '[dim]not set[/dim]'))
        table.add_row("FLT Repo", config.get('flt_repo_path', '[dim]auto-detect[/dim]'))
        console.print(table)
    else:
        print(f"   Username:    {config.get('username', DEFAULT_USERNAME + ' (default)')}")
        cert_plain = f"{cert_cn} ({cert_tp[:8]}...)" if cert_tp else cert_cn or 'unknown'
        print(f"   Certificate: {cert_plain}")
        print(f"   Workspace:   {config.get('workspace_id', 'not set')}")
        print(f"   Artifact:    {config.get('artifact_id', 'not set')}")
        print(f"   Capacity:    {config.get('capacity_id', 'not set')}")
        print(f"   FLT Repo:    {config.get('flt_repo_path', 'auto-detect')}")


def ui_status(msg):
    """Context manager for spinner/status. Falls back to simple print."""
    if RICH_AVAILABLE:
        return console.status(f"  {msg}", spinner="dots")
    else:
        class _FallbackStatus:
            def __enter__(self): print(f"  {msg}..."); return self
            def __exit__(self, *a): pass
        return _FallbackStatus()


def ui_prompt(prompt_text, default=None, choices=None, example=None):
    """Styled prompt. Falls back to input()."""
    if example:
        ui_dim(f"  Example: {example}")
    if RICH_AVAILABLE:
        return Prompt.ask(f"  {prompt_text}", default=default, choices=choices)
    else:
        suffix = f" [{default}]" if default else ""
        choice_hint = f" ({'/'.join(choices)})" if choices else ""
        return input(f"  {prompt_text}{choice_hint}{suffix}: ").strip() or default


def ui_confirm(prompt_text, default=True):
    """Styled yes/no confirm. Falls back to input()."""
    if RICH_AVAILABLE:
        return Confirm.ask(f"  {prompt_text}", default=default)
    else:
        yn = "[Y/n]" if default else "[y/N]"
        answer = input(f"  {prompt_text} {yn}: ").strip().lower()
        if not answer:
            return default
        return answer in ('y', 'yes')


def ui_choose(prompt_text, options, show_path=False):
    """Show numbered list and let user pick. Returns selected value."""
    ui_print(f"\n  {prompt_text}")
    for i, opt in enumerate(options, 1):
        display = str(opt) if not show_path else str(opt)
        ui_print(f"    [header]{i}.[/header] {display}")

    while True:
        choice = ui_prompt("Enter number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except (ValueError, IndexError):
            pass
        ui_warn(f"Please enter a number between 1 and {len(options)}")


# ============================================================================
# GUID Validation & URL Extraction
# ============================================================================
GUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)

# Fabric portal URL patterns — field-aware extraction
_FABRIC_URL_PATTERNS = {
    'workspace': re.compile(
        r'(?:app\.fabric\.microsoft\.com|app\.powerbi\.com|app\.fabric\.microsoft\.com/.*?'
        r'|msit\.powerbi\.com|powerbi-df\.analysis-df\.windows-int\.net)'
        r'.*?/groups/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
    ),
    'artifact': re.compile(
        r'(?:lakehouses?|datasets?|notebooks?|warehouses?)'
        r'/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
    ),
}


def validate_guid(value):
    """Validate GUID format. Returns True if valid."""
    return bool(GUID_PATTERN.match(value.strip()))


def try_extract_guid(value, field_name=None):
    """Try to extract a GUID from raw input. Handles:
    - Direct GUID string
    - Fabric portal URL (field-aware extraction)
    - Pasted text containing a GUID
    Returns (guid, source_hint) or (None, error_hint).
    """
    value = value.strip()

    # Direct GUID
    if validate_guid(value):
        return value, None

    # Try field-aware URL extraction
    if '/' in value or 'http' in value.lower():
        if field_name and field_name in _FABRIC_URL_PATTERNS:
            m = _FABRIC_URL_PATTERNS[field_name].search(value)
            if m:
                return m.group(1), f"extracted from URL ({field_name})"

        # Try all patterns
        for fname, pattern in _FABRIC_URL_PATTERNS.items():
            m = pattern.search(value)
            if m:
                return m.group(1), f"extracted from URL ({fname})"

    # Try to find any GUID in the string
    guid_in_text = re.search(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
        value
    )
    if guid_in_text:
        return guid_in_text.group(0), "extracted GUID from text"

    return None, f"expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (got {len(value)} chars)"


def prompt_guid_rich(prompt_text, field_name=None):
    """Prompt for a GUID with validation, URL extraction, and retry."""
    while True:
        value = ui_prompt(prompt_text)
        if not value:
            ui_error(f"{field_name or 'Value'} is required")
            continue

        guid, hint = try_extract_guid(value, field_name=field_name)
        if guid:
            if hint:
                ui_success(f"{hint}: [value]{guid}[/value]")
            return guid

        ui_error(f"Invalid format: {value}")
        ui_dim(hint or "Expected a GUID or Fabric portal URL")
        ui_dim("Tip: paste the Fabric portal URL and I'll extract the ID")


# ============================================================================
# Configuration
# ============================================================================
POWER_BI_URL = "https://powerbi-df.analysis-df.windows.net/"
MWC_TOKEN_ENDPOINT = "https://biazure-int-edog-redirect.analysis-df.windows.net/metadata/v201606/generatemwctoken"

DEFAULT_USERNAME = "Admin1CBA@FabricFMLV07PPE.ccsctp.net"

CONFIG_FILE = "edog-config.json"

CHECK_INTERVAL_MINS = 5
REFRESH_THRESHOLD_MINS = 10
MAX_BROWSER_RETRIES = 3
MWC_LIVE_TOKEN_FILE = ".edog-bearer-live"  # Live bearer token file read by the running service

# API REPL endpoint shortcuts
EDOG_API_ENDPOINTS = {
    "generatemwctoken": ("POST", "https://biazure-int-edog-redirect.analysis-df.windows.net/metadata/v201606/generatemwctoken"),
    "workspaces": ("GET", "https://api.powerbi.com/v1.0/myorg/groups"),
    "capacities": ("GET", "https://api.powerbi.com/v1.0/myorg/capacities"),
}

# File paths relative to repo root
SERVICE_PATH = Path("Service/Microsoft.LiveTable.Service")
FILES = {
    "LiveTableController": SERVICE_PATH / "Controllers/LiveTableController.cs",
    "LiveTableSchedulerRunController": SERVICE_PATH / "Controllers/LiveTableSchedulerRunController.cs",
    "GTSBasedSparkClient": SERVICE_PATH / "SparkHttp/GTSBasedSparkClient.cs",
    "TelemetryReporter": SERVICE_PATH / "Telemetry/CustomLiveTableTelemetryReporter.cs",
    "WorkloadApp": SERVICE_PATH / "WorkloadApp.cs",
    "Program": Path("Service/Microsoft.LiveTable.Service.EntryPoint") / "Program.cs",
    "ParametersManifest": Path("Service/Microsoft.LiveTable.Service.EntryPoint") / "WorkloadParameters/ParametersManifest.json",
    "TestRollout": Path("Service/Microsoft.LiveTable.Service.EntryPoint") / "WorkloadParameters/Rollouts/Test.json",
}

# DevMode log viewer files (created, not patched)
DEVMODE_FILES = {
    "EdogLogServer": SERVICE_PATH / "DevMode/EdogLogServer.cs",
    "EdogApiProxy": SERVICE_PATH / "DevMode/EdogApiProxy.cs",
    "EdogLogModels": SERVICE_PATH / "DevMode/EdogLogModels.cs",
    "EdogLogInterceptor": SERVICE_PATH / "DevMode/EdogLogInterceptor.cs", 
    "EdogTelemetryInterceptor": SERVICE_PATH / "DevMode/EdogTelemetryInterceptor.cs",
    "EdogLogsHtml": SERVICE_PATH / "DevMode/edog-logs.html",
    "EditorConfig": SERVICE_PATH / "DevMode/.editorconfig",
}


# ============================================================================
# Config file management
# ============================================================================
def get_config_path():
    """Get path to config file."""
    return Path(__file__).parent / CONFIG_FILE


def load_config():
    """Load config from file. Returns dict with workspace_id, artifact_id, capacity_id."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            ui_warn(f"Could not load config: {e}")
    return {}


def save_config(config):
    """Save config to file. Also clears token cache since config changes may invalidate it."""
    config_path = get_config_path()
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        # Clear token cache since config changes may invalidate the cached token
        token_cache = Path(__file__).parent / ".edog-token-cache"
        if token_cache.exists():
            token_cache.unlink()
        return True
    except Exception as e:
        ui_error(f"Could not save config: {e}")
        return False


# ============================================================================
# Workload dev mode config sync
# ============================================================================
def get_workload_dev_mode_path(flt_repo_path=None):
    """
    Get path to workload-dev-mode.json by reading launchSettings.json.
    Returns Path or None if not found.
    """
    if not flt_repo_path:
        config = load_config()
        flt_repo_path = config.get("flt_repo_path")
    
    if not flt_repo_path:
        return None
    
    launch_settings = Path(flt_repo_path) / "Service" / "Microsoft.LiveTable.Service.EntryPoint" / "Properties" / "launchSettings.json"
    
    if not launch_settings.exists():
        return None
    
    try:
        with open(launch_settings, 'r') as f:
            settings = json.load(f)
        
        # Extract path from commandLineArgs: -DevMode:LocalConfigFilePath="C:\...\workload-dev-mode.json"
        profiles = settings.get("profiles", {})
        for profile in profiles.values():
            args = profile.get("commandLineArgs", "")
            match = re.search(r'-DevMode:LocalConfigFilePath="([^"]+)"', args)
            if match:
                return Path(match.group(1))
    except Exception:
        pass
    
    return None


def read_workload_dev_mode_config(flt_repo_path=None):
    """
    Read workload-dev-mode.json and return relevant config values.
    Returns dict with capacity_id (mapped from CapacityGuid) or empty dict.
    """
    path = get_workload_dev_mode_path(flt_repo_path)
    if not path or not path.exists():
        return {}
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        result = {}
        if data.get("CapacityGuid"):
            result["capacity_id"] = data["CapacityGuid"]
        if data.get("TenantGuid"):
            result["tenant_id"] = data["TenantGuid"]
        return result
    except Exception:
        return {}


def write_workload_dev_mode_config(capacity_id, flt_repo_path=None):
    """
    Update CapacityGuid in workload-dev-mode.json.
    Returns True if successful, False otherwise.
    """
    path = get_workload_dev_mode_path(flt_repo_path)
    if not path or not path.exists():
        return False
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        data["CapacityGuid"] = capacity_id
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        
        return True
    except Exception as e:
        ui_warn(f"Could not update workload-dev-mode.json: {e}")
        return False


def check_capacity_sync(flt_repo_path=None):
    """
    Check if capacity_id is in sync between edog-config.json and workload-dev-mode.json.
    Returns tuple: (is_synced, edog_value, workload_value, workload_path)
    """
    config = load_config()
    edog_capacity = config.get("capacity_id")
    
    workload_config = read_workload_dev_mode_config(flt_repo_path)
    workload_capacity = workload_config.get("capacity_id")
    
    workload_path = get_workload_dev_mode_path(flt_repo_path)
    
    if not workload_capacity:
        return (True, edog_capacity, None, workload_path)  # No workload file, consider synced
    
    if not edog_capacity:
        return (False, None, workload_capacity, workload_path)  # Edog missing, not synced
    
    is_synced = edog_capacity.lower() == workload_capacity.lower()
    return (is_synced, edog_capacity, workload_capacity, workload_path)


def sync_capacity_from_workload(flt_repo_path=None, silent=False):
    """
    Sync capacity_id from workload-dev-mode.json to edog-config.json.
    Returns the synced capacity_id or None.
    """
    is_synced, edog_val, workload_val, workload_path = check_capacity_sync(flt_repo_path)
    
    if is_synced:
        return edog_val or workload_val
    
    if workload_val:
        config = load_config()
        old_val = config.get("capacity_id")
        config["capacity_id"] = workload_val
        save_config(config)
        
        if not silent:
            ui_info("Synced capacity_id from workload-dev-mode.json")
            if old_val:
                ui_dim(f"Old: {old_val}")
            ui_dim(f"New: {workload_val}")
        
        return workload_val
    
    return edog_val


def validate_guid(value):
    """Validate GUID format. Returns True if valid."""
    guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    return bool(re.match(guid_pattern, value))


def prompt_guid(prompt_text, field_name):
    """Prompt for a GUID with validation, URL extraction, and retry. Delegates to prompt_guid_rich."""
    return prompt_guid_rich(prompt_text, field_name=field_name)


def prompt_for_config(flt_repo_path=None):
    """Prompt user to enter config values. Auto-detects capacity_id from workload-dev-mode.json if available."""
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(
            "[header]First-time setup[/header]\n"
            "[dim]Enter your EDOG environment details.\n"
            "Tip: paste a Fabric portal URL and I'll extract the IDs.[/dim]",
            border_style="cyan", padding=(0, 2)
        ))
    else:
        print("\n📝 First-time setup - please enter your EDOG environment details:")
        print("   (You can find these in Fabric portal URL or workload-dev-mode.json)\n")
    
    username = ui_prompt(f"Username/Email", default=DEFAULT_USERNAME)
    if not username:
        username = DEFAULT_USERNAME
    
    workspace_id = prompt_guid_rich("Workspace ID", field_name="workspace")
    artifact_id = prompt_guid_rich("Artifact ID (Lakehouse)", field_name="artifact")
    
    # Try to auto-detect capacity_id from workload-dev-mode.json
    workload_config = read_workload_dev_mode_config(flt_repo_path)
    detected_capacity = workload_config.get("capacity_id")
    
    if detected_capacity:
        workload_path = get_workload_dev_mode_path(flt_repo_path)
        ui_success(f"Found CapacityGuid in workload-dev-mode.json")
        ui_dim(f"Path: {workload_path}")
        ui_dim(f"Value: {detected_capacity}")
        if ui_confirm("Use this capacity ID?"):
            capacity_id = detected_capacity
            ui_success("Using capacity ID from workload-dev-mode.json")
        else:
            capacity_id = prompt_guid_rich("Capacity ID", field_name=None)
    else:
        capacity_id = prompt_guid_rich("Capacity ID", field_name=None)
    
    return {
        "username": username,
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "capacity_id": capacity_id
    }


def update_config(username=None, workspace_id=None, artifact_id=None, capacity_id=None, flt_repo_path=None):
    """Update specific config values with GUID validation. Also syncs capacity_id to workload-dev-mode.json."""
    config = load_config()
    
    if username:
        config["username"] = username
    if workspace_id:
        valid, cleaned = validate_guid(workspace_id, "workspace_id")
        if not valid:
            return False
        config["workspace_id"] = cleaned
    if artifact_id:
        valid, cleaned = validate_guid(artifact_id, "artifact_id")
        if not valid:
            return False
        config["artifact_id"] = cleaned
    if capacity_id:
        valid, cleaned = validate_guid(capacity_id, "capacity_id")
        if not valid:
            return False
        config["capacity_id"] = cleaned
        # Also update workload-dev-mode.json for bidirectional sync
        if write_workload_dev_mode_config(cleaned, config.get("flt_repo_path")):
            ui_info("Also updated CapacityGuid in workload-dev-mode.json")
    if flt_repo_path:
        # Validate the path
        repo_path = Path(flt_repo_path).resolve()
        if (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            config["flt_repo_path"] = str(repo_path)
        else:
            ui_error(f"Invalid FLT repo path: {repo_path}")
            ui_dim("Expected to find: Service/Microsoft.LiveTable.Service")
            return False
    
    if save_config(config):
        ui_success("Config updated")
        show_config_table(config)
        return True
    return False


def ensure_config():
    """Ensure config exists, prompt user if not. Also syncs capacity_id from workload-dev-mode.json."""
    config = load_config()
    
    # First, try to sync capacity_id from workload-dev-mode.json if flt_repo_path is set
    if config.get("flt_repo_path"):
        sync_capacity_from_workload(config.get("flt_repo_path"), silent=False)
        config = load_config()  # Reload after potential sync
    
    if not config.get("workspace_id") or not config.get("artifact_id") or not config.get("capacity_id"):
        config = prompt_for_config(config.get("flt_repo_path"))
        if not config:
            return None
        if not save_config(config):
            return None
        ui_success("Config saved to edog-config.json")
    
    return config


def show_config():
    """Display current config with sync status using rich table."""
    config = load_config()
    if not config:
        ui_warn("No config found. Run 'edog' to set up.")
        return

    ui_step("Current EDOG Config")
    show_config_table(config)
    ui_dim(f"Config file: {get_config_path()}")

    # Check sync status with workload-dev-mode.json
    is_synced, edog_val, workload_val, workload_path = check_capacity_sync(config.get("flt_repo_path"))
    if workload_path and workload_path.exists():
        ui_dim(f"workload-dev-mode.json: {workload_path}")
        if is_synced:
            ui_success("Capacity ID is in sync")
        else:
            ui_warn("Capacity ID OUT OF SYNC:")
            ui_dim(f"  edog-config.json:       {edog_val or 'not set'}")
            ui_dim(f"  workload-dev-mode.json: {workload_val or 'not set'}")
            ui_dim("  Run 'edog' to auto-sync from workload-dev-mode.json")

# ============================================================================
# Smart Pattern Matching (Anchor-Based Fuzzy Matching)
# ============================================================================

SMART_PATTERNS = {
    # Each pattern has:
    #   anchor: The key identifier to find (whitespace-flexible)
    #   context: Nearby text that must exist to validate location
    #   context_distance: Max lines between anchor and context
    #   action: "wrap_ifdef" or "replace_line"
    #   description: Human-readable description
    
    # Auth bypass patches removed — DisableFLTAuth config flag handles this globally now.
}

def normalize_whitespace(text):
    """Normalize whitespace for flexible matching."""
    return ' '.join(text.split())

def find_anchor_line(lines, anchor):
    """Find line number containing the anchor (whitespace-flexible)."""
    normalized_anchor = normalize_whitespace(anchor)
    for i, line in enumerate(lines):
        if normalized_anchor in normalize_whitespace(line):
            return i
    return -1

def validate_context(lines, anchor_line, context, max_distance):
    """Check if context exists within max_distance lines of anchor."""
    normalized_context = normalize_whitespace(context).lower()
    start = max(0, anchor_line - max_distance)
    end = min(len(lines), anchor_line + max_distance + 1)
    
    for i in range(start, end):
        if normalized_context in normalize_whitespace(lines[i]).lower():
            return True
    return False

def is_already_wrapped(lines, anchor_line):
    """Check if the anchor line is already wrapped with #if EDOG_DEVMODE."""
    if anchor_line <= 0:
        return False
    prev_line = lines[anchor_line - 1].strip()
    return prev_line.startswith("#if EDOG_DEVMODE")

def apply_smart_pattern(content, pattern_config):
    """
    Apply pattern using smart anchor-based matching.
    Returns (new_content, status) where status is:
      - "applied": Successfully applied
      - "already_applied": Already wrapped
      - "anchor_not_found": Anchor text not found
      - "context_mismatch": Anchor found but context validation failed
    """
    lines = content.split('\n')
    anchor = pattern_config["anchor"]
    context = pattern_config["context"]
    max_distance = pattern_config["context_distance"]
    
    # Find anchor
    anchor_line = find_anchor_line(lines, anchor)
    if anchor_line == -1:
        return content, "anchor_not_found"
    
    # Validate context
    if not validate_context(lines, anchor_line, context, max_distance):
        return content, "context_mismatch"
    
    # Check if already applied
    if is_already_wrapped(lines, anchor_line):
        return content, "already_applied"
    
    # Apply wrap_ifdef
    original_line = lines[anchor_line]
    indent = len(original_line) - len(original_line.lstrip())
    indent_str = original_line[:indent]
    
    wrapped = f"#if EDOG_DEVMODE  // EDOG DevMode - disabled\n{original_line}\n{indent_str}#endif"
    lines[anchor_line] = wrapped
    
    return '\n'.join(lines), "applied"

def revert_smart_pattern(content, pattern_config):
    """
    Revert a smart pattern by removing #if EDOG_DEVMODE wrapper.
    Returns (new_content, was_reverted)
    """
    lines = content.split('\n')
    anchor = pattern_config["anchor"]
    
    # Find anchor
    anchor_line = find_anchor_line(lines, anchor)
    if anchor_line == -1:
        return content, False
    
    # Check if wrapped
    if not is_already_wrapped(lines, anchor_line):
        return content, False
    
    # Find #endif after anchor
    endif_line = -1
    for i in range(anchor_line + 1, min(len(lines), anchor_line + 3)):
        if lines[i].strip().startswith("#endif"):
            endif_line = i
            break
    
    if endif_line == -1:
        return content, False
    
    # Remove the wrapper lines
    del lines[endif_line]  # Remove #endif first (so indices don't shift)
    del lines[anchor_line - 1]  # Remove #if EDOG_DEVMODE
    
    return '\n'.join(lines), True

def check_smart_pattern_status(content, pattern_config):
    """
    Check if a smart pattern is applied.
    Returns: "applied", "not_applied", "anchor_not_found", or "context_mismatch"
    """
    lines = content.split('\n')
    anchor = pattern_config["anchor"]
    context = pattern_config["context"]
    max_distance = pattern_config["context_distance"]
    
    anchor_line = find_anchor_line(lines, anchor)
    if anchor_line == -1:
        return "anchor_not_found"
    
    if not validate_context(lines, anchor_line, context, max_distance):
        return "context_mismatch"
    
    if is_already_wrapped(lines, anchor_line):
        return "applied"
    
    return "not_applied"


# ============================================================================
# Legacy Patterns — auth bypass entries removed (DisableFLTAuth config flag handles this globally now)
PATTERNS = {
}


# ============================================================================
# EDOG change management
# ============================================================================



# ============================================================================
# Token utilities
# ============================================================================
def parse_jwt_expiry(token):
    """Extract expiry datetime from JWT token."""
    try:
        # JWT format: header.payload.signature
        payload = token.split('.')[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        exp_timestamp = decoded.get('exp')
        if exp_timestamp:
            return datetime.fromtimestamp(exp_timestamp)
    except Exception as e:
        ui_warn(f"Could not parse token expiry: {e}")
    return None


def get_token_time_remaining(expiry):
    """Get remaining time until token expires."""
    if not expiry:
        return None
    return expiry - datetime.now()


def format_timedelta(td):
    """Format timedelta for display."""
    if not td:
        return "unknown"
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "EXPIRED"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


# ============================================================================
# File modification utilities
# ============================================================================
def find_flt_repo():
    """Search for FabricLiveTable repo across targeted roots on C: and Q: drives.
    
    Returns a list of all found repos (caller decides chooser UX).
    Uses targeted candidate roots for speed — NOT full drive crawl.
    """
    # Signature: repo must contain Service/Microsoft.LiveTable.Service
    def is_flt_repo(path):
        try:
            return (path / "Service" / "Microsoft.LiveTable.Service").exists()
        except (PermissionError, OSError):
            return False
    
    skip_dirs = {'.git', '.vs', '.vscode', 'node_modules', '__pycache__', 'bin', 'obj', 
                 'packages', 'AppData', '.nuget', '.dotnet', '.azure', 'OneDrive'}
    
    found_repos = []
    
    def search_dir(start_path, max_depth, current_depth=0):
        if current_depth > max_depth:
            return
        try:
            for entry in start_path.iterdir():
                try:
                    if not entry.is_dir():
                        continue
                except (PermissionError, OSError):
                    continue
                if entry.name.startswith('.') or entry.name in skip_dirs:
                    continue
                if is_flt_repo(entry):
                    found_repos.append(entry)
                    continue  # Don't recurse into a found repo
                search_dir(entry, max_depth, current_depth + 1)
        except (PermissionError, OSError):
            pass
    
    # Build candidate roots: user home, common dev dirs on C: and Q:
    home = Path.home()
    candidate_roots = [home]
    for drive in ["C:", "Q:"]:
        drive_path = Path(f"{drive}\\")
        if not drive_path.exists():
            continue
        for subdir in ["src", "repos", "dev", "projects", "code", "work", "git",
                        "Users", "enlistments"]:
            candidate = drive_path / subdir
            if candidate.exists() and candidate != home:
                candidate_roots.append(candidate)
    
    ui_dim("Scanning for FLT repos...")
    for root in candidate_roots:
        search_dir(root, max_depth=4)
    
    # Deduplicate by resolved path
    seen = set()
    unique = []
    for r in found_repos:
        resolved = str(r.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(r)
    
    return unique


def get_repo_root():
    """Get FLT repository root directory from config or auto-detect with chooser."""
    config = load_config()
    
    # First, check config for explicit repo path
    if config.get("flt_repo_path"):
        repo_path = Path(config["flt_repo_path"])
        if repo_path.exists() and (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            return repo_path
        else:
            ui_warn(f"Configured FLT repo path no longer valid: {repo_path}")
            ui_dim("Update with: edog --config -r <new_path>")
    
    # Try current working directory
    cwd = Path.cwd()
    if (cwd / "Service" / "Microsoft.LiveTable.Service").exists():
        return cwd
    
    # Try parent directories (in case running from subdirectory)
    for parent in cwd.parents:
        if (parent / "Service" / "Microsoft.LiveTable.Service").exists():
            return parent
    
    # Auto-search common locations (returns list)
    repos = find_flt_repo()
    
    if len(repos) == 1:
        chosen = repos[0]
        if ui_confirm(f"Found FLT repo: {chosen}", default=True):
            config["flt_repo_path"] = str(chosen)
            save_config(config)
            ui_success(f"Saved FLT repo path: {chosen}")
            return chosen
    elif len(repos) > 1:
        ui_info(f"Found {len(repos)} FLT repos:")
        options = [str(r) for r in repos]
        chosen_path = ui_choose("Select repo", options)
        if chosen_path:
            chosen = Path(chosen_path)
            config["flt_repo_path"] = str(chosen)
            save_config(config)
            ui_success(f"Saved FLT repo path: {chosen}")
            return chosen
    
    # Not found — prompt user for path with example
    ui_warn("FabricLiveTable repo not found automatically.")
    
    while True:
        repo_input = ui_prompt(
            "FLT Repo Path",
            default="",
            example=r"C:\Users\you\repos\workload-fabriclivetable"
        )
        if not repo_input:
            return None
        
        repo_path = Path(repo_input).resolve()
        if not repo_path.exists():
            ui_error(f"Path does not exist: {repo_path}")
            continue
        if not (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            ui_error("Not a valid FLT repo (missing Service/Microsoft.LiveTable.Service)")
            continue
        
        # Valid path - save to config
        config["flt_repo_path"] = str(repo_path)
        save_config(config)
        ui_success(f"Saved FLT repo path: {repo_path}")
        return repo_path


def read_file(filepath):
    """Read file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except PermissionError:
        ui_error(f"File is locked: {filepath.name}")
        ui_dim("Close the file in Visual Studio/VS Code and retry")
        return None
    except FileNotFoundError:
        ui_error(f"File not found: {filepath}")
        ui_dim("Check if FLT repo path is correct: edog --config")
        return None
    except Exception as e:
        ui_error(f"Error reading {filepath.name}: {e}")
        return None


def write_file(filepath, content):
    """Write file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except PermissionError:
        ui_error(f"File is locked: {filepath.name}")
        ui_dim("Close the file in Visual Studio/VS Code and retry")
        return False
    except Exception as e:
        ui_error(f"Error writing {filepath.name}: {e}")
        return False


# ============================================================================
# Git safety checks
# ============================================================================
def check_git_status(repo_root):
    """Check if EDOG-modified files have uncommitted changes. Returns list of dirty files."""
    dirty_files = []
    
    try:
        # Get list of modified/staged files
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []  # Git not available or not a repo, skip check
        
        # Check if any EDOG-managed files are in the dirty list
        edog_files = [str(f).replace("\\", "/") for f in FILES.values()]
        
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Git status format: "XY filename" where X=staged, Y=unstaged
            file_path = line[3:].strip().replace("\\", "/")
            for edog_file in edog_files:
                if file_path.endswith(edog_file) or edog_file.endswith(file_path):
                    dirty_files.append(file_path)
                    break
    
    except Exception:
        pass  # If git check fails, don't block the user
    
    return dirty_files


def warn_uncommitted_edog_changes(repo_root):
    """Print warning if EDOG changes are uncommitted."""
    dirty_files = check_git_status(repo_root)
    
    if dirty_files:
        ui_warn("EDOG-modified files have uncommitted changes!")
        ui_dim("Don't commit these files with EDOG changes.")
        ui_dim("Run 'edog --revert' before committing.")
        for f in dirty_files:
            ui_dim(f"  • {f}")
        return True
    return False


def install_git_hook(repo_root):
    """Install a pre-commit hook that blocks commits with EDOG changes."""
    hooks_dir = repo_root / ".git" / "hooks"
    hook_file = hooks_dir / "pre-commit"
    
    if not hooks_dir.exists():
        ui_error(f"Git hooks directory not found: {hooks_dir}")
        return False
    
    # Hook script content
    hook_script = '''#!/bin/sh
# EDOG DevMode pre-commit hook
# Prevents accidental commits of EDOG-modified files

# Files that EDOG modifies
EDOG_FILES="LiveTableController.cs LiveTableSchedulerRunController.cs GTSBasedSparkClient.cs"

# Check if any EDOG files are staged
for file in $EDOG_FILES; do
    if git diff --cached --name-only | grep -q "$file"; then
        # Check if file contains EDOG markers
        if git diff --cached -- "*$file" | grep -q "EDOG DevMode"; then
            echo ""
            echo "COMMIT BLOCKED: EDOG DevMode changes detected!"
            echo ""
            echo "   File: $file contains EDOG modifications."
            echo "   Run 'edog --revert' before committing."
            echo ""
            exit 1
        fi
    fi
done

exit 0
'''
    
    # Check if hook already exists
    if hook_file.exists():
        existing = hook_file.read_text(encoding='utf-8', errors='ignore')
        if "EDOG DevMode pre-commit hook" in existing:
            ui_success("EDOG pre-commit hook already installed")
            return True
        else:
            # Backup existing hook
            backup = hook_file.with_suffix(".pre-edog-backup")
            hook_file.rename(backup)
            ui_dim(f"Backed up existing hook to: {backup.name}")
    
    try:
        hook_file.write_text(hook_script, encoding='utf-8')
        # Make executable (on Unix)
        import stat
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IEXEC)
        ui_success("Installed EDOG pre-commit hook")
        ui_dim(f"Location: {hook_file}")
        ui_dim("Commits with EDOG changes will now be blocked.")
        return True
    except Exception as e:
        ui_error(f"Failed to install hook: {e}")
        return False


def uninstall_git_hook(repo_root):
    """Remove the EDOG pre-commit hook."""
    hook_file = repo_root / ".git" / "hooks" / "pre-commit"
    
    if not hook_file.exists():
        ui_dim("No pre-commit hook found")
        return True
    
    content = hook_file.read_text()
    if "EDOG DevMode pre-commit hook" not in content:
        ui_dim("Pre-commit hook exists but is not EDOG's hook")
        return False
    
    try:
        hook_file.unlink()
        ui_success("Removed EDOG pre-commit hook")
        
        # Restore backup if exists
        backup = hook_file.with_suffix(".pre-edog-backup")
        if backup.exists():
            backup.rename(hook_file)
            ui_dim("Restored previous hook from backup")
        
        return True
    except Exception as e:
        ui_error(f"Failed to remove hook: {e}")
        return False


# ============================================================================
# Patch-based change management
# ============================================================================
def get_patch_file_path():
    """Get path to EDOG changes patch file."""
    return Path(__file__).parent / ".edog-changes.patch"


def generate_patch(original_contents, modified_contents, repo_root):
    """
    Generate a unified diff patch file for all EDOG changes.
    
    Args:
        original_contents: dict of {relative_path: original_content}
        modified_contents: dict of {relative_path: modified_content}
        repo_root: Path to the FLT repository root
    
    Returns:
        True if patch was generated, False otherwise
    """
    import difflib
    
    patch_lines = []
    
    for rel_path in original_contents:
        if rel_path not in modified_contents:
            continue
        
        original = original_contents[rel_path]
        modified = modified_contents[rel_path]
        
        if original == modified:
            continue  # No changes for this file
        
        # Generate unified diff
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        # Ensure last line has newline for proper patch format
        if original_lines and not original_lines[-1].endswith('\n'):
            original_lines[-1] += '\n'
        if modified_lines and not modified_lines[-1].endswith('\n'):
            modified_lines[-1] += '\n'
        
        # Use forward slashes for git compatibility
        git_path = str(rel_path).replace('\\', '/')
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{git_path}",
            tofile=f"b/{git_path}",
            lineterm='\n'
        )
        
        patch_lines.extend(diff)
    
    if not patch_lines:
        return False
    
    # Write patch file
    patch_path = get_patch_file_path()
    try:
        patch_content = ''.join(patch_lines)
        patch_path.write_text(patch_content, encoding='utf-8')
        return True
    except Exception as e:
        ui_error(f"Failed to write patch file: {e}")
        return False


def apply_patch_reverse(repo_root):
    """
    Revert EDOG changes by applying the patch in reverse.
    Handles edge case where user edited files after applying EDOG changes.
    
    Returns:
        (success: bool, message: str)
    """
    patch_path = get_patch_file_path()
    
    if not patch_path.exists():
        return False, "No patch file found - EDOG changes may not have been applied or were already reverted"
    
    try:
        # First, check if patch applies cleanly
        check_result = subprocess.run(
            ['git', 'apply', '-R', '--check', '--whitespace=nowarn', str(patch_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if check_result.returncode == 0:
            # Patch applies cleanly - go ahead
            result = subprocess.run(
                ['git', 'apply', '-R', '--whitespace=nowarn', str(patch_path)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                patch_path.unlink()
                return True, "Successfully reverted all EDOG changes"
            else:
                return False, f"Failed to apply patch: {result.stderr.strip()}"
        
        else:
            # Patch doesn't apply cleanly - files were modified
            ui_warn("Files were modified after EDOG changes were applied.")
            ui_dim("Attempting 3-way merge to preserve your changes...")
            
            # Try with --3way to do a 3-way merge
            result = subprocess.run(
                ['git', 'apply', '-R', '--3way', '--whitespace=nowarn', str(patch_path)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                patch_path.unlink()
                return True, "Successfully reverted EDOG changes (merged with your edits)"
            
            # 3-way merge failed - check for conflicts
            if "conflict" in result.stderr.lower() or "conflict" in result.stdout.lower():
                return False, (
                    "Merge conflicts detected. Your edits conflict with EDOG changes.\n"
                    "      Options:\n"
                    "        1. Resolve conflicts manually in the affected files\n"
                    "        2. Run 'git checkout -- <file>' to discard ALL changes (including yours)\n"
                    f"        3. Delete patch file manually: {patch_path}"
                )
            
            # Check if changes are already reverted
            if "patch does not apply" in check_result.stderr.lower():
                patch_path.unlink()
                return True, "EDOG changes already reverted (or files were manually restored)"
            
            return False, f"Failed to revert: {result.stderr.strip() or check_result.stderr.strip()}"
    
    except subprocess.TimeoutExpired:
        return False, "Git apply timed out"
    except FileNotFoundError:
        return False, "Git not found - please ensure git is installed and in PATH"
    except Exception as e:
        return False, f"Error applying patch: {e}"


def has_pending_edog_changes():
    """Check if there are unapplied EDOG changes (patch file exists)."""
    return get_patch_file_path().exists()


# ============================================================================
# Token caching
# ============================================================================
def get_token_cache_path():
    """Get path to cached token file."""
    return Path(__file__).parent / ".edog-token-cache"


def cache_token(token, expiry_timestamp):
    """Save token to cache file (simple obfuscation, not encryption)."""
    import base64
    
    cache_path = get_token_cache_path()
    try:
        # Simple obfuscation (base64) - not secure, just prevents casual viewing
        data = f"{expiry_timestamp}|{token}"
        encoded = base64.b64encode(data.encode()).decode()
        cache_path.write_text(encoded)
        return True
    except Exception:
        return False


def load_cached_token():
    """Load token from cache if still valid. Returns (token, expiry) or (None, None)."""
    import base64
    
    cache_path = get_token_cache_path()
    if not cache_path.exists():
        return None, None
    
    try:
        encoded = cache_path.read_text()
        data = base64.b64decode(encoded.encode()).decode()
        expiry_str, token = data.split("|", 1)
        expiry_timestamp = float(expiry_str)
        
        # Check if token is still valid (with 5 min buffer)
        if time.time() < expiry_timestamp - 300:
            expiry = datetime.fromtimestamp(expiry_timestamp)
            return token, expiry
        else:
            # Token expired, delete cache
            cache_path.unlink()
            return None, None
    except Exception:
        # Corrupted cache, delete it
        try:
            cache_path.unlink()
        except:
            pass
        return None, None


def clear_token_cache():
    """Delete cached token."""
    cache_path = get_token_cache_path()
    if cache_path.exists():
        cache_path.unlink()


# ============================================================================
# Bearer token caching (for Silent CBA tokens)
# ============================================================================
def get_bearer_cache_path(cache_dir: Path | None = None) -> Path:
    """Get path to the bearer token cache file."""
    base = cache_dir if cache_dir is not None else Path(__file__).parent
    return base / ".edog-bearer-cache"


def cache_bearer_token(token: str, expiry_timestamp: float, cache_dir: Path | None = None) -> bool:
    """Save bearer token to a dedicated cache file."""
    cache_path = get_bearer_cache_path(cache_dir)
    try:
        data = f"{expiry_timestamp}|{token}"
        encoded = base64.b64encode(data.encode()).decode()
        cache_path.write_text(encoded, encoding="utf-8")
        return True
    except OSError as e:
        ui_warn(f"Could not cache bearer token: {e}")
        return False


def load_cached_bearer_token(cache_dir: Path | None = None) -> tuple:
    """Load bearer token from cache if still valid (5-min safety buffer).
    Returns (token, expiry_datetime) or (None, None).
    """
    cache_path = get_bearer_cache_path(cache_dir)
    if not cache_path.exists():
        return None, None

    try:
        encoded = cache_path.read_text(encoding="utf-8")
        data = base64.b64decode(encoded.encode()).decode()
        expiry_str, token = data.split("|", 1)
        expiry_timestamp = float(expiry_str)

        if time.time() < expiry_timestamp - 300:
            expiry = datetime.fromtimestamp(expiry_timestamp)
            return token, expiry
        else:
            cache_path.unlink(missing_ok=True)
            return None, None
    except (OSError, ValueError, UnicodeDecodeError):
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None, None


# ============================================================================
# Live bearer token file (read by the C# service to generate MWC tokens)
# ============================================================================
def get_bearer_live_path(workspace_id=None):
    """Get path to the live bearer token file.
    
    Scoped per workspace to avoid collisions if multiple edog instances run.
    """
    suffix = f"-{workspace_id[:8]}" if workspace_id else ""
    return Path.home() / f"{MWC_LIVE_TOKEN_FILE}{suffix}"


def write_bearer_live_token(token, expiry_timestamp=None, workspace_id=None):
    """Write bearer token to the live file atomically.
    
    Uses temp-file + rename to prevent partial reads by the C# service.
    Format: token_string|unix_timestamp
    """
    if not token:
        return False
    live_path = get_bearer_live_path(workspace_id)
    data = f"{token}|{int(expiry_timestamp)}" if expiry_timestamp is not None else token
    try:
        tmp_path = live_path.with_suffix('.tmp')
        tmp_path.write_text(data, encoding='utf-8')
        tmp_path.replace(live_path)
        ui_dim(f"Live bearer written to {live_path.name}")
        return True
    except OSError as e:
        ui_warn(f"Failed to write live bearer: {e}")
        return False


def cleanup_bearer_live_token(workspace_id=None):
    """Remove the live bearer token file."""
    live_path = get_bearer_live_path(workspace_id)
    try:
        live_path.unlink(missing_ok=True)
        live_path.with_suffix('.tmp').unlink(missing_ok=True)
    except OSError:
        pass


# ============================================================================
# Desktop notifications
# ============================================================================
def show_notification(title, message):
    """Show a Windows toast notification."""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5, threaded=True)
        return True
    except ImportError:
        # win10toast not installed, try PowerShell fallback
        try:
            import subprocess
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            $template = "<toast><visual><binding template='ToastText02'><text id='1'>{title}</text><text id='2'>{message}</text></binding></visual></toast>"
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("EDOG DevMode").Show($toast)
            '''
            subprocess.run(["powershell", "-Command", ps_script], 
                         capture_output=True, timeout=5)
            return True
        except Exception:
            pass
    except Exception:
        pass
    return False


# ============================================================================
# EDOG change management
# ============================================================================
def apply_simple_pattern(content, original, modified, description):
    """Apply a simple pattern replacement. Returns (new_content, was_changed, was_already_applied)."""
    if modified in content:
        return content, False, True  # Already applied
    if original in content:
        return content.replace(original, modified, 1), True, False  # Applied now
    return content, False, False  # Pattern not found


def revert_simple_pattern(content, original, modified, description):
    """Revert a simple pattern replacement. Returns (new_content, was_reverted)."""
    if modified in content:
        return content.replace(modified, original, 1), True
    return content, False



def get_gts_spark_client_bypass(bearer_file_path, mwc_endpoint):
    """Get the bypass code for GTSBasedSparkClient (bearer file → MWC generation).
    
    The generated C# reads a bearer token from a file on disk, then calls
    the metadata endpoint to generate an MWC token. The caller (GetMWCV1Token...)
    already handles caching and auto-renewal via IsNullOrExpiringSoon.
    """
    bypass_code = f'''        protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)
        {{
            // EDOG DevMode - reads bearer from file, generates MWC via metadata endpoint
            // Bearer file is kept fresh by the edog Python daemon (Silent CBA)
            // MWC auto-renewal is handled by the caller's IsNullOrExpiringSoon check
            var bearerFilePath = @"{bearer_file_path}";
            try
            {{
                // Step 1: Read bearer token from file (written atomically by edog daemon)
                string bearerData;
                try
                {{
                    bearerData = System.IO.File.ReadAllText(bearerFilePath).Trim();
                }}
                catch (System.IO.IOException) when (!ct.IsCancellationRequested)
                {{
                    await Task.Delay(100, ct);
                    bearerData = System.IO.File.ReadAllText(bearerFilePath).Trim();
                }}

                var bearerParts = bearerData.Split('|');
                var bearer = bearerParts[0];
                if (string.IsNullOrWhiteSpace(bearer))
                {{
                    throw new InvalidOperationException("Bearer token file is empty");
                }}

                // Step 2: Call metadata endpoint to generate MWC token
                var capacityContext = CustomerCapacityAsyncLocalContext.Value;
                var capacityId = capacityContext?.CustomerCapacityObjectId ?? string.Empty;

                var requestBody = $@"{{{{""capacityObjectId"":""{{capacityId}}"",""workspaceObjectId"":""{{this.workspaceId}}"",""workloadType"":""Lakehouse"",""artifactObjectIds"":[""{{this.artifactId}}""]}}}}";

                using var httpClient = new System.Net.Http.HttpClient();
                httpClient.DefaultRequestHeaders.Authorization =
                    new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", bearer);

                var response = await httpClient.PostAsync(
                    "{mwc_endpoint}",
                    new System.Net.Http.StringContent(requestBody, System.Text.Encoding.UTF8, "application/json"),
                    ct);
                response.EnsureSuccessStatusCode();

                var responseJson = await response.Content.ReadAsStringAsync();
                var mwcTokenObj = Newtonsoft.Json.JsonConvert.DeserializeObject<dynamic>(responseJson);
                string mwcToken = mwcTokenObj.token;

                if (string.IsNullOrWhiteSpace(mwcToken))
                {{
                    throw new InvalidOperationException("MWC token generation returned empty token");
                }}

                // Step 3: Parse expiry from bearer (use bearer expiry as upper bound)
                var expiry = bearerParts.Length > 1 && long.TryParse(bearerParts[1], out var ts)
                    ? DateTimeOffset.FromUnixTimeSeconds(ts)
                    : DateTimeOffset.UtcNow.AddHours(1);

                Tracer.LogSanitizedWarning($"[DevMode] Generated MWC token from bearer file, expiry: {{expiry:HH:mm:ss}}");
                return new Token
                {{
                    Value = mwcToken,
                    Expiry = expiry,
                }};
            }}
            catch (Exception ex)
            {{
                Tracer.LogSanitizedError(ex, "[DevMode] Failed to generate MWC token from bearer file");
                throw new InvalidOperationException(
                    $"EDOG DevMode: Cannot generate MWC token. Ensure edog daemon is running and bearer file exists at {{bearerFilePath}}.", ex);
            }}
        }}'''
    return bypass_code



def apply_gts_spark_client_change(content, repo_root=None, workspace_id=None):
    """Apply GTSBasedSparkClient bypass (file-based token reading). Returns (new_content, status).
    
    Handles 3 cases:
    - New file-based marker present → already applied, skip
    - Old hardcoded marker present → upgrade to file-based
    - No marker → fresh apply
    """
    file_marker = '// EDOG DevMode - bypassing OBO token exchange (file-based'
    old_marker = '// EDOG DevMode - bypassing OBO token exchange (hardcoded'
    original_marker_start = '// EDOG_ORIGINAL_START:'
    
    # Case 1: Already has file-based bypass
    if file_marker in content:
        return content, "already_applied"
    
    # Case 2: Has old hardcoded bypass → strip it first, then apply fresh
    if old_marker in content:
        content, reverted = revert_gts_spark_client_change(content, repo_root)
        if not reverted:
            return content, "upgrade_failed"
        ui_dim("Upgrading from hardcoded to file-based bypass")
    
    # Case 3: Fresh apply — find the method and replace
    method_sig = 'protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)'
    if method_sig not in content:
        return content, "pattern_not_found"
    
    sig_start = content.find(method_sig)
    if sig_start == -1:
        return content, "pattern_not_found"
    
    brace_start = content.find('{', sig_start)
    if brace_start == -1:
        return content, "pattern_not_found"
    
    brace_count = 1
    pos = brace_start + 1
    while pos < len(content) and brace_count > 0:
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1
    
    if brace_count != 0:
        return content, "pattern_not_found"
    
    method_end = pos
    
    # Find start of method block (include preceding comments/attributes)
    line_start = content.rfind('\n', 0, sig_start) + 1
    method_start = line_start
    while method_start > 0:
        prev_line_end = method_start - 1
        if prev_line_end < 0:
            break
        prev_line_start = content.rfind('\n', 0, prev_line_end) + 1
        prev_line = content[prev_line_start:prev_line_end].strip()
        if prev_line.startswith('//') or prev_line.startswith('/*') or prev_line.startswith('*') or prev_line.startswith('['):
            method_start = prev_line_start
        else:
            break
    
    # Store original as base64 for safe revert
    original_content = content[method_start:method_end]
    original_encoded = base64.b64encode(original_content.encode('utf-8')).decode('ascii')
    
    # Get the bearer file path and MWC endpoint for this workspace
    bearer_file_path = get_bearer_live_path(workspace_id)
    bypass_body = get_gts_spark_client_bypass(bearer_file_path, MWC_TOKEN_ENDPOINT)
    
    bypass_code = f'''        // EDOG_ORIGINAL_START:{original_encoded}
{bypass_body}'''
    
    new_content = content[:method_start] + bypass_code + content[method_end:]
    return new_content, "applied"


def revert_gts_spark_client_change(content, repo_root=None):
    """Revert GTSBasedSparkClient bypass - restore original method from stored backup or git.
    
    Handles both old (hardcoded) and new (file-based) bypass markers.
    """
    original_marker_start = '// EDOG_ORIGINAL_START:'
    # Detect ANY EDOG bypass — check for stored original OR comment markers
    edog_markers = [
        original_marker_start,
        '// EDOG DevMode',
        'EDOG DevMode:',
    ]
    
    if not any(m in content for m in edog_markers):
        return content, False
    
    # Try to restore from stored original (base64 on same line as EDOG_ORIGINAL_START:)
    if original_marker_start in content:
        marker_pos = content.find(original_marker_start)
        encoded_start = marker_pos + len(original_marker_start)
        encoded_end = content.find('\n', encoded_start)
        if encoded_end == -1:
            encoded_end = len(content)
        encoded_original = content[encoded_start:encoded_end].strip()
        
        try:
            original_content = base64.b64decode(encoded_original.encode('ascii')).decode('utf-8')
            marker_line_start = content.rfind('\n', 0, marker_pos) + 1
            
            method_sig = 'protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)'
            sig_start = content.find(method_sig, marker_line_start)
            if sig_start == -1:
                return content, False
            
            brace_start = content.find('{', sig_start)
            if brace_start == -1:
                return content, False
            
            brace_count = 1
            pos = brace_start + 1
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            if brace_count != 0:
                return content, False
            
            method_end = pos
            new_content = content[:marker_line_start] + original_content + content[method_end:]
            return new_content, True
            
        except Exception as e:
            ui_warn(f"Failed to decode stored original: {e}")
    
    # No stored original - try to restore from git
    if repo_root:
        try:
            file_rel_path = str(FILES["GTSBasedSparkClient"]).replace('\\', '/')
            result = subprocess.run(
                ['git', 'show', f'HEAD:{file_rel_path}'],
                cwd=str(repo_root),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                ui_dim("Restored from git HEAD (no stored original found)")
                return result.stdout, True
            else:
                ui_warn(f"Git show failed: {result.stderr.strip()}")
        except Exception as e:
            ui_warn(f"Could not restore from git: {e}")
    
    ui_warn("No stored original found. Please manually revert GTSBasedSparkClient.cs.")
    return content, False


# ============================================================================
# Telemetry Console Output (included in patch for easy revert)
# ============================================================================
TELEMETRY_CONSOLE_CODE = '''
            // EDOG DevMode - Console telemetry output
            var edogCorrelationId = string.IsNullOrEmpty(correlationId) ? MonitoredScope.RootActivityId.ToString() : correlationId;
            Console.ForegroundColor = ConsoleColor.Magenta;
            Console.WriteLine($"[TELEMETRY] Activity: {activityName} | Status: {activityStatus} | Result: {resultCode ?? "OK"} | Duration: {durationMs}ms | CorrelationId: {edogCorrelationId}");
            if (activityAttributes != null && activityAttributes.Count > 0)
            {
                Console.WriteLine($"            Attributes: {JsonConvert.SerializeObject(activityAttributes, Formatting.None)}");
            }

            Console.ResetColor();
'''

def apply_telemetry_console_output(content):
    """Add console output to telemetry reporter. Revert handled by patch."""
    marker = '// EDOG DevMode - Console telemetry output'
    if marker in content:
        return content, "already_applied"
    
    target = 'Check.Assert(durationMs >= 0, nameof(durationMs));'
    if target not in content:
        return content, "pattern_not_found"
    
    # Insert after target line
    idx = content.find(target)
    line_end = content.find('\n', idx) + 1
    
    return content[:line_end] + TELEMETRY_CONSOLE_CODE + content[line_end:], "applied"


# ============================================================================
# Tracer Console Output (for actual logs via Tracer.LogSanitizedMessage etc.)
# ============================================================================

# This file will be created in the FLT repo to intercept Tracer calls
DEVMODE_TRACER_FILE_CONTENT = '''// <auto-generated>
// EDOG DevMode - Tracer Console Output Wrapper
// This file redirects platform Tracer calls to console for local debugging.
// DO NOT COMMIT THIS FILE - Run 'edog --revert' before committing.
// </auto-generated>
#pragma warning disable CS1591 // Missing XML comment
#pragma warning disable SA1600 // Elements should be documented

namespace Microsoft.ServicePlatform.Telemetry
{
    using System;
    using System.Diagnostics.CodeAnalysis;
    using OriginalTracer = global::Microsoft.ServicePlatform.Telemetry.Tracer;

    [ExcludeFromCodeCoverage]
    internal static class EdogTracer
    {
        private static readonly object Lock = new object();

        public static void LogSanitizedMessage(string message)
        {
            WriteToConsole("INFO", message);
            OriginalTracer.LogSanitizedMessage(message);
        }

        public static void LogSanitizedWarning(string message)
        {
            WriteToConsole("WARN", message);
            OriginalTracer.LogSanitizedWarning(message);
        }

        public static void LogSanitizedError(string message)
        {
            WriteToConsole("ERROR", message);
            OriginalTracer.LogSanitizedError(message);
        }

        public static void LogSanitizedError(Exception ex, string message)
        {
            WriteToConsole("ERROR", $"{message} | Exception: {ex.Message}");
            OriginalTracer.LogSanitizedError(ex, message);
        }

        private static void WriteToConsole(string level, string message)
        {
            lock (Lock)
            {
                var timestamp = DateTime.Now.ToString("HH:mm:ss.fff");
                var originalColor = Console.ForegroundColor;

                Console.ForegroundColor = level switch
                {
                    "ERROR" => ConsoleColor.Red,
                    "WARN" => ConsoleColor.Yellow,
                    _ => ConsoleColor.Cyan
                };

                var displayMsg = message.Length > 200 ? message.Substring(0, 200) + "..." : message;
                Console.WriteLine($"[{timestamp}] [{level,-5}] {displayMsg}");
                Console.ForegroundColor = originalColor;
            }
        }
    }
}

#pragma warning restore SA1600
#pragma warning restore CS1591
'''

# Global usings file to redirect Tracer to EdogTracer
DEVMODE_GLOBAL_USINGS_CONTENT = '''// <auto-generated>
// EDOG DevMode - Global using directives for Tracer interception
// DO NOT COMMIT THIS FILE - Run 'edog --revert' before committing.
// </auto-generated>

global using Tracer = Microsoft.ServicePlatform.Telemetry.EdogTracer;
'''

def get_tracer_file_path(repo_root):
    """Get the path for the DevMode tracer wrapper file."""
    return repo_root / "Service/Microsoft.LiveTable.Service/Core/EdogDevModeTracer.cs"

def get_global_usings_path(repo_root):
    """Get the path for the global usings file."""
    return repo_root / "Service/Microsoft.LiveTable.Service/EdogGlobalUsings.cs"

def apply_tracer_console_output(repo_root):
    """
    Create the DevMode tracer wrapper and global usings files.
    This allows Tracer.LogSanitizedMessage calls to output to console.
    """
    tracer_path = get_tracer_file_path(repo_root)
    usings_path = get_global_usings_path(repo_root)
    
    created_files = []
    
    # Create EdogDevModeTracer.cs
    if not tracer_path.exists():
        write_file(tracer_path, DEVMODE_TRACER_FILE_CONTENT)
        created_files.append(tracer_path.name)
    
    # Create EdogGlobalUsings.cs  
    if not usings_path.exists():
        write_file(usings_path, DEVMODE_GLOBAL_USINGS_CONTENT)
        created_files.append(usings_path.name)
    
    if created_files:
        return "applied", created_files
    else:
        return "already_applied", []


def revert_tracer_console_output(repo_root):
    """Remove the DevMode tracer wrapper files."""
    tracer_path = get_tracer_file_path(repo_root)
    usings_path = get_global_usings_path(repo_root)
    
    removed = False
    
    if tracer_path.exists():
        tracer_path.unlink()
        removed = True
    
    if usings_path.exists():
        usings_path.unlink()
        removed = True
    
    return removed


def check_tracer_console_output(repo_root):
    """Check if tracer console output files exist."""
    tracer_path = get_tracer_file_path(repo_root)
    usings_path = get_global_usings_path(repo_root)
    return tracer_path.exists() and usings_path.exists()


def apply_log_viewer_files(repo_root):
    """Deploy EDOG web log viewer files to FLT repo and build output."""
    src_dir = Path(__file__).parent / "src"
    created_files = []
    
    for name, rel_path in DEVMODE_FILES.items():
        target = repo_root / rel_path
        src_file = src_dir / target.name
        
        if not src_file.exists():
            ui_warn(f"Source file not found: {src_file}")
            continue
        
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if not target.exists():
            shutil.copy2(src_file, target)
            created_files.append(target.name)
        else:
            # Update if content differs
            if src_file.read_text(encoding='utf-8') != target.read_text(encoding='utf-8'):
                shutil.copy2(src_file, target)
                created_files.append(f"{target.name} (updated)")
    
    # Also copy edog-logs.html to build output dirs so the server can find it at runtime
    html_src = src_dir / "edog-logs.html"
    if html_src.exists():
        entry_point = repo_root / "Service" / "Microsoft.LiveTable.Service.EntryPoint"
        bin_dir = entry_point / "bin"
        if bin_dir.exists():
            for dll in bin_dir.rglob("Microsoft.LiveTable.Service.EntryPoint.dll"):
                out_devmode = dll.parent / "DevMode"
                out_devmode.mkdir(parents=True, exist_ok=True)
                shutil.copy2(html_src, out_devmode / "edog-logs.html")
    
    if created_files:
        return "applied", created_files
    return "already_applied", []


def revert_log_viewer_files(repo_root):
    """Remove EDOG web log viewer files from FLT repo."""
    removed = False
    for name, rel_path in DEVMODE_FILES.items():
        target = repo_root / rel_path
        if target.exists():
            target.unlink()
            removed = True
    
    # Remove DevMode directory if empty
    devmode_dir = repo_root / SERVICE_PATH / "DevMode"
    if devmode_dir.exists() and not any(devmode_dir.iterdir()):
        devmode_dir.rmdir()
    
    return removed


def apply_log_viewer_registration_program_cs(content):
    """Apply log viewer registration to Program.cs."""
    # Check if already applied
    if "EDOG DevMode - Start log viewer server" in content:
        return content, "already_applied"
    
    # Find the WorkloadApp instantiation line (capture leading whitespace on same line only)
    patterns = [
        r"(^[ \t]*)(await new WorkloadApp\(\)\.RunAsync\(.*?\);)",
        r"(^[ \t]*)(new WorkloadApp\(\)\.RunAsync\(.*?\)\.GetAwaiter\(\)\.GetResult\(\);)"
    ]
    
    registration_code = (
        "            // EDOG DevMode - Start log viewer server and intercept Tracer\n"
        "            var edogServer = new Microsoft.LiveTable.Service.DevMode.EdogLogServer(5050);\n"
        "\n"
        "            // Load the full log viewer UI from DevMode directory\n"
        "            var edogHtmlCandidates = new[]\n"
        "            {\n"
        '                System.IO.Path.Combine(System.IO.Path.GetDirectoryName(typeof(Microsoft.LiveTable.Service.WorkloadApp).Assembly.Location), "DevMode", "edog-logs.html"),\n'
        '                System.IO.Path.Combine(AppContext.BaseDirectory, "DevMode", "edog-logs.html"),\n'
        '                System.IO.Path.Combine(System.IO.Path.GetDirectoryName(typeof(Microsoft.LiveTable.Service.WorkloadApp).Assembly.Location), "..", "..", "..", "..", "Microsoft.LiveTable.Service", "DevMode", "edog-logs.html"),\n'
        "            };\n"
        "            foreach (var path in edogHtmlCandidates)\n"
        "            {\n"
        "                if (System.IO.File.Exists(path))\n"
        "                {\n"
        "                    edogServer.SetHtmlContent(System.IO.File.ReadAllText(path));\n"
        "                    break;\n"
        "                }\n"
        "            }\n"
        "\n"
        "            edogServer.Start();\n"
        "            Microsoft.ServicePlatform.Telemetry.Tracer.SetStructuredTestLogger(\n"
        "                new Microsoft.LiveTable.Service.DevMode.EdogLogInterceptor(edogServer));\n"
        "\n"
        "            // Store server for telemetry interceptor registration later\n"
        "            Microsoft.PowerBI.ServicePlatform.WireUp.WireUp.RegisterInstance(edogServer);\n"
        "\n"
    )
    
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            indent = match.group(1)
            workload_line = match.group(2)
            new_content = content[:match.start()] + registration_code + indent + workload_line + content[match.end():]
            return new_content, "applied"
    
    return content, "pattern_not_found"


def apply_log_viewer_registration_workloadapp_cs(content):
    """Apply log viewer telemetry interceptor registration to WorkloadApp.cs."""
    # Check if already applied
    if "EdogTelemetryInterceptor" in content:
        return content, "already_applied"
    
    # Find the TelemetryReporter registration line and replace with interceptor wrapper
    original = "WireUp.RegisterSingletonType<ICustomLiveTableTelemetryReporter, CustomLiveTableTelemetryReporter>();"
    replacement = (
        "// EDOG DevMode - Wrap telemetry reporter with web log viewer interceptor\n"
        "            WireUp.RegisterInstance<ICustomLiveTableTelemetryReporter>(\n"
        "                new Microsoft.LiveTable.Service.DevMode.EdogTelemetryInterceptor(\n"
        "                    new CustomLiveTableTelemetryReporter(),\n"
        "                    WireUp.Resolve<Microsoft.LiveTable.Service.DevMode.EdogLogServer>()));"
    )
    
    if original in content:
        new_content = content.replace(original, replacement)
        return new_content, "applied"
    
    return content, "pattern_not_found"


def revert_log_viewer_registration_program_cs(content):
    """Revert log viewer registration from Program.cs."""
    # Remove the EDOG DevMode block (match from start-of-line to preserve surrounding newlines)
    pattern = r"^[ \t]*// EDOG DevMode - Start log viewer server.*?WireUp\.RegisterInstance\(edogServer\);[ \t]*\n\n?"
    new_content = re.sub(pattern, "", content, flags=re.DOTALL | re.MULTILINE)
    return new_content


def revert_log_viewer_registration_workloadapp_cs(content):
    """Revert log viewer telemetry interceptor registration from WorkloadApp.cs."""
    # Replace interceptor wrapper back with original registration
    pattern = (
        r"// EDOG DevMode - Wrap telemetry reporter with web log viewer interceptor\n"
        r"\s*WireUp\.RegisterInstance<ICustomLiveTableTelemetryReporter>\(\n"
        r"\s*new Microsoft\.LiveTable\.Service\.DevMode\.EdogTelemetryInterceptor\(\n"
        r"\s*new CustomLiveTableTelemetryReporter\(\),\n"
        r"\s*WireUp\.Resolve<Microsoft\.LiveTable\.Service\.DevMode\.EdogLogServer>\(\)\)\);"
    )
    replacement = "WireUp.RegisterSingletonType<ICustomLiveTableTelemetryReporter, CustomLiveTableTelemetryReporter>();"
    
    new_content = re.sub(pattern, replacement, content)
    return new_content


def apply_disable_flt_auth_manifest(content):
    """Set DisableFLTAuth to true in ParametersManifest.json."""
    if '"DisableFLTAuth": true' in content:
        return content, "already_applied"
    original = '"DisableFLTAuth": false'
    if original in content:
        return content.replace(original, '"DisableFLTAuth": true'), "applied"
    return content, "pattern_not_found"


def revert_disable_flt_auth_manifest(content):
    """Revert DisableFLTAuth to false in ParametersManifest.json."""
    return content.replace('"DisableFLTAuth": true', '"DisableFLTAuth": false')


def apply_disable_flt_auth_test_json(content):
    """Add DisableFLTAuth: true to Test.json rollout config."""
    if '"DisableFLTAuth": true' in content:
        return content, "already_applied"
    # Add DisableFLTAuth after the last existing property (before closing braces)
    pattern = r'("FabricPublicApiHost":\s*"[^"]*")\s*\n(\s*}\s*\n\s*})'
    match = re.search(pattern, content)
    if match:
        # Preserve whatever comes after the match (including any trailing newline)
        new_content = content[:match.end(1)] + ',\n    "DisableFLTAuth": true\n' + content[match.start(2):]
        return new_content, "applied"
    return content, "pattern_not_found"


def revert_disable_flt_auth_test_json(content):
    """Remove DisableFLTAuth from Test.json rollout config."""
    # Remove the DisableFLTAuth line and trailing comma from previous line
    content = re.sub(r',\s*\n\s*"DisableFLTAuth":\s*true', '', content)
    return content


def check_tracer_console_output(repo_root):
    """Check if tracer console output files exist."""
    tracer_path = get_tracer_file_path(repo_root)
    usings_path = get_global_usings_path(repo_root)
    return tracer_path.exists() and usings_path.exists()


def fetch_mwc_token(bearer_token, workspace_id, artifact_id, capacity_id):
    """Fetch MWC token using Bearer token."""
    
    body = json.dumps({
        "type": "[Start] GetMWCToken",
        "workloadType": "Lakehouse",
        "workspaceObjectId": workspace_id,
        "artifactObjectIds": [artifact_id],
        "capacityObjectId": capacity_id,
        "asyncId": str(uuid.uuid4()),
        "iframeId": str(uuid.uuid4())
    }).encode('utf-8')
    
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json",
        "activityid": str(uuid.uuid4()),
        "requestid": str(uuid.uuid4()),
        "x-powerbi-hostenv": "Power BI Web App",
        "origin": "https://powerbi-df.analysis-df.windows.net",
        "referer": "https://powerbi-df.analysis-df.windows.net/"
    }
    
    req = urllib.request.Request(MWC_TOKEN_ENDPOINT, data=body, headers=headers, method='POST')
    
    try:
        import ssl
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('Token') or result.get('token')
    except urllib.error.HTTPError as e:
        ui_error(f"HTTP Error {e.code}: {e.reason}")
        try:
            ui_dim(f"Response: {e.read().decode('utf-8')[:500]}")
        except:
            pass
        return None
    except urllib.error.URLError as e:
        ui_error(f"URL Error: {e.reason}")
        return None
    except Exception as e:
        ui_error(f"Error fetching MWC token: {type(e).__name__}: {e}")
        return None


# Module-level cache: {cert_cn: thumbprint}
_thumbprint_cache: dict = {}


def _get_token_helper_exe():
    """Locate the token-helper executable, preferring net8.0 over net472."""
    helper_dir = Path(__file__).parent / "scripts" / "token-helper"
    # Prefer net8.0 (current csproj target) over stale net472
    for tfm in ("net8.0", "net472"):
        exe = helper_dir / "bin" / "Debug" / tfm / "token-helper.exe"
        if exe.exists():
            return exe

    # Not built yet — try building
    csproj = helper_dir / "token-helper.csproj"
    if csproj.exists():
        ui_dim("Building token-helper...")
        build = subprocess.run(
            ["dotnet", "build", str(csproj), "-v", "q"],
            capture_output=True, text=True,
        )
        if build.returncode == 0:
            for tfm in ("net8.0", "net472"):
                exe = helper_dir / "bin" / "Debug" / tfm / "token-helper.exe"
                if exe.exists():
                    return exe
    return None


def _find_cert_thumbprint(cert_subject: str):
    """Find certificate thumbprint from Windows cert store by CN.

    Strategy:
        1. Memory cache
        2. Disk cache (survives restarts)
        3. token-helper --list-certs (fast, returns all CBA certs as JSON)
        4. PowerShell fallback
    If multiple certs match, shows chooser.
    """
    if cert_subject in _thumbprint_cache:
        return _thumbprint_cache[cert_subject]

    # Check disk cache (survives restarts)
    cache_file = Path(__file__).parent / ".edog-thumbprint-cache"
    if cache_file.exists():
        try:
            for line in cache_file.read_text(encoding="utf-8").splitlines():
                if line.startswith(cert_subject + "="):
                    tp = line.split("=", 1)[1].strip()
                    if len(tp) == 40:
                        _thumbprint_cache[cert_subject] = tp
                        return tp
        except OSError:
            pass

    # Try token-helper --list-certs first (faster than PowerShell, returns JSON)
    helper_exe = _get_token_helper_exe()
    if helper_exe:
        try:
            result = subprocess.run(
                [str(helper_exe), "--list-certs"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                certs = json.loads(result.stdout.strip())
                # Filter certs matching our subject
                matches = [c for c in certs if cert_subject.lower() in c.get("cn", "").lower()
                           or cert_subject.lower() in c.get("subject", "").lower()]
                if len(matches) == 1:
                    tp = matches[0]["thumbprint"]
                    _thumbprint_cache[cert_subject] = tp
                    try:
                        cache_file.write_text(f"{cert_subject}={tp}\n", encoding="utf-8")
                    except OSError:
                        pass
                    ui_dim(f"Cert: {matches[0].get('cn', cert_subject)} ({tp[:8]}...)")
                    return tp
                elif len(matches) > 1:
                    ui_info(f"Found {len(matches)} CBA certificates matching '{cert_subject}':")
                    options = []
                    for c in matches:
                        label = f"{c.get('cn', '?')}  thumbprint:{c['thumbprint'][:8]}...  expires:{c.get('notAfter', '?')[:10]}"
                        options.append(label)
                    chosen = ui_choose("Select certificate", options)
                    if chosen:
                        idx = options.index(chosen)
                        tp = matches[idx]["thumbprint"]
                        _thumbprint_cache[cert_subject] = tp
                        try:
                            cache_file.write_text(f"{cert_subject}={tp}\n", encoding="utf-8")
                        except OSError:
                            pass
                        return tp
                    return None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass

    # Fallback: PowerShell cert store query
    tp = _query_cert_store(cert_subject)
    if tp:
        _thumbprint_cache[cert_subject] = tp
        try:
            cache_file.write_text(f"{cert_subject}={tp}\n", encoding="utf-8")
        except OSError:
            pass
    else:
        ui_error(f"No CBA certificate found for '{cert_subject}'")
        ui_dim("The certificate is needed for Silent CBA authentication.")
        
        # Offer to import from file
        if _try_import_cert(cert_subject):
            # Re-query after import
            tp = _query_cert_store(cert_subject)
            if tp:
                _thumbprint_cache[cert_subject] = tp
                try:
                    cache_file.write_text(f"{cert_subject}={tp}\n", encoding="utf-8")
                except OSError:
                    pass
                ui_success(f"Certificate imported and ready ({tp[:8]}...)")
    return tp


def _try_import_cert(cert_cn: str) -> bool:
    """Prompt user for a .pfx/.p12 cert file and import into CurrentUser\\My store."""
    if not ui_confirm("Do you have the certificate file (.pfx/.p12) to import?", default=False):
        ui_dim("Install the CBA cert manually into CurrentUser\\My cert store, then retry.")
        return False
    
    cert_path = ui_prompt("Certificate file path (.pfx or .p12)")
    if not cert_path:
        return False
    
    # Strip quotes (drag-and-drop paths often have them)
    cert_path = cert_path.strip('"').strip("'")
    cert_file = Path(cert_path)
    
    if not cert_file.exists():
        ui_error(f"File not found: {cert_path}")
        return False
    
    if cert_file.suffix.lower() not in ('.pfx', '.p12'):
        ui_error(f"Expected .pfx or .p12 file, got: {cert_file.suffix}")
        return False
    
    try:
        ps_cmd = (
            f'Import-PfxCertificate -FilePath "{cert_file}" '
            f'-CertStoreLocation Cert:\\CurrentUser\\My'
        )
        
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            ui_success("Certificate imported into CurrentUser\\My store")
            return True
        else:
            err = result.stderr.strip() or result.stdout.strip()
            ui_error(f"Import failed: {err[:200]}")
            return False
    except subprocess.TimeoutExpired:
        ui_error("Import timed out")
        return False
    except Exception as e:
        ui_error(f"Import error: {e}")
        return False


def _query_cert_store(cert_cn: str) -> str | None:
    """Query Windows cert store via PowerShell. Slow (~2-8s), called once."""
    try:
        ps_cmd = (
            'Import-Module PKI -ErrorAction SilentlyContinue; '
            f'Get-ChildItem Cert:\\CurrentUser\\My | '
            f'Where-Object {{ $_.Subject -like "*CN={cert_cn}*" }} | '
            'Select-Object -First 1 -ExpandProperty Thumbprint'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
        )
        tp = result.stdout.strip()
        if tp and len(tp) == 40:
            return tp

        # Fallback: .NET cert store API
        dotnet_cmd = (
            'Add-Type -AssemblyName System.Security; '
            '$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('
            '"My", [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser); '
            '$store.Open("ReadOnly"); '
            f'$c = $store.Certificates | Where-Object {{ $_.Subject -like "*CN={cert_cn}*" }} | '
            'Select-Object -First 1; '
            '$store.Close(); '
            'if ($c) { $c.Thumbprint }'
        )
        result2 = subprocess.run(
            ["powershell", "-NoProfile", "-Command", dotnet_cmd],
            capture_output=True, text=True, timeout=10,
        )
        tp2 = result2.stdout.strip()
        return tp2 if tp2 and len(tp2) == 40 else None
    except Exception:
        return None


def _try_silent_cba(username: str, resource: str | None = None):
    """Acquire token via C# Silent CBA helper (no browser needed).

    Uses certificate-based auth purely over HTTP/TLS — the same
    mechanism used by FabricSparkCST CI/CD pipelines.
    Returns bearer token string or None.

    Args:
        username: CBA username (e.g. Admin1CBA@FabricFMLV08PPE.ccsctp.net).
        resource: Optional token audience/resource URI. If provided, passed
                  as 5th arg to token-helper (overrides the default PowerBI API).
    """
    cert_subject = username.replace("@", ".")
    thumbprint = _find_cert_thumbprint(cert_subject)
    if not thumbprint:
        return None

    helper_exe = _get_token_helper_exe()
    if not helper_exe:
        return None

    ui_dim(f"Silent CBA: {cert_subject}" + (f" (audience: {resource})" if resource else ""))
    try:
        cmd = [str(helper_exe), thumbprint, username]
        if resource:
            # token-helper args: <thumbprint> <username> [clientId] [authority] [resource]
            cmd += ["ea0616ba-638b-4df5-95b9-636659ae5121",
                    "https://login.windows-ppe.net/organizations",
                    resource]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        ui_warn("Silent CBA timed out")
        return None

    if result.returncode == 0:
        token = result.stdout.strip()
        if token.startswith("eyJ"):
            ui_dim(f"Token acquired via Silent CBA ({len(token)} chars)")
            return token

    for line in (result.stderr or "").strip().split("\n"):
        if "ERROR" in line:
            ui_warn(f"Silent CBA: {line}")
    return None



def _cache_bearer(token: str) -> None:
    """Parse JWT expiry and cache bearer token to disk."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        claims = json.loads(base64.b64decode(payload).decode("utf-8", errors="replace"))
        expiry_ts = float(claims.get("exp", time.time() + 3600))
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        expiry_ts = time.time() + 3600
    cache_bearer_token(token, expiry_ts)


def get_bearer_token(username):
    """Acquire a user-delegated bearer token via Silent CBA.

    Strategy:
        1. Check disk cache first (sub-millisecond).
        2. Silent CBA via C# token-helper (~3-5 seconds, zero browser).

    Args:
        username: CBA username, e.g. Admin1CBA@FabricFMLV08PPE.ccsctp.net.

    Returns:
        Bearer token string, or None on failure.
    """
    if not username:
        ui_error("Username is required")
        return None

    # --- 1. Try cache first ---
    cached_token, cached_expiry = load_cached_bearer_token()
    if cached_token:
        remaining = (cached_expiry - datetime.now()).total_seconds() / 60
        ui_dim(f"Using cached bearer token (expires in {remaining:.0f} min)")
        return cached_token

    # --- 2. Silent CBA ---
    bearer_token = _try_silent_cba(username)
    if bearer_token:
        _cache_bearer(bearer_token)
        return bearer_token

    ui_error("Failed to acquire token")
    return None


# ============================================================================
# Main EDOG operations
# ============================================================================
def apply_all_changes(repo_root, workspace_id=None):
    """Apply all EDOG changes to codebase and generate a patch file for clean revert."""
    ui_step("Applying EDOG changes...")
    
    changes_made = []
    warnings = []
    original_contents = {}  # Store originals for patch generation
    modified_contents = {}  # Store modified for patch generation
    
    # 1. GTSBasedSparkClient - File-based token bypass
    rel_path = FILES["GTSBasedSparkClient"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        new_content, status = apply_gts_spark_client_change(content, repo_root, workspace_id=workspace_id)
        if status in ["applied"]:
            original_contents[rel_path] = content
            write_file(filepath, new_content)
            modified_contents[rel_path] = new_content
            changes_made.append(f"✅ GTSBasedSparkClient file-based token bypass")
        elif status == "already_applied":
            reverted, reverted_ok = revert_gts_spark_client_change(content, repo_root)
            if reverted_ok and reverted != content:
                original_contents[rel_path] = reverted
                modified_contents[rel_path] = content
            changes_made.append(f"⏭️  GTSBasedSparkClient file-based bypass (already)")
        elif status == "pattern_not_found":
            original_contents[rel_path] = content
            modified_contents[rel_path] = content
            warnings.append(f"⚠️  GTSBasedSparkClient: pattern not found")
        elif status == "upgrade_failed":
            warnings.append(f"⚠️  GTSBasedSparkClient: failed to upgrade from hardcoded to file-based")
    
    # 3. Deploy web log viewer files (creates new files in DevMode/)
    status, files = apply_log_viewer_files(repo_root)
    if status == "applied":
        changes_made.append(f"✅ Web log viewer ({', '.join(files)})")
    elif status == "already_applied":
        changes_made.append(f"⏭️  Web log viewer (already)")
    
    # 4. Register log viewer interceptors (modify Program.cs and WorkloadApp.cs)
    # Program.cs registration
    rel_path = FILES["Program"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        new_content, status = apply_log_viewer_registration_program_cs(content)
        if status == "applied":
            original_contents[rel_path] = content
            write_file(filepath, new_content)
            modified_contents[rel_path] = new_content
            changes_made.append(f"✅ Log viewer server registration (Program.cs)")
        elif status == "already_applied":
            reverted = revert_log_viewer_registration_program_cs(content)
            if reverted != content:
                original_contents[rel_path] = reverted
                modified_contents[rel_path] = content
            changes_made.append(f"⏭️  Log viewer server registration (already)")
        elif status == "pattern_not_found":
            original_contents[rel_path] = content
            modified_contents[rel_path] = content
            warnings.append(f"⚠️  Log viewer server registration: pattern not found")
    
    # WorkloadApp.cs registration
    rel_path = FILES["WorkloadApp"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        new_content, status = apply_log_viewer_registration_workloadapp_cs(content)
        if status == "applied":
            if rel_path not in original_contents:
                original_contents[rel_path] = content
            write_file(filepath, new_content)
            modified_contents[rel_path] = new_content
            changes_made.append(f"✅ Log viewer telemetry interceptor (WorkloadApp.cs)")
        elif status == "already_applied":
            # Compute the pre-EDOG original by reverting the current content
            reverted = revert_log_viewer_registration_workloadapp_cs(content)
            if reverted != content:
                original_contents[rel_path] = reverted
                modified_contents[rel_path] = content
            changes_made.append(f"⏭️  Log viewer telemetry interceptor (already)")
        elif status == "pattern_not_found":
            if rel_path not in original_contents:
                original_contents[rel_path] = content
            modified_contents[rel_path] = content
            warnings.append(f"⚠️  Log viewer telemetry interceptor: pattern not found")
    
    # 5. Disable FLT auth for EDOG DevMode (ParametersManifest.json and Test.json)
    for file_key, apply_fn, revert_fn, desc in [
        ("ParametersManifest", apply_disable_flt_auth_manifest, revert_disable_flt_auth_manifest, "DisableFLTAuth (ParametersManifest.json)"),
        ("TestRollout", apply_disable_flt_auth_test_json, revert_disable_flt_auth_test_json, "DisableFLTAuth (Test.json)"),
    ]:
        rel_path = FILES[file_key]
        filepath = repo_root / rel_path
        content = read_file(filepath)
        if content:
            new_content, status = apply_fn(content)
            if status == "applied":
                original_contents[rel_path] = content
                write_file(filepath, new_content)
                modified_contents[rel_path] = new_content
                changes_made.append(f"✅ {desc}")
            elif status == "already_applied":
                reverted = revert_fn(content)
                if reverted != content:
                    original_contents[rel_path] = reverted
                    modified_contents[rel_path] = content
                changes_made.append(f"⏭️  {desc} (already)")
            elif status == "pattern_not_found":
                original_contents[rel_path] = content
                modified_contents[rel_path] = content
                warnings.append(f"⚠️  {desc}: pattern not found")
    
    # Generate patch file for clean revert
    if generate_patch(original_contents, modified_contents, repo_root):
        ui_dim(f"Patch file saved: {get_patch_file_path().name}")
        ui_dim("Use 'edog --revert' to cleanly undo all changes")
    
    # Print summary
    for msg in changes_made:
        ui_print(f"   {msg}")
    
    # Print warnings
    if warnings:
        for msg in warnings:
            ui_warn(msg)
    
    # Auto-install pre-commit hook if not present
    try:
        hook_path = repo_root / ".git" / "hooks" / "pre-commit"
        if not hook_path.exists():
            install_git_hook(repo_root)
            ui_dim("Pre-commit hook auto-installed (blocks EDOG changes in commits)")
        elif "EDOG DevMode" not in hook_path.read_text(encoding="utf-8", errors="replace"):
            ui_dim("Pre-commit hook exists (non-EDOG) — skipping auto-install")
    except Exception:
        pass  # Non-critical
    
    return len(warnings) == 0


def revert_all_changes(repo_root):
    """Revert all EDOG changes using smart pattern-based revert functions.
    
    Does NOT depend on the patch file — each change type has its own revert
    function that detects and removes EDOG modifications directly.
    """
    ui_step("Reverting EDOG changes...")
    
    all_success = True
    
    # 1. Revert log viewer files (created files, not patches)
    try:
        if revert_log_viewer_files(repo_root):
            ui_success("Removed log viewer files")
    except Exception as e:
        ui_warn(f"Error removing log viewer files: {e}")
        all_success = False
    
    # 2. Revert GTSBasedSparkClient bypass
    try:
        rel_path = FILES["GTSBasedSparkClient"]
        filepath = repo_root / rel_path
        content = read_file(filepath)
        if content:
            reverted, changed = revert_gts_spark_client_change(content, repo_root)
            if changed:
                write_file(filepath, reverted)
                ui_success("Reverted GTSBasedSparkClient bypass")
            else:
                ui_dim("GTSBasedSparkClient (clean)")
    except Exception as e:
        ui_warn(f"Error reverting GTSBasedSparkClient: {e}")
        all_success = False
    
    # 4. Revert Program.cs registration
    try:
        rel_path = FILES["Program"]
        filepath = repo_root / rel_path
        content = read_file(filepath)
        if content:
            reverted = revert_log_viewer_registration_program_cs(content)
            if reverted != content:
                write_file(filepath, reverted)
                ui_success("Reverted log viewer registration (Program.cs)")
            else:
                ui_dim("Program.cs (clean)")
    except Exception as e:
        ui_warn(f"Error reverting Program.cs: {e}")
        all_success = False
    
    # 5. Revert WorkloadApp.cs interceptor
    try:
        rel_path = FILES["WorkloadApp"]
        filepath = repo_root / rel_path
        content = read_file(filepath)
        if content:
            reverted = revert_log_viewer_registration_workloadapp_cs(content)
            if reverted != content:
                write_file(filepath, reverted)
                ui_success("Reverted telemetry interceptor (WorkloadApp.cs)")
            else:
                ui_dim("WorkloadApp.cs (clean)")
    except Exception as e:
        ui_warn(f"Error reverting WorkloadApp.cs: {e}")
        all_success = False
    
    # 6. Revert DisableFLTAuth in ParametersManifest.json and Test.json
    for file_key, revert_fn, desc in [
        ("ParametersManifest", revert_disable_flt_auth_manifest, "DisableFLTAuth (ParametersManifest.json)"),
        ("TestRollout", revert_disable_flt_auth_test_json, "DisableFLTAuth (Test.json)"),
    ]:
        try:
            rel_path = FILES[file_key]
            filepath = repo_root / rel_path
            content = read_file(filepath)
            if content:
                reverted = revert_fn(content)
                if reverted != content:
                    write_file(filepath, reverted)
                    ui_success(f"Reverted {desc}")
                else:
                    ui_dim(f"{desc} (clean)")
        except Exception as e:
            ui_warn(f"Error reverting {desc}: {e}")
            all_success = False
    
    # 7. Clean up patch file (no longer needed)
    try:
        patch_path = get_patch_file_path()
        if patch_path.exists():
            patch_path.unlink()
    except Exception:
        pass
    
    return all_success


def detect_stale_patches(repo_root):
    """Scan patched files for leftover EDOG markers from a previous dirty exit.

    Returns list of (file_key, rel_path) tuples where stale patches were found.
    This is read-only — it never modifies any files.
    """
    MARKERS = ("// EDOG", "EDOG DevMode")
    stale = []

    # Check FILES entries for EDOG markers in the target source files
    for file_key, rel_path in FILES.items():
        try:
            filepath = repo_root / rel_path
            if not filepath.exists():
                continue
            content = filepath.read_text(encoding="utf-8", errors="replace")
            if any(marker in content for marker in MARKERS):
                stale.append((file_key, str(rel_path)))
        except Exception:
            pass  # read-only scan — skip unreadable files

    # Check if DevMode/ directory exists (created files, not patches)
    devmode_dir = repo_root / SERVICE_PATH / "DevMode"
    if devmode_dir.is_dir():
        stale.append(("DevMode_dir", str(SERVICE_PATH / "DevMode")))

    return stale


def run_setup(force=False):
    """Run EDOG setup: check prerequisites, install deps, build token-helper, add to PATH.
    
    Returns True if setup is complete and ready to go.
    """
    edog_dir = Path(__file__).parent
    errors = 0
    
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(
            "[bold]EDOG DevMode[/bold]  [dim]Setup[/dim]\n[dim]FabricLiveTable Development Tool[/dim]",
            border_style="cyan", expand=False
        ))
    else:
        print("\n  EDOG DevMode Setup")
        print("  " + "-" * 40)
    
    # Step 1: Prerequisites
    ui_step("[1/4] Checking prerequisites")
    
    # Python (already running if we're here)
    import platform
    py_ver = platform.python_version()
    ui_success(f"Python {py_ver}")
    
    # .NET SDK
    try:
        result = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            ui_success(f".NET SDK {result.stdout.strip()}")
        else:
            ui_error(".NET SDK not found")
            ui_dim("Install .NET SDK 8.0+ from: https://dotnet.microsoft.com/download")
            return False
    except FileNotFoundError:
        ui_error(".NET SDK not found — 'dotnet' not in PATH")
        ui_dim("Install .NET SDK 8.0+ from: https://dotnet.microsoft.com/download")
        return False
    except subprocess.TimeoutExpired:
        ui_warn(".NET SDK check timed out")
        errors += 1
    
    # Step 2: Python deps
    ui_step("[2/4] Installing Python dependencies")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "--quiet", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            ui_success("rich installed")
        else:
            ui_warn("rich install failed — CLI will work without styling")
            errors += 1
    except Exception:
        ui_warn("Could not install rich")
        errors += 1
    
    # Step 3: Build token-helper
    ui_step("[3/4] Building token-helper (Silent CBA auth)")
    helper_dir = edog_dir / "scripts" / "token-helper"
    helper_exe = None
    for tfm in ("net8.0", "net472"):
        exe = helper_dir / "bin" / "Debug" / tfm / "token-helper.exe"
        if exe.exists():
            helper_exe = exe
            break
    
    if helper_exe:
        ui_success("Already built")
    else:
        csproj = helper_dir / "token-helper.csproj"
        if csproj.exists():
            result = subprocess.run(
                ["dotnet", "build", str(csproj), "--nologo", "-v", "q"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                ui_success("Build successful")
            else:
                ui_error("Build failed")
                ui_dim(f"Try manually: dotnet build {csproj}")
                errors += 1
        else:
            ui_error(f"token-helper.csproj not found at {helper_dir}")
            errors += 1
    
    # Step 4: PATH
    ui_step("[4/4] Adding edog to PATH")
    edog_dir_str = str(edog_dir)
    path_env = os.environ.get("PATH", "")
    if edog_dir_str.lower() in path_env.lower():
        ui_success("Already in PATH")
    else:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"$p = [Environment]::GetEnvironmentVariable('Path','User'); "
                 f"if (-not $p -or $p -notlike '*{edog_dir_str}*') {{ "
                 f"[Environment]::SetEnvironmentVariable('Path', \"$p;{edog_dir_str}\", 'User') }}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                ui_success("Added to PATH (restart terminal to use globally)")
            else:
                ui_warn(f"Could not add automatically — add manually: {edog_dir_str}")
                errors += 1
        except Exception:
            ui_warn(f"Could not add to PATH — add manually: {edog_dir_str}")
            errors += 1
    
    # Summary
    print()
    if errors == 0:
        ui_success("Setup complete!")
    else:
        ui_warn(f"Setup complete with {errors} warning(s)")
    
    ui_dim("Quick start:")
    ui_dim("  edog --config      Set workspace, artifact, capacity")
    ui_dim("  edog               Start DevMode (launches FLT service)")
    ui_dim("  edog --no-launch   Token management only")
    ui_dim("  edog --revert      Undo all EDOG changes")
    print()
    
    return errors == 0


def run_doctor():
    """One-shot diagnostic for all dependencies and config."""
    import platform

    show_banner()
    ui_step("Running diagnostics...")
    print()

    passed = 0
    failed = 0
    warnings = 0

    def check_pass(msg):
        nonlocal passed
        passed += 1
        ui_success(msg)

    def check_fail(msg, hint=None):
        nonlocal failed
        failed += 1
        ui_error(msg)
        if hint:
            ui_dim(f"  Fix: {hint}")

    def check_warn(msg, hint=None):
        nonlocal warnings
        warnings += 1
        ui_warn(msg)
        if hint:
            ui_dim(f"  Tip: {hint}")

    # 1. Python
    py_ver = platform.python_version()
    py_parts = tuple(int(x) for x in py_ver.split(".")[:2])
    if py_parts >= (3, 10):
        check_pass(f"Python {py_ver}")
    else:
        check_fail(f"Python {py_ver} (need 3.10+)", "Install Python 3.10 or newer")

    # 2. Rich
    if RICH_AVAILABLE:
        import rich
        check_pass(f"Rich {rich.__version__}")
    else:
        check_warn("Rich not installed (CLI will work but look plain)", "pip install rich")

    # 3. .NET SDK
    try:
        result = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            check_pass(f".NET SDK {result.stdout.strip()}")
        else:
            check_fail(".NET SDK not found", "Install .NET SDK 8.0+ from https://dotnet.microsoft.com/download")
    except FileNotFoundError:
        check_fail(".NET SDK not found — 'dotnet' not in PATH", "Install .NET SDK 8.0+ from https://dotnet.microsoft.com/download")
    except subprocess.TimeoutExpired:
        check_warn(".NET SDK check timed out")

    # 4. token-helper
    helper_exe = _get_token_helper_exe()
    if helper_exe:
        check_pass(f"token-helper: {helper_exe.name}")
    else:
        check_fail("token-helper not found", "Run: edog --setup")

    # 5. Config file
    config_path = Path(__file__).parent / CONFIG_FILE
    if config_path.exists():
        check_pass(f"Config file: {CONFIG_FILE}")
    else:
        check_warn(f"Config file not found: {CONFIG_FILE}", "Run: edog --config")

    # 6. Username
    config = load_config()
    username = config.get("username", DEFAULT_USERNAME)
    if "@" in username:
        check_pass(f"Username: {username}")
    else:
        check_fail(f"Username invalid: {username}", "Run: edog --config -u your@email.com")

    # 7. Certificate
    cert_cn = username.replace("@", ".")
    try:
        tp = _find_cert_thumbprint(cert_cn)
        if tp:
            check_pass(f"Certificate: {tp[:8]}...")
        else:
            check_warn(f"Certificate not found for {cert_cn}", "Install CBA certificate or check username")
    except Exception:
        check_warn(f"Certificate lookup failed for {cert_cn}")

    # 8. Workspace ID
    ws_id = config.get("workspace_id", "")
    if ws_id and len(ws_id) > 8:
        check_pass(f"Workspace ID: {ws_id[:8]}...")
    else:
        check_fail("Workspace ID not set", "Run: edog --config -w <workspace-id>")

    # 9. Artifact ID
    art_id = config.get("artifact_id", "")
    if art_id and len(art_id) > 8:
        check_pass(f"Artifact ID: {art_id[:8]}...")
    else:
        check_fail("Artifact ID not set", "Run: edog --config -a <artifact-id>")

    # 10–13. FLT repo checks (grouped)
    repo_root = None
    try:
        repo_root = get_repo_root()
    except SystemExit:
        pass

    if repo_root:
        check_pass(f"FLT repo: {repo_root}")

        # 11. Service project
        entrypoint = get_entrypoint_path(repo_root)
        if entrypoint.exists():
            check_pass(f"Service project: {entrypoint.name}")
        else:
            check_fail("Service EntryPoint project not found", f"Expected at {entrypoint}")

        # 12. Git hooks
        hook_file = repo_root / ".git" / "hooks" / "pre-commit"
        if hook_file.exists():
            try:
                hook_content = hook_file.read_text(encoding="utf-8", errors="replace")
                if "EDOG DevMode pre-commit hook" in hook_content:
                    check_pass("Git pre-commit hook installed")
                else:
                    check_warn("Pre-commit hook exists but not EDOG hook", "Run: edog --install-hook")
            except Exception:
                check_warn("Could not read pre-commit hook")
        else:
            check_warn("No git pre-commit hook", "Run: edog --install-hook")

        # 13. Stale patches
        stale = detect_stale_patches(repo_root)
        if not stale:
            check_pass("No stale patches found")
        else:
            check_warn(f"{len(stale)} stale patch(es) detected", "Run: edog --revert to clean up")
    else:
        check_fail("FLT repo not found", "Run: edog --config -r <path-to-FabricLiveTable>")
        # Skip checks 11–13
        check_fail("Service project — skipped (no repo)")
        check_warn("Git hooks — skipped (no repo)")
        check_warn("Stale patches — skipped (no repo)")

    # 14. PATH
    edog_dir = str(Path(__file__).parent)
    if edog_dir in os.environ.get("PATH", ""):
        check_pass(f"PATH includes edog directory")
    else:
        check_warn("edog directory not in PATH", f"Add {edog_dir} to your PATH")

    # Summary
    total = passed + failed + warnings
    print()
    if failed == 0:
        ui_success(f"All clear! {passed}/{total} passed, {warnings} warning(s)")
    else:
        ui_error(f"{failed} failed, {warnings} warning(s), {passed} passed")


def auto_update():
    """Pull latest EDOG code from git (fast-forward only).
    
    Returns True if updated, False if already up-to-date, None on error/skip.
    """
    edog_dir = Path(__file__).parent
    
    # Check if edog dir is a git repo
    if not (edog_dir / ".git").exists():
        return None
    
    try:
        # Check for local changes first
        status = subprocess.run(
            ["git", "-C", str(edog_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        if status.stdout.strip():
            ui_dim("Skipping auto-update (local changes detected)")
            return None
        
        # Fetch + fast-forward
        ui_dim("Checking for updates...")
        result = subprocess.run(
            ["git", "-C", str(edog_dir), "pull", "--ff-only", "--quiet"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            if "Already up to date" in (result.stdout + result.stderr):
                ui_dim("Already up to date")
                return False
            else:
                ui_success("Updated to latest version!")
                ui_dim("Restart edog to use the new version.")
                return True
        else:
            ui_dim("Auto-update skipped (pull failed — run manually if needed)")
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def run_api_repl(workspace_id):
    """Interactive authenticated REPL for API calls with bearer token."""
    import urllib.request
    import urllib.error
    
    live_path = get_bearer_live_path(workspace_id)
    if not live_path.exists():
        ui_error("No bearer token found. Start edog first to generate a token.")
        return
    
    raw = live_path.read_text(encoding="utf-8").strip()
    token = raw.split("|")[0] if "|" in raw else raw
    
    show_banner()
    ui_step("API REPL")
    ui_dim("Type 'help' for commands, 'quit' to exit")
    print()
    
    while True:
        try:
            cmd = input("edog-api> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        
        if not cmd:
            continue
        
        parts = cmd.split(None, 2)
        verb = parts[0].upper()
        
        if verb in ("QUIT", "EXIT", "Q"):
            break
        elif verb == "HELP":
            ui_info("Commands:")
            ui_dim("  GET <url>           — GET request with bearer auth")
            ui_dim("  POST <url> [body]   — POST request with bearer auth")
            ui_dim("  endpoints           — Show endpoint shortcuts")
            ui_dim("  token               — Show current token info")
            ui_dim("  refresh             — Reload token from file")
            ui_dim("  quit                — Exit REPL")
            continue
        elif verb == "ENDPOINTS":
            ui_info("Endpoint shortcuts:")
            for name, (method, url) in EDOG_API_ENDPOINTS.items():
                ui_dim(f"  {name:20s} {method:4s} {url}")
            continue
        elif verb == "TOKEN":
            ui_info(f"Token length: {len(token)} chars")
            ui_dim(f"First 20: {token[:20]}...")
            ui_dim(f"File: {live_path}")
            continue
        elif verb == "REFRESH":
            if live_path.exists():
                raw = live_path.read_text(encoding="utf-8").strip()
                token = raw.split("|")[0] if "|" in raw else raw
                ui_success("Token reloaded from file")
            else:
                ui_warn("Token file not found")
            continue
        elif verb in ("GET", "POST"):
            if len(parts) < 2:
                ui_warn(f"Usage: {verb} <url> [body]")
                continue
            
            url_or_shortcut = parts[1]
            body = parts[2] if len(parts) > 2 else None
            
            # Resolve shortcut
            if url_or_shortcut.lower() in EDOG_API_ENDPOINTS:
                shortcut_method, url = EDOG_API_ENDPOINTS[url_or_shortcut.lower()]
                if verb == "GET" and shortcut_method == "POST":
                    ui_dim(f"Note: '{url_or_shortcut}' is typically {shortcut_method}, using {verb} as requested")
            else:
                url = url_or_shortcut
            
            try:
                req = urllib.request.Request(url, method=verb)
                req.add_header("Authorization", f"Bearer {token}")
                req.add_header("Content-Type", "application/json")
                if body:
                    req.data = body.encode("utf-8")
                
                ui_dim(f"{verb} {url}...")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_body = resp.read().decode("utf-8")
                    ui_success(f"HTTP {resp.status}")
                    
                    # Pretty-print JSON
                    try:
                        parsed = json.loads(resp_body)
                        if RICH_AVAILABLE:
                            from rich.syntax import Syntax
                            formatted = json.dumps(parsed, indent=2)
                            console.print(Syntax(formatted, "json", theme="monokai", line_numbers=False))
                        else:
                            print(json.dumps(parsed, indent=2))
                    except json.JSONDecodeError:
                        print(resp_body[:2000])
                        
            except urllib.error.HTTPError as e:
                ui_error(f"HTTP {e.code} {e.reason}")
                try:
                    err_body = e.read().decode("utf-8")
                    if err_body:
                        ui_dim(err_body[:500])
                except Exception:
                    pass
            except urllib.error.URLError as e:
                ui_error(f"Connection error: {e.reason}")
            except Exception as e:
                ui_error(f"Request failed: {e}")
            continue
        else:
            ui_warn(f"Unknown command: {verb}. Type 'help' for commands.")
    
    ui_dim("Goodbye!")


def _needs_setup():
    """Check if first-time setup is needed (token-helper not built)."""
    helper_dir = Path(__file__).parent / "scripts" / "token-helper"
    for tfm in ("net8.0", "net472"):
        if (helper_dir / "bin" / "Debug" / tfm / "token-helper.exe").exists():
            return False
    return True


def check_status(repo_root):
    """Check if EDOG changes are applied using smart pattern matching."""
    ui_step("Checking EDOG status...")
    
    status = []
    
    # Check GTSBasedSparkClient (legacy - exact match)
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        applied = "// EDOG DevMode - bypassing OBO token exchange" in content
        status.append(("GTSBasedSparkClient token bypass", applied))
    
    # Check log viewer files
    log_viewer_files_exist = all((repo_root / rel_path).exists() for rel_path in DEVMODE_FILES.values())
    status.append(("Web log viewer files", log_viewer_files_exist))
    
    # Check Program.cs registration
    filepath = repo_root / FILES["Program"]
    content = read_file(filepath)
    if content:
        applied = "EDOG DevMode - Start log viewer server" in content
        status.append(("Log viewer server registration (Program.cs)", applied))
    
    # Check WorkloadApp.cs registration
    filepath = repo_root / FILES["WorkloadApp"]
    content = read_file(filepath)
    if content:
        applied = "EdogTelemetryInterceptor" in content
        status.append(("Log viewer telemetry interceptor (WorkloadApp.cs)", applied))
    
    # Check DisableFLTAuth (ParametersManifest.json)
    filepath = repo_root / FILES["ParametersManifest"]
    content = read_file(filepath)
    if content:
        applied = '"DisableFLTAuth": true' in content
        status.append(("DisableFLTAuth (ParametersManifest.json)", applied))
    
    # Check DisableFLTAuth (Test.json)
    filepath = repo_root / FILES["TestRollout"]
    content = read_file(filepath)
    if content:
        applied = '"DisableFLTAuth": true' in content
        status.append(("DisableFLTAuth (Test.json)", applied))
    
    all_applied = all(s[1] for s in status) if status else False
    any_applied = any(s[1] for s in status) if status else False
    
    for desc, applied in status:
        if applied:
            ui_success(desc)
        else:
            ui_error(desc)
    
    if all_applied:
        ui_success("All EDOG changes are applied")
    elif any_applied:
        ui_warn("Some EDOG changes are applied (partial state)")
    else:
        ui_error("No EDOG changes are applied")
    
    # Check for patch file
    patch_path = get_patch_file_path()
    if patch_path.exists():
        ui_dim(f"Patch file exists: {patch_path.name}")
        ui_dim("Run 'edog --revert' to cleanly undo changes")
    
    # Git safety warning
    if any_applied:
        warn_uncommitted_edog_changes(repo_root)
    
    return all_applied


def fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id, max_retries=MAX_BROWSER_RETRIES):
    """Fetch MWC token, using cached bearer when available.

    Flow:
        1. Check bearer cache — if valid, skip CBA entirely.
        2. Otherwise acquire via Silent CBA (~3-5 seconds, zero browser).
        3. Use bearer to fetch MWC token from redirect host.
        4. On MWC failure, clear stale bearer cache and retry.
    """
    for attempt in range(max_retries):
        if attempt > 0:
            ui_dim(f"Retry {attempt + 1}/{max_retries}...")

        bearer_token = get_bearer_token(username)
        if not bearer_token:
            ui_warn("Failed to capture Bearer token")
            continue

        ui_dim("Fetching MWC token...")
        mwc_token = fetch_mwc_token(bearer_token, workspace_id, artifact_id, capacity_id)

        if mwc_token:
            return mwc_token

        # MWC fetch failed — bearer might be stale, clear cache and retry
        ui_warn("MWC token fetch failed, clearing bearer cache...")
        cache_path = get_bearer_cache_path()
        cache_path.unlink(missing_ok=True)

    return None


# ============================================================================
# FLT Service Management
# ============================================================================
FLT_SERVICE_PROCESS = None  # Global reference to the service process

def get_entrypoint_path(repo_root):
    """Get path to the FLT service EntryPoint project."""
    return repo_root / "Service" / "Microsoft.LiveTable.Service.EntryPoint"


def start_flt_service(repo_root):
    """
    Start the FLT service using dotnet run.
    First builds to ensure code changes are compiled, then runs.
    Returns the process handle or None on failure.
    """
    global FLT_SERVICE_PROCESS
    
    entrypoint = get_entrypoint_path(repo_root)
    if not entrypoint.exists():
        ui_error(f"EntryPoint not found: {entrypoint}")
        return None
    
    ui_dim(f"Project: {entrypoint}")
    
    try:
        # Step 1: Build first to ensure changes are compiled
        ui_step("Building project (to compile code changes)...")
        build_result = subprocess.run(
            ["dotnet", "build", str(entrypoint), "--no-incremental"],
            capture_output=True,
            text=True,
            cwd=str(repo_root)
        )
        
        if build_result.returncode != 0:
            ui_error("Build failed:")
            for line in build_result.stdout.split('\n')[-20:]:
                if line.strip():
                    ui_dim(f"  {line}")
            return None
        
        ui_success("Build successful")
        
        # Step 2: Run the service from the EntryPoint directory (required for WorkloadParameters)
        ui_step("Launching service...")
        process = subprocess.Popen(
            ["dotnet", "run", "--no-build"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(entrypoint)  # Run from EntryPoint dir so it finds WorkloadParameters
        )
        
        FLT_SERVICE_PROCESS = process
        ui_success(f"Service started (PID: {process.pid})")
        return process
        
    except FileNotFoundError:
        ui_error("'dotnet' not found. Make sure .NET SDK is installed and in PATH.")
        return None
    except Exception as e:
        ui_error(f"Failed to start service: {e}")
        return None


def stop_flt_service(process=None, timeout=10):
    """
    Stop the FLT service gracefully.
    Sends SIGTERM first, then SIGKILL after timeout.
    Returns True if stopped successfully.
    """
    global FLT_SERVICE_PROCESS
    
    proc = process or FLT_SERVICE_PROCESS
    if not proc:
        return True
    
    if proc.poll() is not None:
        # Already terminated
        FLT_SERVICE_PROCESS = None
        return True
    
    ui_step(f"Stopping FLT Service (PID: {proc.pid})...")
    
    try:
        # Try graceful termination first
        proc.terminate()
        
        try:
            proc.wait(timeout=timeout)
            ui_success("Service stopped gracefully")
            FLT_SERVICE_PROCESS = None
            return True
        except subprocess.TimeoutExpired:
            ui_warn(f"Service didn't stop in {timeout}s, forcing kill...")
            proc.kill()
            proc.wait(timeout=5)
            ui_success("Service killed")
            FLT_SERVICE_PROCESS = None
            return True
            
    except Exception as e:
        ui_error(f"Error stopping service: {e}")
        FLT_SERVICE_PROCESS = None
        return False


def stream_service_output(process, stop_event, connected_event=None):
    """
    Stream service output to console in a background thread.
    Runs until stop_event is set or process ends.
    
    If connected_event is provided, suppresses output until
    'Dev Connection established successfully' is seen (or timeout),
    then signals the event and starts streaming.
    """
    waiting_for_connection = connected_event is not None
    connected = False
    try:
        while not stop_event.is_set() and process.poll() is None:
            line = process.stdout.readline()
            if line:
                stripped = line.rstrip()
                # Check for successful deployment
                if waiting_for_connection and 'Dev Connection established successfully' in stripped:
                    connected_event.set()
                    waiting_for_connection = False
                    connected = True
                    continue
                # After connection: suppress all logs (use log viewer instead)
                # Before connection: also suppress noisy startup logs
                if not waiting_for_connection and not connected:
                    # Detect log level for colored output
                    line_upper = stripped.upper()
                    if any(k in line_upper for k in ("ERROR", "FATAL", "EXCEPTION", "FAIL")):
                        level = "error"
                    elif any(k in line_upper for k in ("WARN", "WARNING")):
                        level = "warn"
                    elif "SUCCESS" in line_upper:
                        level = "success"
                    else:
                        level = "info"
                    ui_log(f"[FLT] {stripped}", level=level)
    except Exception:
        pass
    # If process ended without connection signal, set event to unblock main thread
    if connected_event and not connected_event.is_set():
        connected_event.set()


def inject_devmode_token(username, flt_repo_path):
    """Acquire a token with the MwcFrontendBaseEndpoint audience and inject
    it as UserAuthorizationToken into workload-dev-mode.json.

    WCL SDK checks this field on startup — if present, it skips the browser
    popup entirely.  Zero-popup auth, no pywinauto needed.

    NOTE: This is a DIFFERENT token from the bearer live file.
      - Live file bearer  → audience: PowerBI API → used for MWC generation
      - This token         → audience: MwcFrontendBaseEndpoint → used by WCL SDK

    Returns:
        datetime expiry of the injected token, or None on failure.
    """
    devmode_path = get_workload_dev_mode_path(flt_repo_path)
    if not devmode_path or not devmode_path.exists():
        ui_warn("workload-dev-mode.json not found — browser popup may appear")
        return None

    try:
        data = json.loads(devmode_path.read_text(encoding="utf-8"))
        mwc_endpoint = data.get("MwcFrontendBaseEndpoint", "")
        if not mwc_endpoint:
            ui_warn("No MwcFrontendBaseEndpoint in config — skipping token injection")
            return None

        # Strip trailing port/slash for the resource URI
        resource = mwc_endpoint.rstrip("/")
        if resource.endswith(":443"):
            resource = resource[:-4]

        # Acquire token with MwcFrontendBaseEndpoint as audience
        ui_dim(f"Acquiring DevMode token (audience: {resource})...")
        devmode_token = _try_silent_cba(username, resource=resource)
        if not devmode_token:
            ui_warn("Could not acquire DevMode token — browser popup may appear")
            return None

        data["UserAuthorizationToken"] = devmode_token
        # Atomic write
        tmp = devmode_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        tmp.replace(devmode_path)

        expiry = parse_jwt_expiry(devmode_token)
        ui_success(f"Injected UserAuthorizationToken → zero-popup auth (expires: {expiry.strftime('%I:%M:%S %p') if expiry else 'unknown'})")
        return expiry
    except Exception as e:
        ui_warn(f"Token injection failed: {e} — browser popup may appear")
        return None


def print_session_summary(session_start, stats):
    """Print session summary on exit."""
    duration = datetime.now() - session_start
    total_secs = int(duration.total_seconds())
    if total_secs >= 3600:
        hrs = total_secs // 3600
        mins = (total_secs % 3600) // 60
        dur_str = f"{hrs}h {mins}m"
    elif total_secs >= 60:
        mins = total_secs // 60
        secs = total_secs % 60
        dur_str = f"{mins}m {secs}s"
    else:
        dur_str = f"{total_secs}s"

    refreshes = stats.get("token_refreshes", 0)
    failures = stats.get("refresh_failures", 0)
    restarts = stats.get("service_restarts", 0)

    parts = [f"Session: {dur_str}"]
    parts.append(f"{refreshes} token refresh{'es' if refreshes != 1 else ''}")
    if failures:
        parts.append(f"{failures} failure{'s' if failures != 1 else ''}")
    if restarts:
        parts.append(f"{restarts} restart{'s' if restarts != 1 else ''}")

    summary = " · ".join(parts)

    if RICH_AVAILABLE:
        from rich.panel import Panel
        console.print(Panel(
            f"[bold]👋  EDOG DevMode stopped[/bold]\n{summary}\nAll changes reverted. Clean state.",
            border_style="dim", expand=False
        ))
    else:
        print(f"👋  {summary}")
        print("✅ All changes reverted. Clean state.")


def watch_for_git_changes(repo_root, workspace_id, stop_event, reapply_lock):
    """Watch patched files for external changes (git pull/stash/checkout).
    
    If EDOG markers disappear from a patched file, revert all and reapply.
    Uses polling (every 10s) on file mtimes to detect changes.
    """
    POLL_INTERVAL = 10  # seconds
    MARKERS = ("// EDOG", "EDOG DevMode")
    
    # Snapshot initial mtimes of patched files
    mtimes = {}
    for file_key, rel_path in FILES.items():
        try:
            filepath = repo_root / rel_path
            if filepath.exists():
                mtimes[file_key] = filepath.stat().st_mtime
        except Exception:
            pass
    
    while not stop_event.is_set():
        stop_event.wait(POLL_INTERVAL)
        if stop_event.is_set():
            break
        
        try:
            changed_files = []
            for file_key, rel_path in FILES.items():
                try:
                    filepath = repo_root / rel_path
                    if not filepath.exists():
                        continue
                    current_mtime = filepath.stat().st_mtime
                    prev_mtime = mtimes.get(file_key)
                    if prev_mtime and current_mtime != prev_mtime:
                        # File changed — check if EDOG markers are gone
                        content = filepath.read_text(encoding="utf-8", errors="replace")
                        if not any(marker in content for marker in MARKERS):
                            changed_files.append(file_key)
                    mtimes[file_key] = current_mtime
                except Exception:
                    pass
            
            if changed_files and not stop_event.is_set():
                with reapply_lock:
                    ui_warn(f"External change detected — EDOG markers lost in: {', '.join(changed_files)}")
                    ui_step("Re-applying EDOG patches...")
                    try:
                        revert_all_changes(repo_root)
                        apply_all_changes(repo_root, workspace_id=workspace_id)
                        ui_success("Patches re-applied successfully")
                        show_notification("EDOG DevMode", "Patches re-applied after external change")
                        # Update mtimes after reapply
                        for fk, rp in FILES.items():
                            try:
                                fp = repo_root / rp
                                if fp.exists():
                                    mtimes[fk] = fp.stat().st_mtime
                            except Exception:
                                pass
                    except Exception as e:
                        ui_error(f"Re-apply failed: {e}")
                        show_notification("EDOG DevMode", "⚠️ Patch re-apply failed!")
        except Exception:
            pass  # Watcher must not crash


def run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root, launch_service=True):
    """Main daemon loop - fetch token, apply changes, optionally launch service, monitor and refresh."""
    session_start = datetime.now()
    session_stats = {"token_refreshes": 0, "refresh_failures": 0, "service_restarts": 0}
    watcher_stop = threading.Event()
    reapply_lock = threading.Lock()

    # Check and sync capacity_id from workload-dev-mode.json
    synced_capacity = sync_capacity_from_workload(str(repo_root), silent=False)
    if synced_capacity and synced_capacity.lower() != capacity_id.lower():
        capacity_id = synced_capacity
        ui_dim(f"Using synced capacity_id: {capacity_id}")
    
    # Pre-warm cert cache so banner can show thumbprint
    cert_cn = username.replace("@", ".")
    _find_cert_thumbprint(cert_cn)
    
    # Detect stale patches from a previous dirty exit (BSOD, kill -9, crash)
    try:
        stale = detect_stale_patches(repo_root)
        if stale:
            ui_warn("Stale EDOG patches detected from a previous session!")
            ui_dim("This usually means EDOG crashed or was killed without cleanup.")
            for _file_key, rel_path in stale:
                ui_dim(f"  • {rel_path}")
            if ui_confirm("Revert stale patches before starting fresh?", default=True):
                revert_all_changes(repo_root)
                cleanup_bearer_live_token(workspace_id)
                ui_success("Stale patches reverted — starting fresh")
            else:
                ui_dim("Keeping existing patches (may cause conflicts)")
    except Exception as e:
        ui_warn(f"Stale patch detection failed: {e} — continuing anyway")
    
    # Show daemon banner
    if RICH_AVAILABLE:
        banner_config = {
            "username": username,
            "workspace_id": workspace_id,
            "artifact_id": artifact_id,
            "capacity_id": capacity_id,
        }
        show_banner()
        set_terminal_title("EDOG 🐕 | Starting...")
        show_config_table(banner_config)
        ui_dim(f"Auto-launch: {'Yes' if launch_service else 'No'}")
    else:
        print("=" * 70)
        print("EDOG DevMode Token Manager")
        print("=" * 70)
        print(f"Username:  {username}")
        print(f"Workspace: {workspace_id}")
        print(f"Artifact:  {artifact_id}")
        print(f"Capacity:  {capacity_id}")
        print(f"Auto-launch: {'Yes' if launch_service else 'No'}")
        print("=" * 70)
    
    # Get bearer token (C# service will use this to generate MWC tokens itself)
    try:
        ui_step("Acquiring bearer token...")
        bearer_token = get_bearer_token(username)
        if not bearer_token:
            ui_error("Failed to acquire bearer token")
            return 1
        
        bearer_expiry = parse_jwt_expiry(bearer_token)
        ui_success(f"Bearer acquired (expires: {bearer_expiry.strftime('%I:%M:%S %p') if bearer_expiry else 'unknown'})")
        
        # Write bearer to live file BEFORE applying changes (C# bypass reads from this file)
        write_bearer_live_token(bearer_token, bearer_expiry.timestamp() if bearer_expiry else None, workspace_id)
        
        # Apply code patches (token-independent — C# reads bearer from file)
        if not apply_all_changes(repo_root, workspace_id=workspace_id):
            ui_warn("Some changes could not be applied")
        
        ui_success("Code changes applied successfully")
        
        # Start FLT service if requested
        service_process = None
        stop_event = None
        output_thread = None
        
        # Track DevMode token expiry separately (different audience → different lifetime)
        devmode_expiry = None

        # Inject DevMode token into workload-dev-mode.json (always, even --no-launch)
        # WCL SDK picks this up → skips browser popup entirely
        devmode_expiry = inject_devmode_token(username, str(repo_root))

        if launch_service:
            ui_step("Starting FLT Service...")
            service_process = start_flt_service(repo_root)
            if service_process:
                # Start background thread to stream service output
                stop_event = threading.Event()
                connected_event = threading.Event()
                output_thread = threading.Thread(
                    target=stream_service_output,
                    args=(service_process, stop_event, connected_event),
                    daemon=True
                )
                output_thread.start()
                
                # Wait for Dev Connection (up to 120 seconds)
                ui_dim("Waiting for Dev Connection...")
                if connected_event.wait(timeout=120):
                    if service_process.poll() is None:
                        ui_success("Deployed successfully! Logs available at http://localhost:5050")
                    else:
                        ui_warn(f"Service exited during startup (code: {service_process.returncode})")
                else:
                    ui_warn("Dev Connection not detected within 120s — service may still be starting")
                    ui_dim("Check logs at http://localhost:5050")
            else:
                ui_warn("Service failed to start, continuing with token management only")
    except KeyboardInterrupt:
        # User hit Ctrl+C during setup/build/deploy — clean shutdown
        ui_step("Shutting down...")
        watcher_stop.set()
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if service_process:
                if stop_event:
                    stop_event.set()
                stop_flt_service(service_process)
            revert_all_changes(repo_root)
            cleanup_bearer_live_token(workspace_id)
            reset_terminal_title()
            print_session_summary(session_start, session_stats)
        except Exception as e:
            ui_error(f"Error during cleanup: {e}")
            ui_dim("Run 'edog --revert' to manually revert changes.")
        return 0
    
    # Start git change watcher thread
    watcher_thread = threading.Thread(
        target=watch_for_git_changes,
        args=(repo_root, workspace_id, watcher_stop, reapply_lock),
        daemon=True
    )
    watcher_thread.start()
    ui_dim("Git change watcher active (auto-reapply on external changes)")

    # Monitor loop
    ui_step("Monitoring token expiry (Ctrl+C to stop)")
    ui_dim(f"Check interval: {CHECK_INTERVAL_MINS} mins | Refresh threshold: {REFRESH_THRESHOLD_MINS} mins remaining")
    if service_process:
        ui_dim(f"FLT Service: Running (PID: {service_process.pid})")
        ui_dim("Service logs available at http://localhost:5050")
    
    try:
        while True:
            # Check if service crashed
            if service_process and service_process.poll() is not None:
                exit_code = service_process.returncode
                ui_warn(f"FLT Service exited (code: {exit_code})")
                show_notification("EDOG DevMode", f"⚠️ FLT Service exited (code: {exit_code})")
                service_process = None
            
            # Calculate time remaining — use the EARLIER expiry of the two tokens
            bearer_remaining = get_token_time_remaining(bearer_expiry)
            devmode_remaining = get_token_time_remaining(devmode_expiry) if devmode_expiry else None
            remaining = min(bearer_remaining, devmode_remaining) if (bearer_remaining and devmode_remaining) else (bearer_remaining or devmode_remaining)
            remaining_str = format_timedelta(remaining)
            
            status = f"Bearer: {format_timedelta(bearer_remaining)}"
            if devmode_expiry:
                status += f" | DevMode: {format_timedelta(devmode_remaining)}"
            if service_process:
                status += " | Service: Running"
            ui_info(f"[{datetime.now().strftime('%I:%M:%S %p')}] {status}")
            
            # Update terminal title with token countdown
            if remaining:
                total_mins = int(remaining.total_seconds() / 60)
                title = f"EDOG 🐕 | Token: {total_mins}m left"
                if service_process:
                    title += " | Service: Running"
                set_terminal_title(title)
            
            # Check if refresh needed(triggers on whichever token expires first)
            if remaining and remaining <= timedelta(minutes=REFRESH_THRESHOLD_MINS):
                ui_step("Token expiring soon, refreshing...")
                show_notification("EDOG DevMode", "Token expiring, refreshing...")
                
                new_bearer = get_bearer_token(username)
                
                if new_bearer:
                    bearer_token = new_bearer
                    bearer_expiry = parse_jwt_expiry(bearer_token)
                    ui_success(f"Bearer refreshed (expires: {bearer_expiry.strftime('%I:%M:%S %p') if bearer_expiry else 'unknown'})")
                    session_stats["token_refreshes"] += 1

                    # Update the live bearer file (PowerBI API audience)
                    write_bearer_live_token(bearer_token, bearer_expiry.timestamp() if bearer_expiry else None, workspace_id)
                    # Refresh UserAuthorizationToken (MwcFrontendBaseEndpoint audience)
                    devmode_expiry = inject_devmode_token(username, str(repo_root))
                    show_notification("EDOG DevMode", f"Tokens refreshed! Expires {bearer_expiry.strftime('%H:%M')}")
                else:
                    ui_error("Failed to refresh tokens - continuing with old ones")
                    session_stats["refresh_failures"] += 1
                    show_notification("EDOG DevMode", "⚠️ Token refresh failed!")
            
            # Wait for next check
            ui_dim(f"Next check in {CHECK_INTERVAL_MINS} mins...")
            time.sleep(CHECK_INTERVAL_MINS * 60)
            
    except KeyboardInterrupt:
        ui_step("Shutting down...")
        watcher_stop.set()
        
        # Block further Ctrl+C during cleanup
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        try:
            # Step 1: Stop service first (sequential cleanup)
            if service_process:
                if stop_event:
                    stop_event.set()  # Signal output thread to stop
                stop_flt_service(service_process)
            
            # Step 2: Revert code changes
            revert_all_changes(repo_root)
            
            # Step 3: Clean up live bearer file
            cleanup_bearer_live_token(workspace_id)
            
            reset_terminal_title()
            print_session_summary(session_start, session_stats)
        except Exception as e:
            ui_error(f"Error during cleanup: {e}")
            ui_dim("Run 'edog --revert' to manually revert changes.")
        
        return 0
    
    return 0


# ============================================================================
# Entry point
# ============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="EDOG DevMode Token Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  edog                              Start daemon + auto-launch FLT service
  edog --no-launch                  Token management only (no service launch)
  edog --revert                     Revert all EDOG changes  
  edog --status                     Check if changes are applied
  edog --logs                       Open web log viewer in browser
  edog --doctor                     Run diagnostic checks
  edog --config                     Show current config
  edog --config -u <email>          Update username/email
  edog --config -w <id> -a <id>     Update workspace and artifact IDs
  edog --config -r C:\\path\\to\\FLT  Set FLT repo path
  edog --install-hook               Install git pre-commit hook
  edog --uninstall-hook             Remove git pre-commit hook
  edog --setup                      Re-run setup (install deps, build helper)

Token flow:
  Silent CBA → bearer token → live file → C# reads → POST /generatemwctoken
  Silent CBA → devmode token → workload-dev-mode.json → WCL SDK (no popup)
        """
    )
    
    parser.add_argument("--revert", action="store_true", help="Revert all EDOG changes")
    parser.add_argument("--status", action="store_true", help="Check if EDOG changes are applied")
    parser.add_argument("--config", action="store_true", help="Show or update config")
    parser.add_argument("--clear-token", action="store_true", help="Clear cached authentication token")
    parser.add_argument("--install-hook", action="store_true", help="Install git pre-commit hook")
    parser.add_argument("--uninstall-hook", action="store_true", help="Remove git pre-commit hook")
    parser.add_argument("--no-launch", action="store_true", help="Don't auto-launch FLT service (token management only)")
    parser.add_argument("--setup", action="store_true", help="Run setup (install deps, build token-helper, add to PATH)")
    parser.add_argument("--logs", action="store_true", help="Open log viewer in browser")
    parser.add_argument("--doctor", action="store_true", help="Run diagnostic checks")
    parser.add_argument("--no-update", action="store_true", help="Skip auto-update check")
    parser.add_argument("--bearer", action="store_true", help="Show bearer token path and copy to clipboard")
    parser.add_argument("--api", action="store_true", help="Interactive API REPL with bearer auth")
    parser.add_argument("-u", "--username", help="Username/Email for login")
    parser.add_argument("-w", "--workspace", help="Workspace ID")
    parser.add_argument("-a", "--artifact", help="Artifact ID")
    parser.add_argument("-c", "--capacity", help="Capacity ID")
    parser.add_argument("-r", "--repo", help="FabricLiveTable repo path")
    
    args = parser.parse_args()
    
    # Setup command
    if args.setup:
        run_setup(force=True)
        sys.exit(0)
    
    # Auto-setup on first run (token-helper not built)
    if _needs_setup():
        ui_info("First run detected — running setup...")
        print()
        if not run_setup():
            ui_error("Setup failed. Fix the issues above and retry.")
            sys.exit(1)
        print()
    
    # Auto-update (unless --no-update or a standalone command)
    if not args.no_update and not any([args.config, args.clear_token, args.doctor, args.setup,
                                       args.install_hook, args.uninstall_hook, args.logs,
                                       args.bearer, args.api]):
        updated = auto_update()
        if updated:
            ui_dim("Please restart edog to use the updated version.")
            sys.exit(0)
    
    # Config command doesn't need repo_root
    if args.config:
        if args.username or args.workspace or args.artifact or args.capacity or args.repo:
            update_config(args.username, args.workspace, args.artifact, args.capacity, args.repo)
        else:
            show_config()
        sys.exit(0)
    
    # Clear token command doesn't need repo_root
    if args.clear_token:
        clear_token_cache()
        ui_success("Token cache cleared")
        sys.exit(0)
    
    # Logs command doesn't need repo_root
    if args.logs:
        import webbrowser
        webbrowser.open("http://localhost:5050")
        ui_info("Opening EDOG Log Viewer at http://localhost:5050")
        ui_dim("Make sure FLT service is running with EDOG changes applied.")
        sys.exit(0)
    
    # Doctor command doesn't need repo_root (handles it internally)
    if args.doctor:
        run_doctor()
        sys.exit(0)
    
    # Bearer export command
    if args.bearer:
        config = load_config()
        workspace_id = args.workspace or config.get("workspace_id")
        if not workspace_id:
            ui_error("No workspace_id configured. Run 'edog --config' first.")
            sys.exit(1)
        live_path = get_bearer_live_path(workspace_id)
        if not live_path.exists():
            ui_error(f"No bearer token found at {live_path}")
            ui_dim("Start edog first to generate a token.")
            sys.exit(1)

        raw = live_path.read_text(encoding="utf-8").strip()
        token = raw.split("|")[0] if "|" in raw else raw

        show_banner()
        ui_step("Bearer Token Export")
        print()
        ui_info(f"Token file: {live_path}")
        ui_info(f"Token length: {len(token)} chars")
        print()

        # Usage examples
        ui_step("Usage Examples")
        ui_dim(f'  curl -H "Authorization: Bearer $(cat {live_path})" <url>')
        ui_dim(f'  $token = (Get-Content "{live_path}").Split("|")[0]')
        ui_dim(f'  Invoke-RestMethod -Headers @{{Authorization="Bearer $token"}} -Uri <url>')
        print()

        # Copy to clipboard
        try:
            subprocess.run(["clip"], input=token.encode(), check=True, timeout=5)
            ui_success("Token copied to clipboard!")
        except Exception:
            ui_dim("Could not copy to clipboard — use the file path above")

        sys.exit(0)

    # API REPL command
    if args.api:
        config = load_config()
        workspace_id = args.workspace or config.get("workspace_id")
        if not workspace_id:
            ui_error("No workspace_id configured. Run 'edog --config' first.")
            sys.exit(1)
        run_api_repl(workspace_id)
        sys.exit(0)

    # All other commands need repo_root
    repo_root = get_repo_root()
    if not repo_root:
        sys.exit(1)
    
    if args.install_hook:
        install_git_hook(repo_root)
        sys.exit(0)
    elif args.uninstall_hook:
        uninstall_git_hook(repo_root)
        sys.exit(0)
    elif args.revert:
        revert_all_changes(repo_root)
        sys.exit(0)
    elif args.status:
        check_status(repo_root)
        sys.exit(0)
    else:
        # Run daemon mode - get config first
        config = load_config()
        
        # Override with command line args if provided
        username = args.username or config.get("username") or DEFAULT_USERNAME
        workspace_id = args.workspace or config.get("workspace_id")
        artifact_id = args.artifact or config.get("artifact_id")
        capacity_id = args.capacity or config.get("capacity_id")
        
        # If still missing, prompt user
        if not workspace_id or not artifact_id or not capacity_id:
            config = ensure_config()
            if not config:
                ui_error("Cannot proceed without config")
                sys.exit(1)
            username = config.get("username") or DEFAULT_USERNAME
            workspace_id = config["workspace_id"]
            artifact_id = config["artifact_id"]
            capacity_id = config["capacity_id"]
        
        sys.exit(run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root, launch_service=not args.no_launch))
