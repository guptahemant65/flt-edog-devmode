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
CERT_SUBJECT = "Admin1CBA.FabricFMLV07PPE.ccsctp.net"

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


def prompt_for_config():
    """Prompt user to enter config values."""
    print("\n📝 First-time setup - please enter your EDOG environment details:")
    print("   (You can find these in Fabric portal URL or workload-dev-mode.json)\n")
    
    username = input(f"   Username/Email [{DEFAULT_USERNAME}]: ").strip()
    if not username:
        username = DEFAULT_USERNAME
    
    workspace_id = input("   Workspace ID: ").strip()
    artifact_id = input("   Artifact ID (Lakehouse): ").strip()
    capacity_id = input("   Capacity ID: ").strip()
    
    if not workspace_id or not artifact_id or not capacity_id:
        print("\n❌ All three IDs are required")
        return None
    
    # Validate GUID format
    guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    for name, value in [("Workspace", workspace_id), ("Artifact", artifact_id), ("Capacity", capacity_id)]:
        if not re.match(guid_pattern, value):
            print(f"\n❌ Invalid {name} ID format (expected GUID)")
            return None
    
    return {
        "username": username,
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "capacity_id": capacity_id
    }


def update_config(username=None, workspace_id=None, artifact_id=None, capacity_id=None):
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
    
    if save_config(config):
        print("\n✅ Config updated:")
        print(f"   Username:  {config.get('username', DEFAULT_USERNAME)}")
        print(f"   Workspace: {config.get('workspace_id', 'not set')}")
        print(f"   Artifact:  {config.get('artifact_id', 'not set')}")
        print(f"   Capacity:  {config.get('capacity_id', 'not set')}")
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
        print(f"\n   Config file: {get_config_path()}")
    else:
        print("   No config found. Run 'edog.cmd' to set up.")

# ============================================================================
# Patterns for applying/reverting changes
# ============================================================================
PATTERNS = {
    # (original, modified, description)
    "auth_engine_ltc": (
        "    [AuthenticationEngine]",
        "    // [AuthenticationEngine]  // EDOG DevMode - commented by edog tool",
        "AuthenticationEngine on LiveTableController"
    ),
    "auth_engine_ltsrc": (
        "    [AuthenticationEngine]",
        "    // [AuthenticationEngine]  // EDOG DevMode - commented by edog tool",
        "AuthenticationEngine on LiveTableSchedulerRunController"
    ),
    "permission_filter_getlatestdag": (
        "        [RequiresPermissionFilter(Permissions.ReadAll)]",
        "        // [RequiresPermissionFilter(Permissions.ReadAll)]  // EDOG DevMode - commented by edog tool",
        "RequiresPermissionFilter on getLatestDag"
    ),
    "permission_filter_rundag": (
        "        [MwcV2RequirePermissionsFilter([Permissions.ReadAll, Permissions.Execute])]",
        "        // [MwcV2RequirePermissionsFilter([Permissions.ReadAll, Permissions.Execute])]  // EDOG DevMode - commented by edog tool",
        "MwcV2RequirePermissionsFilter on runDAG"
    ),
}


def handle_certificate_dialog():
    """Background thread to handle the Windows certificate selection dialog."""
    print("   🔍 Watching for certificate dialog...")
    
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
                        if CERT_SUBJECT.lower() in item_text.lower() or "Admin1CBA" in item_text:
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
def get_repo_root():
    """Get repository root directory."""
    return Path(__file__).parent


def read_file(filepath):
    """Read file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except PermissionError:
        print(f"❌ File is locked (close it in VS): {filepath}")
        return None
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None


def write_file(filepath, content):
    """Write file content. Fails immediately if file is locked."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except PermissionError:
        print(f"❌ File is locked (close it in VS): {filepath}")
        return False
    except Exception as e:
        print(f"❌ Error writing {filepath}: {e}")
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
    
    # Original method (simplified - will need the actual original)
    original_method = '''        protected async virtual Task<Token> GenerateMWCV1TokenForGTSWorkloadAsync(CancellationToken ct)
        {
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
    
    # Find the attribute and comment before the method
    search_start = max(0, sig_start - 200)
    attr_marker = '// Extracted so as to mock in Test'
    attr_pos = content.rfind(attr_marker, search_start, sig_start)
    if attr_pos != -1:
        line_start = content.rfind('\n', 0, attr_pos) + 1
        method_start = line_start
    else:
        method_start = sig_start
    
    # Build full original method with comment and attribute
    full_original = '''        // Extracted so as to mock in Test
        [ExcludeFromCodeCoverage]
