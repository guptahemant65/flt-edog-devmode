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
from datetime import datetime, timedelta
from pathlib import Path

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
    """Save config to file."""
    config_path = get_config_path()
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Could not save config: {e}")
        return False


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


def prompt_for_config():
    """Prompt user to enter config values."""
    print("\n📝 First-time setup - please enter your EDOG environment details:")
    print("   (You can find these in Fabric portal URL or workload-dev-mode.json)\n")
    
    username = input(f"   Username/Email [{DEFAULT_USERNAME}]: ").strip()
    if not username:
        username = DEFAULT_USERNAME
    
    workspace_id = prompt_guid("   Workspace ID: ", "Workspace ID")
    artifact_id = prompt_guid("   Artifact ID (Lakehouse): ", "Artifact ID")
    capacity_id = prompt_guid("   Capacity ID: ", "Capacity ID")
    
    return {
        "username": username,
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "capacity_id": capacity_id
    }


def update_config(username=None, workspace_id=None, artifact_id=None, capacity_id=None, flt_repo_path=None):
    """Update specific config values."""
    config = load_config()
    
    if username:
        config["username"] = username
    if workspace_id:
        config["workspace_id"] = workspace_id
    if artifact_id:
        config["artifact_id"] = artifact_id
    if capacity_id:
        config["capacity_id"] = capacity_id
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
    """Ensure config exists, prompt user if not."""
    config = load_config()
    
    if not config.get("workspace_id") or not config.get("artifact_id") or not config.get("capacity_id"):
        config = prompt_for_config()
        if not config:
            return None
        if not save_config(config):
            return None
        print("\n✅ Config saved to edog-config.json")
    
    return config


def show_config():
    """Display current config."""
    config = load_config()
    print("\n📋 Current EDOG config:")
    if config:
        print(f"   Username:  {config.get('username', DEFAULT_USERNAME + ' (default)')}")
        print(f"   Workspace: {config.get('workspace_id', 'not set')}")
        print(f"   Artifact:  {config.get('artifact_id', 'not set')}")
        print(f"   Capacity:  {config.get('capacity_id', 'not set')}")
        print(f"   FLT Repo:  {config.get('flt_repo_path', 'auto-detect (current directory)')}")
        print(f"\n   Config file: {get_config_path()}")
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
    """Search for FabricLiveTable repo by looking for its unique folder structure."""
    home = Path.home()
    
    # Signature: repo must contain Service/Microsoft.LiveTable.Service
    def is_flt_repo(path):
        try:
            return (path / "Service" / "Microsoft.LiveTable.Service").exists()
        except (PermissionError, OSError):
            return False
    
    # Search home directory with depth limit (avoids searching forever)
    max_depth = 4
    skip_dirs = {'.git', '.vs', '.vscode', 'node_modules', '__pycache__', 'bin', 'obj', 
                 'packages', 'AppData', '.nuget', '.dotnet', '.azure', 'OneDrive'}
    
    def search_dir(start_path, current_depth=0):
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
                found = search_dir(entry, current_depth + 1)
                if found:
                    return found
        except (PermissionError, OSError):
            pass
        return None
    
    return search_dir(home)


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


def apply_gts_operation_manager_change(content, token):
    """Apply GTSOperationManager token change. Returns (new_content, status)."""
    original, modified = get_gts_operation_manager_token_pattern(token)
    
    # Check if bypass is already there with same token
    if modified in content:
        return content, "already_applied"
    
    # Check if bypass is there with different token (with EDOG marker) - update it
    edog_marker = '// EDOG DevMode - hardcoded by edog tool'
    if edog_marker in content:
        # Find and replace the line
        pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";  // EDOG DevMode - hardcoded by edog tool'
        new_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  // EDOG DevMode - hardcoded by edog tool'
        new_content = re.sub(pattern, new_line, content)
        if new_content != content:
            return new_content, "token_updated"
    
    # Check if there's a hardcoded token WITHOUT the EDOG marker (manual edit) - update it
    manual_hardcode_pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";'
    if re.search(manual_hardcode_pattern, content) and edog_marker not in content:
        new_line = f'var mwcV1TokenWithHeader = "MwcToken {token}";  // EDOG DevMode - hardcoded by edog tool'
        new_content = re.sub(manual_hardcode_pattern, new_line, content)
        if new_content != content:
            return new_content, "token_updated"
    
    # Apply fresh bypass
    if original in content:
        return content.replace(original, modified, 1), "applied"
    
    return content, "pattern_not_found"


