"""
EDOG DevMode Token Manager

Commands:
  edog.cmd                 - Fetch token, apply changes, monitor & auto-refresh
  edog.cmd --revert        - Revert all EDOG changes
  edog.cmd --status        - Check if EDOG changes are applied

Features:
  - Auto-fetches MWC token via browser automation
  - Applies EDOG bypass changes to codebase
  - Monitors token expiry and auto-refreshes when ≤10 mins remaining
  - Pattern-based revert (works even after script restart)
"""

import asyncio
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
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding for emoji/unicode characters
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "msedge"], check=True)
    from playwright.async_api import async_playwright

try:
    from pywinauto import Desktop
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    print("Installing pywinauto...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pywinauto"], check=True)
    from pywinauto import Desktop
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True

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

# File paths relative to repo root
SERVICE_PATH = Path("Service/Microsoft.LiveTable.Service")
FILES = {
    "LiveTableController": SERVICE_PATH / "Controllers/LiveTableController.cs",
    "LiveTableSchedulerRunController": SERVICE_PATH / "Controllers/LiveTableSchedulerRunController.cs",
    "GTSOperationManager": SERVICE_PATH / "Managers/GTSOperationManager.cs",
    "GTSBasedSparkClient": SERVICE_PATH / "SparkHttp/GTSBasedSparkClient.cs",
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
            print(f"⚠️ Could not load config: {e}")
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
        print(f"❌ Could not save config: {e}")
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
        print(f"⚠️ Could not update workload-dev-mode.json: {e}")
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
            print(f"\n🔄 Synced capacity_id from workload-dev-mode.json:")
            if old_val:
                print(f"   Old: {old_val}")
            print(f"   New: {workload_val}")
        
        return workload_val
    
    return edog_val


def validate_guid(value):
    """Validate GUID format. Returns True if valid."""
    guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    return bool(re.match(guid_pattern, value))


def prompt_guid(prompt_text, field_name):
    """Prompt for a GUID with validation and retry."""
    while True:
        value = input(prompt_text).strip()
        if not value:
            print(f"   ❌ {field_name} is required")
            continue
        if validate_guid(value):
            return value
        print(f"   ❌ Invalid format: {value}")
        print(f"      Expected: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars, got {len(value)})")
        print(f"      Please try again.\n")


def prompt_for_config(flt_repo_path=None):
    """Prompt user to enter config values. Auto-detects capacity_id from workload-dev-mode.json if available."""
    print("\n📝 First-time setup - please enter your EDOG environment details:")
    print("   (You can find these in Fabric portal URL or workload-dev-mode.json)\n")
    
    username = input(f"   Username/Email [{DEFAULT_USERNAME}]: ").strip()
    if not username:
        username = DEFAULT_USERNAME
    
    workspace_id = prompt_guid("   Workspace ID: ", "Workspace ID")
    artifact_id = prompt_guid("   Artifact ID (Lakehouse): ", "Artifact ID")
    
    # Try to auto-detect capacity_id from workload-dev-mode.json
    workload_config = read_workload_dev_mode_config(flt_repo_path)
    detected_capacity = workload_config.get("capacity_id")
    
    if detected_capacity:
        workload_path = get_workload_dev_mode_path(flt_repo_path)
        print(f"\n   ✅ Found CapacityGuid in workload-dev-mode.json:")
        print(f"      Path: {workload_path}")
        print(f"      Value: {detected_capacity}")
        use_detected = input(f"   Use this capacity ID? [Y/n]: ").strip().lower()
        if use_detected != 'n':
            capacity_id = detected_capacity
            print(f"   ✅ Using capacity ID from workload-dev-mode.json")
        else:
            capacity_id = prompt_guid("   Capacity ID: ", "Capacity ID")
    else:
        capacity_id = prompt_guid("   Capacity ID: ", "Capacity ID")
    
    return {
        "username": username,
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "capacity_id": capacity_id
    }


def update_config(username=None, workspace_id=None, artifact_id=None, capacity_id=None, flt_repo_path=None):
    """Update specific config values. Also syncs capacity_id to workload-dev-mode.json."""
    config = load_config()
    
    if username:
        config["username"] = username
    if workspace_id:
        config["workspace_id"] = workspace_id
    if artifact_id:
        config["artifact_id"] = artifact_id
    if capacity_id:
        config["capacity_id"] = capacity_id
        # Also update workload-dev-mode.json for bidirectional sync
        if write_workload_dev_mode_config(capacity_id, config.get("flt_repo_path")):
            print(f"   🔄 Also updated CapacityGuid in workload-dev-mode.json")
    if flt_repo_path:
        # Validate the path
        repo_path = Path(flt_repo_path).resolve()
        if (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            config["flt_repo_path"] = str(repo_path)
        else:
            print(f"❌ Invalid FLT repo path: {repo_path}")
            print("   Expected to find: Service/Microsoft.LiveTable.Service")
            return False
    
    if save_config(config):
        print("\n✅ Config updated:")
        print(f"   Username:  {config.get('username', DEFAULT_USERNAME)}")
        print(f"   Workspace: {config.get('workspace_id', 'not set')}")
        print(f"   Artifact:  {config.get('artifact_id', 'not set')}")
        print(f"   Capacity:  {config.get('capacity_id', 'not set')}")
        print(f"   FLT Repo:  {config.get('flt_repo_path', 'auto-detect')}")
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
        print("\n✅ Config saved to edog-config.json")
    
    return config


def show_config():
    """Display current config with sync status."""
    config = load_config()
    print("\n📋 Current EDOG config:")
    if config:
        print(f"   Username:  {config.get('username', DEFAULT_USERNAME + ' (default)')}")
        print(f"   Workspace: {config.get('workspace_id', 'not set')}")
        print(f"   Artifact:  {config.get('artifact_id', 'not set')}")
        print(f"   Capacity:  {config.get('capacity_id', 'not set')}")
        print(f"   FLT Repo:  {config.get('flt_repo_path', 'auto-detect (current directory)')}")
        print(f"\n   Config file: {get_config_path()}")
        
        # Check sync status with workload-dev-mode.json
        is_synced, edog_val, workload_val, workload_path = check_capacity_sync(config.get("flt_repo_path"))
        if workload_path and workload_path.exists():
            print(f"\n   📁 workload-dev-mode.json: {workload_path}")
            if is_synced:
                print(f"   ✅ Capacity ID is in sync")
            else:
                print(f"   ⚠️  Capacity ID OUT OF SYNC:")
                print(f"      edog-config.json:        {edog_val or 'not set'}")
                print(f"      workload-dev-mode.json:  {workload_val or 'not set'}")
                print(f"      Run 'edog' to auto-sync from workload-dev-mode.json")
    else:
        print("   No config found. Run 'edog' to set up.")

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
    
    "auth_engine_ltc": {
        "anchor": "[AuthenticationEngine]",
        "context": "class LiveTableController",
        "context_distance": 20,  # Class definition may be several lines after attributes
        "action": "wrap_ifdef",
        "description": "AuthenticationEngine on LiveTableController"
    },
    "auth_engine_ltsrc": {
        "anchor": "[AuthenticationEngine]",
        "context": "class LiveTableSchedulerRunController",
        "context_distance": 20,
        "action": "wrap_ifdef",
        "description": "AuthenticationEngine on LiveTableSchedulerRunController"
    },
    "permission_filter_getlatestdag": {
        "anchor": "[RequiresPermissionFilter(Permissions.ReadAll)]",
        "context": "getLatestDag",
        "context_distance": 5,
        "action": "wrap_ifdef",
        "description": "RequiresPermissionFilter on getLatestDag"
    },
    "permission_filter_rundag": {
        "anchor": "[MwcV2RequirePermissionsFilter(",
        "context": "runDAG",
        "context_distance": 5,
        "action": "wrap_ifdef",
        "description": "MwcV2RequirePermissionsFilter on runDAG"
    },
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
# Legacy Patterns (keeping for token replacement which needs exact matching)
# ============================================================================
PATTERNS = {
    # (original, modified, description)
    # Using #if EDOG_DEVMODE preprocessor directive to disable - avoids StyleCop issues and is reversible
    "auth_engine_ltc": (
        "    [AuthenticationEngine]\n",
        "#if EDOG_DEVMODE  // EDOG DevMode - disabled\n    [AuthenticationEngine]\n#endif\n",
        "AuthenticationEngine on LiveTableController"
    ),
    "auth_engine_ltsrc": (
        "    [AuthenticationEngine]\n",
        "#if EDOG_DEVMODE  // EDOG DevMode - disabled\n    [AuthenticationEngine]\n#endif\n",
        "AuthenticationEngine on LiveTableSchedulerRunController"
    ),
    "permission_filter_getlatestdag": (
        "        [RequiresPermissionFilter(Permissions.ReadAll)]\n",
        "#if EDOG_DEVMODE  // EDOG DevMode - disabled\n        [RequiresPermissionFilter(Permissions.ReadAll)]\n#endif\n",
        "RequiresPermissionFilter on getLatestDag"
    ),
    "permission_filter_rundag": (
        "        [MwcV2RequirePermissionsFilter([Permissions.ReadAll, Permissions.Execute])]\n",
        "#if EDOG_DEVMODE  // EDOG DevMode - disabled\n        [MwcV2RequirePermissionsFilter([Permissions.ReadAll, Permissions.Execute])]\n#endif\n",
        "MwcV2RequirePermissionsFilter on runDAG"
    ),
}


# ============================================================================
# EDOG change management
# ============================================================================


def handle_certificate_dialog(username):
    """Background thread to handle the Windows certificate selection dialog."""
    print("   🔍 Watching for certificate dialog...")
    
    # Derive cert subject from username
    cert_subject = username.replace("@", ".") if username else ""
    
    for attempt in range(30):  # Try for 30 seconds
        time.sleep(1)
        try:
            desktop = Desktop(backend="uia")
            dialog = None
            for title in ["Windows Security", "Select a certificate", "Choose a digital certificate"]:
                try:
                    dialog = desktop.window(title_re=f".*{title}.*", visible_only=True)
                    if dialog.exists():
                        break
                except:
                    continue
            
            if not dialog or not dialog.exists():
                continue
                
            print(f"   ✅ Found certificate dialog!")
            
            try:
                list_ctrl = dialog.child_window(control_type="List")
                if list_ctrl.exists():
                    items = list_ctrl.children()
                    for item in items:
                        item_text = item.window_text()
                        # Match cert based on configured username
                        if cert_subject and cert_subject.lower() in item_text.lower():
                            print(f"   ✅ Selecting certificate: {item_text[:50]}...")
                            item.click_input()
                            time.sleep(0.5)
                            break
            except Exception as e:
                print(f"   ⚠️ Could not find cert in list: {e}")
            
            try:
                ok_btn = dialog.child_window(title="OK", control_type="Button")
                if ok_btn.exists():
                    print("   ✅ Clicking OK...")
                    ok_btn.click_input()
                    return True
            except Exception as e:
                print(f"   ⚠️ Could not click OK: {e}")
                
        except ElementNotFoundError:
            continue
        except Exception:
            continue
    
    print("   ⏳ Certificate dialog not found (may have been handled already)")
    return False


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
        print(f"⚠️ Could not parse token expiry: {e}")
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
    """Search for FabricLiveTable repo by looking for its unique folder structure.
    
    Uses a fallback strategy: first searches up to depth 4 (fast ~0.3s), 
    then falls back to depth 8 if not found (slower but more thorough).
    """
    home = Path.home()
    
    # Signature: repo must contain Service/Microsoft.LiveTable.Service
    def is_flt_repo(path):
        try:
            return (path / "Service" / "Microsoft.LiveTable.Service").exists()
        except (PermissionError, OSError):
            return False
    
    skip_dirs = {'.git', '.vs', '.vscode', 'node_modules', '__pycache__', 'bin', 'obj', 
                 'packages', 'AppData', '.nuget', '.dotnet', '.azure', 'OneDrive'}
    
    def search_dir(start_path, max_depth, current_depth=0):
        if current_depth > max_depth:
            return None
        try:
            for entry in start_path.iterdir():
                try:
                    if not entry.is_dir():
                        continue
                except (PermissionError, OSError):
                    continue
                # Skip hidden folders and known non-repo dirs
                if entry.name.startswith('.') or entry.name in skip_dirs:
                    continue
                # Check if this is the FLT repo
                if is_flt_repo(entry):
                    return entry
                # Recurse into subdirectory
                found = search_dir(entry, max_depth, current_depth + 1)
                if found:
                    return found
        except (PermissionError, OSError):
            pass
        return None
    
    # Fallback strategy: try shallow search first (fast), then deeper search if needed
    result = search_dir(home, max_depth=4)
    if result:
        return result
    
    # Not found at depth 4, try deeper search
    print("   Searching deeper for FLT repo...")
    return search_dir(home, max_depth=8)


def get_repo_root():
    """Get FLT repository root directory from config or auto-detect."""
    config = load_config()
    
    # First, check config for explicit repo path
    if config.get("flt_repo_path"):
        repo_path = Path(config["flt_repo_path"])
        if repo_path.exists() and (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            return repo_path
        else:
            print(f"⚠️ Configured FLT repo path no longer valid: {repo_path}")
            print(f"   → Update with: edog --config -r <new_path>")
    
    # Try current working directory
    cwd = Path.cwd()
    if (cwd / "Service" / "Microsoft.LiveTable.Service").exists():
        return cwd
    
    # Try parent directories (in case running from subdirectory)
    for parent in cwd.parents:
        if (parent / "Service" / "Microsoft.LiveTable.Service").exists():
            return parent
    
    # Auto-search common locations
    found = find_flt_repo()
    if found:
        # Save it to config for future use
        config["flt_repo_path"] = str(found)
        save_config(config)
        print(f"✅ Auto-detected FLT repo: {found}")
        return found
    
    # Not found - prompt user for path
    print("\n⚠️ FabricLiveTable repo not found automatically.")
    print("   Please enter the path to your workload-fabriclivetable repo.\n")
    
    while True:
        repo_input = input("   FLT Repo Path (or 'q' to quit): ").strip()
        if repo_input.lower() == 'q':
            return None
        if not repo_input:
            print("   ❌ Path is required")
            continue
        
        repo_path = Path(repo_input).resolve()
        if not repo_path.exists():
            print(f"   ❌ Path does not exist: {repo_path}")
            continue
        if not (repo_path / "Service" / "Microsoft.LiveTable.Service").exists():
            print(f"   ❌ Not a valid FLT repo (missing Service/Microsoft.LiveTable.Service)")
            continue
        
        # Valid path - save to config
        config["flt_repo_path"] = str(repo_path)
        save_config(config)
        print(f"   ✅ Saved FLT repo path: {repo_path}")
        return repo_path


def read_file(filepath):
    """Read file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except PermissionError:
        print(f"❌ File is locked: {filepath.name}")
        print(f"   → Close the file in Visual Studio/VS Code and retry")
        return None
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        print(f"   → Check if FLT repo path is correct: edog --config")
        print(f"   → The codebase structure may have changed")
        return None
    except Exception as e:
        print(f"❌ Error reading {filepath.name}: {e}")
        return None


def write_file(filepath, content):
    """Write file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except PermissionError:
        print(f"❌ File is locked: {filepath.name}")
        print(f"   → Close the file in Visual Studio/VS Code and retry")
        return False
    except Exception as e:
        print(f"❌ Error writing {filepath.name}: {e}")
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
        print()
        print("⚠️  WARNING: EDOG-modified files have uncommitted changes!")
        print("   Don't commit these files with EDOG changes.")
        print("   Run 'edog --revert' before committing.")
        print()
        for f in dirty_files:
            print(f"   • {f}")
        print()
        return True
    return False


def install_git_hook(repo_root):
    """Install a pre-commit hook that blocks commits with EDOG changes."""
    hooks_dir = repo_root / ".git" / "hooks"
    hook_file = hooks_dir / "pre-commit"
    
    if not hooks_dir.exists():
        print(f"❌ Git hooks directory not found: {hooks_dir}")
        return False
    
    # Hook script content
    hook_script = '''#!/bin/sh
# EDOG DevMode pre-commit hook
# Prevents accidental commits of EDOG-modified files

# Files that EDOG modifies
EDOG_FILES="LiveTableController.cs LiveTableSchedulerRunController.cs GTSOperationManager.cs GTSBasedSparkClient.cs"

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
            print("✅ EDOG pre-commit hook already installed")
            return True
        else:
            # Backup existing hook
            backup = hook_file.with_suffix(".pre-edog-backup")
            hook_file.rename(backup)
            print(f"   Backed up existing hook to: {backup.name}")
    
    try:
        hook_file.write_text(hook_script, encoding='utf-8')
        # Make executable (on Unix)
        import stat
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IEXEC)
        print(f"✅ Installed EDOG pre-commit hook")
        print(f"   Location: {hook_file}")
        print(f"   Commits with EDOG changes will now be blocked.")
        return True
    except Exception as e:
        print(f"❌ Failed to install hook: {e}")
        return False


def uninstall_git_hook(repo_root):
    """Remove the EDOG pre-commit hook."""
    hook_file = repo_root / ".git" / "hooks" / "pre-commit"
    
    if not hook_file.exists():
        print("   No pre-commit hook found")
        return True
    
    content = hook_file.read_text()
    if "EDOG DevMode pre-commit hook" not in content:
        print("   Pre-commit hook exists but is not EDOG's hook")
        return False
    
    try:
        hook_file.unlink()
        print("✅ Removed EDOG pre-commit hook")
        
        # Restore backup if exists
        backup = hook_file.with_suffix(".pre-edog-backup")
        if backup.exists():
            backup.rename(hook_file)
            print(f"   Restored previous hook from backup")
        
        return True
    except Exception as e:
        print(f"❌ Failed to remove hook: {e}")
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
        print(f"❌ Failed to write patch file: {e}")
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
            print("\n   ⚠️  Files were modified after EDOG changes were applied.")
            print("   Attempting 3-way merge to preserve your changes...")
            
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


def get_gts_operation_manager_token_pattern(token):
    """Get the pattern for GTSOperationManager token replacement."""
    original = 'var mwcV1TokenWithHeader = await HttpTokenUtils.GenerateMwcV1TokenHeaderAsync(mwcTokenHandler, workloadContext.ArtifactStoreServiceProvider.GetArtifactStoreServiceAsync(), userTJSToken, capacityContext, workspaceId, artifactId, Constants.LakehouseArtifactType, Constants.LakehouseTokenPermissions, default);'
    modified = f'var mwcV1TokenWithHeader = "MwcToken {token}";  // EDOG DevMode - hardcoded by edog tool'
    return original, modified


def get_gts_spark_client_bypass(token):
    """Get the bypass code for GTSBasedSparkClient."""
    bypass_code = f'''        protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)
        {{
            // EDOG DevMode - bypassing OBO token exchange (hardcoded by edog tool)
            var hardcodedToken = "{token}";
            Tracer.LogSanitizedWarning("[DevMode] Using hardcoded MWC V1 token");
            return await Task.FromResult(new Token
            {{
                Value = hardcodedToken,
                Expiry = DateTimeOffset.UtcNow.AddHours(1),
            }});
        }}'''
    return bypass_code


def apply_gts_operation_manager_change(content, token, repo_root=None):
    """Apply GTSOperationManager token change. Returns (new_content, status)."""
    edog_marker = '// EDOG DevMode - hardcoded by edog tool'
    original_marker_start = '// EDOG_GTS_OP_ORIGINAL:'
    original_marker_end = ':END_EDOG_GTS_OP'
    
    # Check if bypass is already there with same token
    modified_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  {edog_marker}'
    if modified_line in content:
        return content, "already_applied"
    
    # Check if bypass is there with different token (with EDOG marker)
    if edog_marker in content:
        # Check if we have stored original
        has_original = original_marker_start in content and original_marker_end in content
        
        if has_original:
            # Just update the token, preserving the stored original
            pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";  // EDOG DevMode - hardcoded by edog tool'
            new_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  {edog_marker}'
            new_content = re.sub(pattern, new_line, content)
            if new_content != content:
                return new_content, "token_updated"
        
        # No stored original - try to fetch from git and reapply properly
        if repo_root:
            try:
                file_rel_path = str(FILES["GTSOperationManager"]).replace('\\', '/')
                result = subprocess.run(
                    ['git', 'show', f'HEAD:{file_rel_path}'],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    git_content = result.stdout
                    # Recursively call to apply fresh bypass using git content as base
                    new_content, status = apply_gts_operation_manager_change(git_content, token, None)
                    if status == "applied":
                        return new_content, "applied_with_git_original"
            except Exception as e:
                print(f"⚠️ Could not fetch GTSOperationManager original from git: {e}")
        
        # Fallback: just update the token (no original will be stored)
        pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";  // EDOG DevMode - hardcoded by edog tool'
        new_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  {edog_marker}'
        new_content = re.sub(pattern, new_line, content)
        if new_content != content:
            return new_content, "token_updated"
    
    # Check if there's a hardcoded token WITHOUT the EDOG marker (manual edit) - update it
    manual_hardcode_pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";'
    if re.search(manual_hardcode_pattern, content) and edog_marker not in content:
        new_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  {edog_marker}'
        new_content = re.sub(manual_hardcode_pattern, new_line, content)
        if new_content != content:
            return new_content, "token_updated"
    
    # Apply fresh bypass - find the original line and store it
    original_pattern = r'var mwcV1TokenWithHeader = await HttpTokenUtils\.GenerateMwcV1TokenHeaderAsync\([^;]+\);'
    match = re.search(original_pattern, content)
    
    if match:
        original_line = match.group(0)
        # Base64 encode the original for safe storage
        original_encoded = base64.b64encode(original_line.encode('utf-8')).decode('ascii')
        # Build replacement with stored original
        replacement = f'var mwcV1TokenWithHeader = "MwcToken {token}";  {edog_marker}  {original_marker_start}{original_encoded}{original_marker_end}'
        new_content = content[:match.start()] + replacement + content[match.end():]
        return new_content, "applied"
    
    return content, "pattern_not_found"


def apply_gts_spark_client_change(content, token, repo_root=None):
    """Apply GTSBasedSparkClient bypass. Returns (new_content, status)."""
    edog_marker = '// EDOG DevMode - bypassing OBO token exchange'
    original_marker_start = '// EDOG_ORIGINAL_START:'
    original_marker_end = '// EDOG_ORIGINAL_END'
    
    # Check if bypass exists
    if edog_marker in content:
        # Check if we have the original stored
        has_original = original_marker_start in content and original_marker_end in content
        
        # Check if token is the same
        if f'var hardcodedToken = "{token}"' in content:
            return content, "already_applied"
        
        # If we have the original stored, just update the token
        if has_original:
            pattern = r'var hardcodedToken = "[^"]+";'
            new_content = re.sub(pattern, f'var hardcodedToken = "{token}";', content)
            if new_content != content:
                return new_content, "token_updated"
        
        # No original stored - need to fetch from git and rebuild the bypass with original
        if repo_root:
            try:
                file_rel_path = FILES["GTSBasedSparkClient"]
                result = subprocess.run(
                    ['git', 'show', f'HEAD:{file_rel_path}'],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    git_content = result.stdout
                    # Recursively call to apply fresh bypass using git content as base
                    # This will capture the original properly
                    new_content, status = apply_gts_spark_client_change(git_content, token, None)
                    if status == "applied":
                        return new_content, "applied_with_git_original"
            except Exception as e:
                print(f"⚠️ Could not fetch original from git: {e}")
        
        # Fallback: just update the token (no original will be stored)
        pattern = r'var hardcodedToken = "[^"]+";'
        new_content = re.sub(pattern, f'var hardcodedToken = "{token}";', content)
        if new_content != content:
            return new_content, "token_updated"
    
    # Apply fresh bypass - find the method signature and replace the entire method
    method_sig = 'protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)'
    
    if method_sig not in content:
        return content, "pattern_not_found"
    
    # Find the method start
    sig_start = content.find(method_sig)
    if sig_start == -1:
        return content, "pattern_not_found"
    
    # Find the opening brace after signature
    brace_start = content.find('{', sig_start)
    if brace_start == -1:
        return content, "pattern_not_found"
    
    # Find matching closing brace (count braces)
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
    
    # Find the start of the method block (including any comments/attributes before the signature)
    # Go back line by line until we hit a line that's not a comment, attribute, or whitespace
    line_start = content.rfind('\n', 0, sig_start) + 1
    method_start = line_start
    
    # Keep going back to include comments and attributes
    while method_start > 0:
        prev_line_end = method_start - 1
        if prev_line_end < 0:
            break
        prev_line_start = content.rfind('\n', 0, prev_line_end) + 1
        prev_line = content[prev_line_start:prev_line_end].strip()
        
        # Include lines that are comments, attributes, or empty
        if prev_line.startswith('//') or prev_line.startswith('/*') or prev_line.startswith('*') or prev_line.startswith('[') or prev_line == '':
            method_start = prev_line_start
        else:
            break
    
    # Capture the original content (everything from method_start to method_end)
    original_content = content[method_start:method_end]
    
    # Base64 encode the original content for safe storage
    original_encoded = base64.b64encode(original_content.encode('utf-8')).decode('ascii')
    
    # Build the bypass code with the original content stored as a comment
    bypass_code = f'''
        // EDOG_ORIGINAL_START:{original_encoded}
        protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)
        {{
            // EDOG DevMode - bypassing OBO token exchange (hardcoded by edog tool)
            var hardcodedToken = "{token}";
            Tracer.LogSanitizedWarning("[DevMode] Using hardcoded MWC V1 token");
            return await Task.FromResult(new Token
            {{
                Value = hardcodedToken,
                Expiry = DateTimeOffset.UtcNow.AddHours(1),
            }});
        }}'''
    
    new_content = content[:method_start] + bypass_code + content[method_end:]
    return new_content, "applied"


def revert_gts_operation_manager_change(content, repo_root=None):
    """Revert GTSOperationManager token change - restore original from stored backup or git."""
    edog_marker = '// EDOG DevMode - hardcoded by edog tool'
    original_marker_start = '// EDOG_GTS_OP_ORIGINAL:'
    original_marker_end = ':END_EDOG_GTS_OP'
    
    if edog_marker not in content:
        return content, False
    
    # Check if we have stored original content
    if original_marker_start in content and original_marker_end in content:
        # Extract the base64-encoded original
        start_idx = content.find(original_marker_start) + len(original_marker_start)
        end_idx = content.find(original_marker_end)
        
        if start_idx < end_idx:
            encoded_original = content[start_idx:end_idx]
            try:
                original_line = base64.b64decode(encoded_original.encode('ascii')).decode('utf-8')
                
                # Find and replace the entire modified line (including markers)
                pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";  // EDOG DevMode - hardcoded by edog tool  // EDOG_GTS_OP_ORIGINAL:[^:]+:END_EDOG_GTS_OP'
                new_content = re.sub(pattern, original_line, content)
                return new_content, new_content != content
                
            except Exception as e:
                print(f"⚠️ Failed to decode stored original for GTSOperationManager: {e}")
    
    # No stored original - try to restore from git
    if repo_root:
        try:
            file_rel_path = str(FILES["GTSOperationManager"]).replace('\\', '/')
            result = subprocess.run(
                ['git', 'show', f'HEAD:{file_rel_path}'],
                cwd=str(repo_root),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("   ℹ️  Restored GTSOperationManager from git HEAD (no stored original found)")
                return result.stdout, True
            else:
                print(f"⚠️ Git show failed for GTSOperationManager: {result.stderr.strip()}")
        except Exception as e:
            print(f"⚠️ Could not restore GTSOperationManager from git: {e}")
    
    # Legacy fallback: no stored original, print warning
    print("⚠️ No stored original found for GTSOperationManager. The bypass may have been applied with an older version.")
    print("   Please manually revert GTSOperationManager.cs using git checkout or restore from source control.")
    return content, False


def revert_gts_spark_client_change(content, repo_root=None):
    """Revert GTSBasedSparkClient bypass - restore original method from stored backup or git."""
    edog_marker = '// EDOG DevMode - bypassing OBO token exchange'
    original_marker_start = '// EDOG_ORIGINAL_START:'
    original_marker_end = '// EDOG_ORIGINAL_END'
    
    if edog_marker not in content:
        return content, False
    
    # Check if we have stored original content
    if original_marker_start in content and original_marker_end in content:
        # Extract the base64-encoded original
        start_idx = content.find(original_marker_start) + len(original_marker_start)
        end_idx = content.find(original_marker_end)
        
        if start_idx < end_idx:
            encoded_original = content[start_idx:end_idx].strip()  # strip newlines/whitespace
            try:
                original_content = base64.b64decode(encoded_original.encode('ascii')).decode('utf-8')
                
                # Find the start of the EDOG marker line
                marker_pos = content.find(original_marker_start)
                marker_line_start = content.rfind('\n', 0, marker_pos) + 1
                
                # The bypass block starts at marker_line_start and includes:
                # 1. The EDOG_ORIGINAL marker line
                # 2. The method signature and body
                # We need to find the method end (closing brace)
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
                
                # Replace the entire bypass block (from marker line to method end) with original
                # The original_content already includes the method signature, body, and any preceding comments
                # that were captured during apply - just restore it directly
                new_content = content[:marker_line_start] + original_content + content[method_end:]
                return new_content, True
                
            except Exception as e:
                print(f"⚠️ Failed to decode stored original: {e}")
                # Fall through to git-based restore
    
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
                print("   ℹ️  Restored from git HEAD (no stored original found)")
                return result.stdout, True
            else:
                print(f"⚠️ Git show failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"⚠️ Could not restore from git: {e}")
    
    # Legacy fallback: no stored original found, cannot revert safely
    print("⚠️ No stored original found. The bypass may have been applied with an older version.")
    print("   Please manually revert GTSBasedSparkClient.cs using git checkout or restore from source control.")
    return content, False


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
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        try:
            print(f"   Response: {e.read().decode('utf-8')[:500]}")
        except:
            pass
        return None
    except urllib.error.URLError as e:
        print(f"❌ URL Error: {e.reason}")
        return None
    except Exception as e:
        print(f"❌ Error fetching MWC token: {type(e).__name__}: {e}")
        return None


async def get_bearer_token(username):
    """Launch Edge, capture Bearer token."""
    
    if not username:
        print("❌ Username is required")
        return None
    
    print("🚀 Starting browser...")
    bearer_token = None
    
    # Extract cert subject from username (e.g., Admin1CBA@domain.net -> Admin1CBA.domain.net)
    cert_subject = username.replace("@", ".")
    cert_policy = f'{{"pattern":"*","filter":{{"SUBJECT":{{"CN":"{cert_subject}"}}}}}}'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                f'--auto-select-certificate-for-urls={cert_policy}',
                '--ignore-certificate-errors',
            ]
        )
        
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_request(request):
            nonlocal bearer_token
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer ey") and not bearer_token:
                bearer_token = auth.replace("Bearer ", "")
                print(f"✅ Captured Bearer token (length: {len(bearer_token)})")
        
        page.on("request", handle_request)
        
        print(f"📡 Navigating to {POWER_BI_URL}")
        try:
            await page.goto(POWER_BI_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️  Navigation: {type(e).__name__}")
        
        print("🔐 Checking for login prompts...")
        
        try:
            email_input = await page.wait_for_selector('input[type="email"], input[name="loginfmt"]', timeout=5000)
            if email_input:
                print(f"   Entering username: {username}")
                await email_input.fill(username)
                await page.keyboard.press("Enter")
                await asyncio.sleep(3)
        except:
            print("   Already logged in or no username prompt")
        
        print("   ⚠️  If certificate dialog appears, please select it manually")
        await asyncio.sleep(5)
        
        try:
            yes_button = await page.wait_for_selector('#idSIButton9, input[value="Yes"]', timeout=5000)
            if yes_button:
                print("   Clicking 'Yes' on stay signed in...")
                await yes_button.click()
                await asyncio.sleep(2)
        except:
            pass
        
        print("⏳ Waiting for Bearer token...")
        for _ in range(20):
            if bearer_token:
                break
            await asyncio.sleep(1)
        
        await browser.close()
        
    return bearer_token


# ============================================================================
# Main EDOG operations
# ============================================================================
def apply_all_changes(token, repo_root):
    """Apply all EDOG changes to codebase and generate a patch file for clean revert."""
    print("\n📝 Applying EDOG changes...")
    
    changes_made = []
    warnings = []
    original_contents = {}  # Store originals for patch generation
    modified_contents = {}  # Store modified for patch generation
    
    # 1. LiveTableController patterns (smart matching)
    rel_path = FILES["LiveTableController"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        original_contents[rel_path] = content
        modified = False
        for key in ["auth_engine_ltc", "permission_filter_getlatestdag"]:
            pattern_config = SMART_PATTERNS[key]
            new_content, status = apply_smart_pattern(content, pattern_config)
            desc = pattern_config["description"]
            
            if status == "applied":
                content = new_content
                modified = True
                changes_made.append(f"✅ {desc}")
            elif status == "already_applied":
                changes_made.append(f"⏭️  {desc} (already)")
            elif status == "anchor_not_found":
                warnings.append(f"⚠️  {desc}: anchor not found (code may have changed)")
            elif status == "context_mismatch":
                warnings.append(f"⚠️  {desc}: found anchor but wrong location")
        
        modified_contents[rel_path] = content
        if modified:
            write_file(filepath, content)
    
    # 2. LiveTableSchedulerRunController patterns (smart matching)
    rel_path = FILES["LiveTableSchedulerRunController"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        original_contents[rel_path] = content
        modified = False
        for key in ["auth_engine_ltsrc", "permission_filter_rundag"]:
            pattern_config = SMART_PATTERNS[key]
            new_content, status = apply_smart_pattern(content, pattern_config)
            desc = pattern_config["description"]
            
            if status == "applied":
                content = new_content
                modified = True
                changes_made.append(f"✅ {desc}")
            elif status == "already_applied":
                changes_made.append(f"⏭️  {desc} (already)")
            elif status == "anchor_not_found":
                warnings.append(f"⚠️  {desc}: anchor not found (code may have changed)")
            elif status == "context_mismatch":
                warnings.append(f"⚠️  {desc}: found anchor but wrong location")
        
        modified_contents[rel_path] = content
        if modified:
            write_file(filepath, content)
    
    # 3. GTSOperationManager - Token
    rel_path = FILES["GTSOperationManager"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        original_contents[rel_path] = content
        new_content, status = apply_gts_operation_manager_change(content, token, repo_root)
        if status in ["applied", "token_updated", "applied_with_git_original"]:
            write_file(filepath, new_content)
            modified_contents[rel_path] = new_content
            changes_made.append(f"✅ GTSOperationManager token")
        elif status == "already_applied":
            modified_contents[rel_path] = content
            changes_made.append(f"⏭️  GTSOperationManager token (already)")
        elif status == "pattern_not_found":
            modified_contents[rel_path] = content
            warnings.append(f"⚠️  GTSOperationManager token: pattern not found")
    
    # 4. GTSBasedSparkClient - Token bypass
    rel_path = FILES["GTSBasedSparkClient"]
    filepath = repo_root / rel_path
    content = read_file(filepath)
    if content:
        original_contents[rel_path] = content
        new_content, status = apply_gts_spark_client_change(content, token, repo_root)
        if status in ["applied", "token_updated", "applied_with_git_original"]:
            write_file(filepath, new_content)
            modified_contents[rel_path] = new_content
            changes_made.append(f"✅ GTSBasedSparkClient token bypass")
        elif status == "already_applied":
            modified_contents[rel_path] = content
            changes_made.append(f"⏭️  GTSBasedSparkClient token bypass (already)")
        elif status == "pattern_not_found":
            modified_contents[rel_path] = content
            warnings.append(f"⚠️  GTSBasedSparkClient: pattern not found")
    
    # Generate patch file for clean revert
    if generate_patch(original_contents, modified_contents, repo_root):
        print(f"\n   📄 Patch file saved: {get_patch_file_path().name}")
        print(f"      Use 'edog --revert' to cleanly undo all changes")
    
    # Print summary
    for msg in changes_made:
        print(f"   {msg}")
    
    # Print warnings
    if warnings:
        print()
        for msg in warnings:
            print(f"   {msg}")
    
    return len(warnings) == 0


def revert_all_changes(repo_root):
    """Revert all EDOG changes using the saved patch file."""
    print("\n🔄 Reverting EDOG changes...")
    
    success, message = apply_patch_reverse(repo_root)
    
    if success:
        print(f"   ✅ {message}")
    else:
        print(f"   ❌ {message}")
    
    return success


def check_status(repo_root):
    """Check if EDOG changes are applied using smart pattern matching."""
    print("\n🔍 Checking EDOG status...")
    
    status = []
    warnings = []
    
    # Check LiveTableController (smart matching)
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
        for key in ["auth_engine_ltc", "permission_filter_getlatestdag"]:
            pattern_config = SMART_PATTERNS[key]
            result = check_smart_pattern_status(content, pattern_config)
            desc = pattern_config["description"]
            
            if result == "applied":
                status.append((desc, True))
            elif result == "not_applied":
                status.append((desc, False))
            elif result == "anchor_not_found":
                warnings.append(f"⚠️  {desc}: anchor not found (code may have changed)")
            elif result == "context_mismatch":
                warnings.append(f"⚠️  {desc}: anchor found but wrong location")
    
    # Check LiveTableSchedulerRunController (smart matching)
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
        for key in ["auth_engine_ltsrc", "permission_filter_rundag"]:
            pattern_config = SMART_PATTERNS[key]
            result = check_smart_pattern_status(content, pattern_config)
            desc = pattern_config["description"]
            
            if result == "applied":
                status.append((desc, True))
            elif result == "not_applied":
                status.append((desc, False))
            elif result == "anchor_not_found":
                warnings.append(f"⚠️  {desc}: anchor not found")
            elif result == "context_mismatch":
                warnings.append(f"⚠️  {desc}: anchor found but wrong location")
    
    # Check GTSOperationManager (legacy - exact match)
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        has_edog_marker = "// EDOG DevMode - hardcoded by edog tool" in content
        has_manual_hardcode = re.search(r'var mwcV1TokenWithHeader = "MwcToken [^"]+";', content) is not None
        if has_edog_marker or has_manual_hardcode:
            status.append(("GTSOperationManager token", True))
        else:
            status.append(("GTSOperationManager token", False))
    
    # Check GTSBasedSparkClient (legacy - exact match)
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        applied = "// EDOG DevMode - bypassing OBO token exchange" in content
        status.append(("GTSBasedSparkClient token bypass", applied))
    
    all_applied = all(s[1] for s in status) if status else False
    any_applied = any(s[1] for s in status) if status else False
    
    for desc, applied in status:
        icon = "✅" if applied else "❌"
        print(f"   {icon} {desc}")
    
    # Print warnings
    for msg in warnings:
        print(f"   {msg}")
    
    print()
    if all_applied:
        print("   ✅ All EDOG changes are applied")
    elif any_applied:
        print("   ⚠️  Some EDOG changes are applied (partial state)")
    else:
        print("   ❌ No EDOG changes are applied")
    
    # Check for patch file
    patch_path = get_patch_file_path()
    if patch_path.exists():
        print(f"\n   📄 Patch file exists: {patch_path.name}")
        print(f"      Run 'edog --revert' to cleanly undo changes")
    
    # Git safety warning
    if any_applied:
        warn_uncommitted_edog_changes(repo_root)
    
    return all_applied


def fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id, max_retries=MAX_BROWSER_RETRIES):
    """Fetch MWC token with retry logic."""
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n🔄 Retry {attempt + 1}/{max_retries}...")
        
        bearer_token = asyncio.run(get_bearer_token(username))
        if not bearer_token:
            print("❌ Failed to capture Bearer token")
            continue
        
        print("\n📡 Fetching MWC token...")
        mwc_token = fetch_mwc_token(bearer_token, workspace_id, artifact_id, capacity_id)
        
        if mwc_token:
            return mwc_token
        
        print("❌ Failed to fetch MWC token")
    
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
        print(f"❌ EntryPoint not found: {entrypoint}")
        return None
    
    print(f"   Project: {entrypoint}")
    
    try:
        # Step 1: Build first to ensure changes are compiled
        print(f"   ⏳ Building project (to compile code changes)...")
        build_result = subprocess.run(
            ["dotnet", "build", str(entrypoint), "--no-incremental"],
            capture_output=True,
            text=True,
            cwd=str(repo_root)
        )
        
        if build_result.returncode != 0:
            print(f"   ❌ Build failed:")
            for line in build_result.stdout.split('\n')[-20:]:  # Last 20 lines
                if line.strip():
                    print(f"      {line}")
            return None
        
        print(f"   ✅ Build successful")
        
        # Step 2: Run the service from the EntryPoint directory (required for WorkloadParameters)
        print(f"   🚀 Launching service...")
        process = subprocess.Popen(
            ["dotnet", "run", "--no-build"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(entrypoint)  # Run from EntryPoint dir so it finds WorkloadParameters
        )
        
        FLT_SERVICE_PROCESS = process
        print(f"   ✅ Service started (PID: {process.pid})")
        return process
        
    except FileNotFoundError:
        print("❌ 'dotnet' not found. Make sure .NET SDK is installed and in PATH.")
        return None
    except Exception as e:
        print(f"❌ Failed to start service: {e}")
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
    
    print(f"\n🛑 Stopping FLT Service (PID: {proc.pid})...")
    
    try:
        # Try graceful termination first
        proc.terminate()
        
        try:
            proc.wait(timeout=timeout)
            print(f"   ✅ Service stopped gracefully")
            FLT_SERVICE_PROCESS = None
            return True
        except subprocess.TimeoutExpired:
            print(f"   ⚠️ Service didn't stop in {timeout}s, forcing kill...")
            proc.kill()
            proc.wait(timeout=5)
            print(f"   ✅ Service killed")
            FLT_SERVICE_PROCESS = None
            return True
            
    except Exception as e:
        print(f"   ❌ Error stopping service: {e}")
        FLT_SERVICE_PROCESS = None
        return False


def stream_service_output(process, stop_event):
    """
    Stream service output to console in a background thread.
    Runs until stop_event is set or process ends.
    """
    try:
        while not stop_event.is_set() and process.poll() is None:
            line = process.stdout.readline()
            if line:
                # Prefix service output to distinguish from edog messages
                print(f"   [FLT] {line.rstrip()}")
    except Exception:
        pass


def run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root, launch_service=True):
    """Main daemon loop - fetch token, apply changes, optionally launch service, monitor and refresh."""
    
    # Check and sync capacity_id from workload-dev-mode.json
    synced_capacity = sync_capacity_from_workload(str(repo_root), silent=False)
    if synced_capacity and synced_capacity.lower() != capacity_id.lower():
        capacity_id = synced_capacity
        print(f"   Using synced capacity_id: {capacity_id}")
    
    print("=" * 70)
    print("EDOG DevMode Token Manager")
    print("=" * 70)
    print(f"Username:  {username}")
    print(f"Workspace: {workspace_id}")
    print(f"Artifact:  {artifact_id}")
    print(f"Capacity:  {capacity_id}")
    print(f"Auto-launch: {'Yes' if launch_service else 'No'}")
    print("=" * 70)
    
    # Check for cached token first
    cached_token, cached_expiry = load_cached_token()
    if cached_token:
        print(f"\n✅ Using cached token (expires: {cached_expiry.strftime('%H:%M:%S')})")
        mwc_token = cached_token
        token_expiry = cached_expiry
    else:
        # Initial token fetch
        mwc_token = fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id)
        if not mwc_token:
            print("\n❌ Failed to fetch initial token after all retries")
            return 1
        
        token_expiry = parse_jwt_expiry(mwc_token)
        print(f"\n✅ Token acquired (expires: {token_expiry.strftime('%H:%M:%S') if token_expiry else 'unknown'})")
        
        # Cache the token
        if token_expiry:
            cache_token(mwc_token, token_expiry.timestamp())
    
    # Apply changes
    if not apply_all_changes(mwc_token, repo_root):
        print("\n⚠️  Some changes could not be applied")
    
    print("\n✅ Code changes applied successfully")
    
    # Start FLT service if requested
    service_process = None
    stop_event = None
    output_thread = None
    
    if launch_service:
        print("\n" + "=" * 70)
        print("🚀 Starting FLT Service...")
        print("=" * 70)
        service_process = start_flt_service(repo_root)
        if service_process:
            # Start background thread to stream service output
            stop_event = threading.Event()
            output_thread = threading.Thread(
                target=stream_service_output,
                args=(service_process, stop_event),
                daemon=True
            )
            output_thread.start()
        else:
            print("\n⚠️  Service failed to start, continuing with token management only")
    
    # Monitor loop
    print("\n" + "=" * 70)
    print("🔄 Monitoring token expiry (Ctrl+C to stop)")
    print(f"   Check interval: {CHECK_INTERVAL_MINS} mins")
    print(f"   Refresh threshold: {REFRESH_THRESHOLD_MINS} mins remaining")
    if service_process:
        print(f"   FLT Service: Running (PID: {service_process.pid})")
    print("=" * 70)
    
    try:
        while True:
            # Check if service crashed
            if service_process and service_process.poll() is not None:
                exit_code = service_process.returncode
                print(f"\n⚠️  FLT Service exited (code: {exit_code})")
                show_notification("EDOG DevMode", f"⚠️ FLT Service exited (code: {exit_code})")
                service_process = None
            
            # Calculate time remaining
            remaining = get_token_time_remaining(token_expiry)
            remaining_str = format_timedelta(remaining)
            
            status = f"Token: {remaining_str}"
            if service_process:
                status += " | Service: Running"
            print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] {status}")
            
            # Check if refresh needed
            if remaining and remaining <= timedelta(minutes=REFRESH_THRESHOLD_MINS):
                print(f"\n🔄 Token expiring soon, refreshing...")
                show_notification("EDOG DevMode", "Token expiring, refreshing...")
                
                new_token = fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id)
                
                if new_token:
                    mwc_token = new_token
                    token_expiry = parse_jwt_expiry(mwc_token)
                    print(f"✅ Token refreshed (expires: {token_expiry.strftime('%H:%M:%S') if token_expiry else 'unknown'})")
                    
                    # Cache the new token
                    if token_expiry:
                        cache_token(mwc_token, token_expiry.timestamp())
                    
                    # Update tokens in codebase
                    apply_all_changes(mwc_token, repo_root)
                    show_notification("EDOG DevMode", f"Token refreshed! Expires {token_expiry.strftime('%H:%M')}")
                else:
                    print("❌ Failed to refresh token - continuing with old token")
                    show_notification("EDOG DevMode", "⚠️ Token refresh failed!")
            
            # Wait for next check
            print(f"   Next check in {CHECK_INTERVAL_MINS} mins...")
            time.sleep(CHECK_INTERVAL_MINS * 60)
            
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        
        # Step 1: Stop service first (sequential cleanup)
        if service_process:
            if stop_event:
                stop_event.set()  # Signal output thread to stop
            stop_flt_service(service_process)
        
        # Step 2: Revert code changes
        print("🔄 Reverting EDOG changes...")
        revert_all_changes(repo_root)
        
        print("✅ Done. Goodbye!")
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
  edog --config                     Show current config
  edog --config -u <email>          Update username/email
  edog --config -w <id> -a <id>     Update workspace and artifact IDs
  edog --config -r C:\\path\\to\\FLT  Set FLT repo path (enables running from anywhere)
  edog --install-hook               Install git pre-commit hook (blocks commits with EDOG changes)
  edog --uninstall-hook             Remove git pre-commit hook
        """
    )
    
    parser.add_argument("--revert", action="store_true", help="Revert all EDOG changes")
    parser.add_argument("--status", action="store_true", help="Check if EDOG changes are applied")
    parser.add_argument("--config", action="store_true", help="Show or update config")
    parser.add_argument("--clear-token", action="store_true", help="Clear cached authentication token")
    parser.add_argument("--install-hook", action="store_true", help="Install git pre-commit hook")
    parser.add_argument("--uninstall-hook", action="store_true", help="Remove git pre-commit hook")
    parser.add_argument("--no-launch", action="store_true", help="Don't auto-launch FLT service (token management only)")
    parser.add_argument("-u", "--username", help="Username/Email for login")
    parser.add_argument("-w", "--workspace", help="Workspace ID")
    parser.add_argument("-a", "--artifact", help="Artifact ID")
    parser.add_argument("-c", "--capacity", help="Capacity ID")
    parser.add_argument("-r", "--repo", help="FabricLiveTable repo path")
    
    args = parser.parse_args()
    
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
        print("✅ Token cache cleared")
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
                print("\n❌ Cannot proceed without config")
                sys.exit(1)
            username = config.get("username") or DEFAULT_USERNAME
            workspace_id = config["workspace_id"]
            artifact_id = config["artifact_id"]
            capacity_id = config["capacity_id"]
        
        sys.exit(run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root, launch_service=not args.no_launch))