''' + original_method
    
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


async def get_bearer_token(username=None):
    """Launch Edge, capture Bearer token."""
    
    if not username:
        username = DEFAULT_USERNAME
    
    print("🚀 Starting browser...")
    bearer_token = None
    
    cert_policies = [
        '{"pattern":"*","filter":{"SUBJECT":{"CN":"Admin1CBA.FabricFMLV07PPE.ccsctp.net"}}}',
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                f'--auto-select-certificate-for-urls={cert_policies[0]}',
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
    """Apply all EDOG changes to codebase."""
    print("\n📝 Applying EDOG changes...")
    
    changes_made = []
    errors = []
    
    # 1. LiveTableController - AuthenticationEngine
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
        orig, mod, desc = PATTERNS["auth_engine_ltc"]
        new_content, changed, already = apply_simple_pattern(content, orig, mod, desc)
        if changed:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
                content = new_content
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif already:
            changes_made.append(f"⏭️  {desc} (already applied)")
        
        # RequiresPermissionFilter on getLatestDag
        orig, mod, desc = PATTERNS["permission_filter_getlatestdag"]
        new_content, changed, already = apply_simple_pattern(content, orig, mod, desc)
        if changed:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif already:
            changes_made.append(f"⏭️  {desc} (already applied)")
    else:
        errors.append(f"❌ Could not read LiveTableController.cs")
    
    # 2. LiveTableSchedulerRunController - AuthenticationEngine + MwcV2RequirePermissionsFilter
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
        orig, mod, desc = PATTERNS["auth_engine_ltsrc"]
        new_content, changed, already = apply_simple_pattern(content, orig, mod, desc)
        if changed:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
                content = new_content
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif already:
            changes_made.append(f"⏭️  {desc} (already applied)")
        
        orig, mod, desc = PATTERNS["permission_filter_rundag"]
        new_content, changed, already = apply_simple_pattern(content, orig, mod, desc)
        if changed:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif already:
            changes_made.append(f"⏭️  {desc} (already applied)")
    else:
        errors.append(f"❌ Could not read LiveTableSchedulerRunController.cs")
    
    # 3. GTSOperationManager - Token
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        new_content, status = apply_gts_operation_manager_change(content, token)
        desc = "GTSOperationManager token"
        if status == "applied":
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif status == "token_updated":
            if write_file(filepath, new_content):
                changes_made.append(f"🔄 {desc} (token updated)")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif status == "already_applied":
            changes_made.append(f"⏭️  {desc} (already applied)")
        else:
            errors.append(f"⚠️  {desc} (pattern not found)")
    else:
        errors.append(f"❌ Could not read GTSOperationManager.cs")
    
    # 4. GTSBasedSparkClient - Token bypass
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        new_content, status = apply_gts_spark_client_change(content, token)
        desc = "GTSBasedSparkClient token bypass"
        if status == "applied":
            if write_file(filepath, new_content):
                changes_made.append(f"✅ {desc}")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif status == "token_updated":
            if write_file(filepath, new_content):
                changes_made.append(f"🔄 {desc} (token updated)")
            else:
                errors.append(f"❌ Failed to write: {desc}")
        elif status == "already_applied":
            changes_made.append(f"⏭️  {desc} (already applied)")
        else:
            errors.append(f"⚠️  {desc} (pattern not found)")
    else:
        errors.append(f"❌ Could not read GTSBasedSparkClient.cs")
    
    # Print summary
    for msg in changes_made:
        print(f"   {msg}")
    for msg in errors:
        print(f"   {msg}")
    
    return len(errors) == 0


def revert_all_changes(repo_root):
    """Revert all EDOG changes."""
    print("\n🔄 Reverting EDOG changes...")
    
    changes_made = []
    errors = []
    
    # 1. LiveTableController
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
        modified = False
        for key in ["auth_engine_ltc", "permission_filter_getlatestdag"]:
            orig, mod, desc = PATTERNS[key]
            new_content, reverted = revert_simple_pattern(content, orig, mod, desc)
            if reverted:
                content = new_content
                modified = True
                changes_made.append(f"✅ Reverted: {desc}")
        
        if modified:
            if not write_file(filepath, content):
                errors.append(f"❌ Failed to write LiveTableController.cs")
    
    # 2. LiveTableSchedulerRunController
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
        modified = False
        for key in ["auth_engine_ltsrc", "permission_filter_rundag"]:
            orig, mod, desc = PATTERNS[key]
            new_content, reverted = revert_simple_pattern(content, orig, mod, desc)
            if reverted:
                content = new_content
                modified = True
                changes_made.append(f"✅ Reverted: {desc}")
        
        if modified:
            if not write_file(filepath, content):
                errors.append(f"❌ Failed to write LiveTableSchedulerRunController.cs")
    
    # 3. GTSOperationManager
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        new_content, reverted = revert_gts_operation_manager_change(content)
        if reverted:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ Reverted: GTSOperationManager token")
            else:
                errors.append(f"❌ Failed to write GTSOperationManager.cs")
    
    # 4. GTSBasedSparkClient
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        new_content, reverted = revert_gts_spark_client_change(content)
        if reverted:
            if write_file(filepath, new_content):
                changes_made.append(f"✅ Reverted: GTSBasedSparkClient token bypass")
            else:
                errors.append(f"❌ Failed to write GTSBasedSparkClient.cs")
    
    if not changes_made and not errors:
        print("   ℹ️  No EDOG changes found to revert")
    else:
        for msg in changes_made:
            print(f"   {msg}")
        for msg in errors:
            print(f"   {msg}")
    
    return len(errors) == 0


def check_status(repo_root):
    """Check if EDOG changes are applied."""
    print("\n🔍 Checking EDOG status...")
    
    status = []
    
    # Check each file
    filepath = repo_root / FILES["LiveTableController"]
    content = read_file(filepath)
    if content:
        _, mod, desc = PATTERNS["auth_engine_ltc"]
        status.append((desc, mod in content))
        _, mod, desc = PATTERNS["permission_filter_getlatestdag"]
        status.append((desc, mod in content))
    
    filepath = repo_root / FILES["LiveTableSchedulerRunController"]
    content = read_file(filepath)
    if content:
        _, mod, desc = PATTERNS["auth_engine_ltsrc"]
        status.append((desc, mod in content))
        _, mod, desc = PATTERNS["permission_filter_rundag"]
        status.append((desc, mod in content))
    
    filepath = repo_root / FILES["GTSOperationManager"]
    content = read_file(filepath)
    if content:
        # Check for EDOG marker OR manual hardcoded token
        has_edog_marker = "// EDOG DevMode - hardcoded by edog tool" in content
        has_manual_hardcode = re.search(r'var mwcV1TokenWithHeader = "MwcToken [^"]+";', content) is not None
        applied = has_edog_marker or has_manual_hardcode
        status.append(("GTSOperationManager token", applied))
    
    filepath = repo_root / FILES["GTSBasedSparkClient"]
    content = read_file(filepath)
    if content:
        applied = "// EDOG DevMode - bypassing OBO token exchange" in content
        status.append(("GTSBasedSparkClient token bypass", applied))
    
    all_applied = all(s[1] for s in status)
    any_applied = any(s[1] for s in status)
    
    for desc, applied in status:
        icon = "✅" if applied else "❌"
        print(f"   {icon} {desc}")
    
    print()
    if all_applied:
        print("   ✅ All EDOG changes are applied")
    elif any_applied:
        print("   ⚠️  Some EDOG changes are applied (partial state)")
    else:
        print("   ❌ No EDOG changes are applied")
    
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
    
    # Initial token fetch
    mwc_token = fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id)
    if not mwc_token:
        print("\n❌ Failed to fetch initial token after all retries")
        return 1
    
    token_expiry = parse_jwt_expiry(mwc_token)
    print(f"\n✅ Token acquired (expires: {token_expiry.strftime('%H:%M:%S') if token_expiry else 'unknown'})")
    
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
                new_token = fetch_token_with_retry(username, workspace_id, artifact_id, capacity_id)
                
                if new_token:
                    mwc_token = new_token
                    token_expiry = parse_jwt_expiry(mwc_token)
                    print(f"✅ Token refreshed (expires: {token_expiry.strftime('%H:%M:%S') if token_expiry else 'unknown'})")
                    
                    # Update tokens in codebase
                    apply_all_changes(mwc_token, repo_root)
                else:
                    print("❌ Failed to refresh token - continuing with old token")
            
            # Wait for next check
            print(f"   Next check in {CHECK_INTERVAL_MINS} mins...")
            time.sleep(CHECK_INTERVAL_MINS * 60)
            
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        print("   Run 'edog.cmd --revert' to revert changes when done testing")
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
  edog.cmd                              Start daemon (fetches token, applies changes, auto-refresh)
  edog.cmd --revert                     Revert all EDOG changes  
  edog.cmd --status                     Check if changes are applied
  edog.cmd --config                     Show current config
  edog.cmd --config -u <email>          Update username/email
  edog.cmd --config -w <id> -a <id>     Update workspace and artifact IDs
        """
    )
    
    parser.add_argument("--revert", action="store_true", help="Revert all EDOG changes")
    parser.add_argument("--status", action="store_true", help="Check if EDOG changes are applied")
    parser.add_argument("--config", action="store_true", help="Show or update config")
    parser.add_argument("-u", "--username", help="Username/Email for login")
    parser.add_argument("-w", "--workspace", help="Workspace ID")
    parser.add_argument("-a", "--artifact", help="Artifact ID")
    parser.add_argument("-c", "--capacity", help="Capacity ID")
    
    args = parser.parse_args()
    
    repo_root = get_repo_root()
    
    if args.revert:
        revert_all_changes(repo_root)
        sys.exit(0)
    elif args.status:
        check_status(repo_root)
        sys.exit(0)
    elif args.config:
        # If any values provided, update them
        if args.username or args.workspace or args.artifact or args.capacity:
            update_config(args.username, args.workspace, args.artifact, args.capacity)
        else:
            show_config()
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