def apply_gts_spark_client_change(content, token):
    """Apply GTSBasedSparkClient bypass. Returns (new_content, status)."""
    edog_marker = '// EDOG DevMode - bypassing OBO token exchange'
    
    # Check if bypass exists
    if edog_marker in content:
        # Check if token is the same
        if f'var hardcodedToken = "{token}"' in content:
            return content, "already_applied"
        # Update token in existing bypass
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
    
    # Find the attribute and comment before the method (go back to find [ExcludeFromCodeCoverage])
    search_start = max(0, sig_start - 200)
    attr_marker = '// Extracted so as to mock in Test'
    attr_pos = content.rfind(attr_marker, search_start, sig_start)
    if attr_pos != -1:
        # Find start of the line with the comment
        line_start = content.rfind('\n', 0, attr_pos) + 1
        method_start = line_start
    else:
        # Just use signature start
        method_start = sig_start
    
    # Build the bypass code with proper indentation
    bypass_code = f'''        // Extracted so as to mock in Test
        [ExcludeFromCodeCoverage]
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


def revert_gts_operation_manager_change(content):
    """Revert GTSOperationManager token change."""
    edog_marker = '// EDOG DevMode - hardcoded by edog tool'
    if edog_marker not in content:
        return content, False
    
    original = 'var mwcV1TokenWithHeader = await HttpTokenUtils.GenerateMwcV1TokenHeaderAsync(mwcTokenHandler, workloadContext.ArtifactStoreServiceProvider.GetArtifactStoreServiceAsync(), userTJSToken, capacityContext, workspaceId, artifactId, Constants.LakehouseArtifactType, Constants.LakehouseTokenPermissions, default);'
    pattern = r'var mwcV1TokenWithHeader = "MwcToken [^"]+";  // EDOG DevMode - hardcoded by edog tool'
    
    new_content = re.sub(pattern, original, content)
    return new_content, new_content != content


def revert_gts_spark_client_change(content):
    """Revert GTSBasedSparkClient bypass - restore original method."""
    edog_marker = '// EDOG DevMode - bypassing OBO token exchange'
    if edog_marker not in content:
        return content, False
    
    # Original method body (without the leading comment/attribute - those are added below)
    original_method_body = '''        {
            var mwcToken = await tokenProvider.GetTokenAsync(ct);
            var tjsAppId = this.parametersProvider.GetHostParameter<string>("TJSFirstPartyApplicationId");

            AADTokenInfo userTJSToken = await HttpTokenUtils.GetOboTokenAsync(
                this.workloadAppAuthProvider, tjsAppId, this.tenantId, mwcToken);

            Tracer.LogSanitizedWarning($"[CDF-GTSClient-userTJSToken] AADTokenInfo.ExpiresOn value: {userTJSToken.ExpiresOn}");

            DateTimeOffset tokenExpiry;

            if (userTJSToken.ExpiresOn != DateTimeOffset.MinValue &&
                userTJSToken.ExpiresOn != default(DateTimeOffset))
            {
                tokenExpiry = userTJSToken.ExpiresOn;
                Tracer.LogSanitizedMessage($"[CDF-GTSClient] Using ExpiresOn from AADTokenInfo: {tokenExpiry:yyyy-MM-dd HH:mm:ss.fff} UTC");
            }
            else if (HttpTokenUtils.TryGetExpiryFromJwtToken(userTJSToken.AccessToken, out DateTime extractedExpiry))
            {
                tokenExpiry = new DateTimeOffset(extractedExpiry);
                Tracer.LogSanitizedWarning($"[CDF-GTSClient] ExpiresOn was MinValue/default. Extracted expiry from JWT 'exp' claim: {tokenExpiry:yyyy-MM-dd HH:mm:ss.fff} UTC");
            }
            else
            {
                tokenExpiry = DateTimeOffset.UtcNow.AddHours(1);
                Tracer.LogSanitizedWarning($"[CDF-GTSClient] ExpiresOn was MinValue AND JWT parsing failed. Using 1-hour fallback: {tokenExpiry:yyyy-MM-dd HH:mm:ss.fff} UTC");
            }

            var capacityContext = CustomerCapacityAsyncLocalContext.Value;

            var mwcV1Token = await HttpTokenUtils.GenerateMwcV1TokenAsync(
                this.mwcTokenHandler,
                this.workloadContext.ArtifactStoreServiceProvider.GetArtifactStoreServiceAsync(),
                userTJSToken.AccessToken,
                capacityContext,
                this.workspaceId,
                this.artifactId,
                Constants.LakehouseArtifactType,
                Constants.LakehouseTokenPermissions,
                tokenExpiry);

            return new Token
            {
                Value = mwcV1Token,
                Expiry = tokenExpiry,
            };
        }'''
    
    # Use same brace-counting logic as apply function
    method_sig = 'protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)'
    
    if method_sig not in content:
        return content, False
    
    # Find the method start
    sig_start = content.find(method_sig)
    if sig_start == -1:
        return content, False
    
    # Find the opening brace after signature
    brace_start = content.find('{', sig_start)
    if brace_start == -1:
        return content, False
    
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
        return content, False
    
    method_end = pos
    
    # Find the comment and attribute before the method
    # Look for "// Extracted so as to mock in Test" which should be 2 lines before the method signature
    search_start = max(0, sig_start - 200)
    comment_marker = '// Extracted so as to mock in Test'
    attr_marker = '[ExcludeFromCodeCoverage]'
    
    comment_pos = content.rfind(comment_marker, search_start, sig_start)
    
    if comment_pos != -1:
        # Found the comment - start replacement from the beginning of that line
        line_start = content.rfind('\n', 0, comment_pos) + 1
        method_start = line_start
    else:
        # Comment not found - check for attribute only
        attr_pos = content.rfind(attr_marker, search_start, sig_start)
        if attr_pos != -1:
            line_start = content.rfind('\n', 0, attr_pos) + 1
            method_start = line_start
        else:
            # Neither found - start from method signature, but we need to find the line start
            line_start = content.rfind('\n', 0, sig_start) + 1
            method_start = line_start
    
    # Build full original method with comment and attribute
    full_original = '''        // Extracted so as to mock in Test
        [ExcludeFromCodeCoverage]
        protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)
''' + original_method_body
    
    new_content = content[:method_start] + full_original + content[method_end:]
    return new_content, True


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
    """Apply all EDOG changes to codebase using smart pattern matching."""
    print("\n📝 Applying EDOG changes...")
    
    changes_made = []
    warnings = []
    
    # 1. LiveTableController patterns (smart matching)
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
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
        
        if modified:
            write_file(filepath, content)
    
    # 2. LiveTableSchedulerRunController patterns (smart matching)
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
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
        
        if modified:
            write_file(filepath, content)
    
    # 3. GTSOperationManager - Token
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        new_content, status = apply_gts_operation_manager_change(content, token)
        if status in ["applied", "token_updated"]:
            write_file(filepath, new_content)
            changes_made.append(f"✅ GTSOperationManager token")
        elif status == "already_applied":
            changes_made.append(f"⏭️  GTSOperationManager token (already)")
        elif status == "pattern_not_found":
            warnings.append(f"⚠️  GTSOperationManager token: pattern not found")
    
    # 4. GTSBasedSparkClient - Token bypass
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        new_content, status = apply_gts_spark_client_change(content, token)
        if status in ["applied", "token_updated"]:
            write_file(filepath, new_content)
            changes_made.append(f"✅ GTSBasedSparkClient token bypass")
        elif status == "already_applied":
            changes_made.append(f"⏭️  GTSBasedSparkClient token bypass (already)")
        elif status == "pattern_not_found":
            warnings.append(f"⚠️  GTSBasedSparkClient: pattern not found")
    
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
    """Revert all EDOG changes using smart pattern matching."""
    print("\n🔄 Reverting EDOG changes...")
    
    changes_made = []
    
    # 1. LiveTableController (smart matching)
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
        modified = False
        for key in ["auth_engine_ltc", "permission_filter_getlatestdag"]:
            pattern_config = SMART_PATTERNS[key]
            new_content, reverted = revert_smart_pattern(content, pattern_config)
            if reverted:
                content = new_content
                modified = True
                changes_made.append(f"✅ Reverted: {pattern_config['description']}")
        if modified:
            write_file(filepath, content)
    
    # 2. LiveTableSchedulerRunController (smart matching)
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
        modified = False
        for key in ["auth_engine_ltsrc", "permission_filter_rundag"]:
            pattern_config = SMART_PATTERNS[key]
            new_content, reverted = revert_smart_pattern(content, pattern_config)
            if reverted:
                content = new_content
                modified = True
                changes_made.append(f"✅ Reverted: {pattern_config['description']}")
        if modified:
            write_file(filepath, content)
    
    # 3. GTSOperationManager
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        new_content, reverted = revert_gts_operation_manager_change(content)
        if reverted:
            write_file(filepath, new_content)
            changes_made.append(f"✅ Reverted: GTSOperationManager token")
    
    # 4. GTSBasedSparkClient
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        new_content, reverted = revert_gts_spark_client_change(content)
        if reverted:
            write_file(filepath, new_content)
            changes_made.append(f"✅ Reverted: GTSBasedSparkClient token bypass")
    
    if not changes_made:
        print("   ℹ️  No EDOG changes found to revert")
    else:
        for msg in changes_made:
            print(f"   {msg}")
    
    return True


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


def run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root):
    """Main daemon loop - fetch token, apply changes, monitor and refresh."""
    
    print("=" * 70)
    print("EDOG DevMode Token Manager")
    print("=" * 70)
    print(f"Username:  {username}")
    print(f"Workspace: {workspace_id}")
    print(f"Artifact:  {artifact_id}")
    print(f"Capacity:  {capacity_id}")
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
    
    # Monitor loop
    print("\n" + "=" * 70)
    print("🔄 Monitoring token expiry (Ctrl+C to stop)")
    print(f"   Check interval: {CHECK_INTERVAL_MINS} mins")
    print(f"   Refresh threshold: {REFRESH_THRESHOLD_MINS} mins remaining")
    print("=" * 70)
    
    try:
        while True:
            # Calculate time remaining
            remaining = get_token_time_remaining(token_expiry)
            remaining_str = format_timedelta(remaining)
            
            print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Token expires in: {remaining_str}")
            
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
        clear_token_cache()  # Clear cache on exit
        warn_uncommitted_edog_changes(repo_root)
        print("   Run 'edog --revert' to revert changes before committing code")
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
  edog                              Start daemon (fetches token, applies changes, auto-refresh)
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
    parser.add_argument("--install-hook", action="store_true", help="Install git pre-commit hook")
    parser.add_argument("--uninstall-hook", action="store_true", help="Remove git pre-commit hook")
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
        
        sys.exit(run_daemon(username, workspace_id, artifact_id, capacity_id, repo_root))
