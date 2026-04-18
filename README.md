<div align="center">

# 🐕 EDOG DevMode

**One command. Zero popups. FabricLiveTable DevMode on autopilot.**

[![v3.2.0](https://img.shields.io/badge/version-3.2.0-blue?style=for-the-badge)](https://github.com/guptahemant65/flt-edog-devmode)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![.NET](https://img.shields.io/badge/.NET-8.0-512BD4?style=for-the-badge&logo=dotnet&logoColor=white)](https://dotnet.microsoft.com/)
[![Microsoft](https://img.shields.io/badge/Microsoft-Internal-E74C3C?style=for-the-badge&logo=microsoft&logoColor=white)](https://microsoft.com)

<br/>

[Quick Start](#-quick-start) · [What's New in v3.0](#-whats-new-in-v30) · [Commands](#-command-reference) · [Debug Mode](#-debug-mode) · [Instance Protection](#-instance-protection) · [Configuration](#-configuration) · [Architecture](#-how-it-works) · [Troubleshooting](#-troubleshooting)

<br/>

<img src="https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/Dog/3D/dog_3d.png" width="120" alt="EDOG"/>

<br/>

*Silent CBA auth • Auto-patching • Crash recovery • Health diagnostics • API REPL • Auto-update*
<br/>
*Type `edog`. Go build things. The dog handles the rest.*

</div>

<br/>

## What Is This?

EDOG DevMode is the **EDOG whisperer** — it takes the painful multi-step FabricLiveTable development setup and collapses it into a single command. No browser popups, no manual token juggling, no remembering which files to patch. Just `edog`.

<br/>

<table>
<tr>
<td width="20%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Locked%20with%20Key.png" width="60"/>
<br/><br/>
<b>Silent CBA Auth</b>
<br/>
Certificate-based, zero popups
<br/><br/>
</td>
<td width="20%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Travel%20and%20places/High%20Voltage.png" width="60"/>
<br/><br/>
<b>Dual Token Engine</b>
<br/>
Bearer + DevMode, auto-refresh
<br/><br/>
</td>
<td width="20%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Gear.png" width="60"/>
<br/><br/>
<b>Smart Patching</b>
<br/>
Apply on start, revert on exit
<br/><br/>
</td>
<td width="20%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Stethoscope.png" width="60"/>
<br/><br/>
<b>Health Diagnostics</b>
<br/>
14-point doctor check
<br/><br/>
</td>
<td width="20%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Magnifying%20Glass%20Tilted%20Left.png" width="60"/>
<br/><br/>
<b>API REPL</b>
<br/>
Interactive authenticated shell
<br/><br/>
</td>
</tr>
</table>

<br/>

---

<br/>

## 🆕 What's New in v3.0

<table>
<tr>
<td>🔄</td>
<td><b>Crash Recovery</b></td>
<td>Detects stale patches from crashed sessions and offers to clean them up automatically — no more manual <code>--revert</code> after a bad exit</td>
</tr>
<tr>
<td>🩺</td>
<td><b><code>edog --doctor</code></b></td>
<td>One-shot health check — validates all 14 dependencies (Python, .NET, certs, config, repos, token-helper) with a clear pass/fail report</td>
</tr>
<tr>
<td>⬆️</td>
<td><b>Auto-Update</b></td>
<td>Checks for updates on every startup via <code>git pull --ff-only</code>. Skip with <code>--no-update</code>. Never touches local changes.</td>
</tr>
<tr>
<td>📊</td>
<td><b>Session Summary</b></td>
<td>On Ctrl+C, prints session duration, token refresh count, failure count, and restart count — a quick glance at how the session went</td>
</tr>
<tr>
<td>🏷️</td>
<td><b>Terminal Title</b></td>
<td>Sets your terminal window title to <code>🐕 EDOG DevMode — {workspace}</code> while running, restores on exit</td>
</tr>
<tr>
<td>🎨</td>
<td><b>Colored Log Output</b></td>
<td>Pre-connection service logs are color-coded (errors in red, warnings in yellow, info in cyan) for faster visual scanning</td>
</tr>
<tr>
<td>🪝</td>
<td><b>Hook Auto-Install</b></td>
<td>Git pre-commit hook auto-installs when patches are applied — blocks accidental commits of EDOG markers</td>
</tr>
<tr>
<td>📋</td>
<td><b><code>edog --bearer</code></b></td>
<td>Copies bearer token to clipboard with ready-to-paste <code>curl</code> and <code>Invoke-RestMethod</code> examples for Postman/API testing</td>
</tr>
<tr>
<td>🔌</td>
<td><b><code>edog --api</code></b></td>
<td>Interactive REPL — type API paths, get authenticated JSON responses. Supports GET/POST, pretty-printing, and history</td>
</tr>
<tr>
<td>👀</td>
<td><b>Git Auto-Reapply</b></td>
<td>Background watcher detects when you <code>git pull</code> or switch branches — automatically re-patches so you never lose DevMode state mid-session</td>
</tr>
</table>

<br/>

---

<br/>

## 🚀 Quick Start

```powershell
# Clone and go — that's literally it
git clone https://github.com/guptahemant65/flt-edog-devmode.git
cd flt-edog-devmode

edog
# First run auto-detects missing setup and runs it for you
# Then prompts for your Workspace ID, Artifact ID, and Capacity ID
```

No separate setup step. No second script. EDOG detects what's needed and handles it.

<br/>

---

<br/>

## ⚙️ How It Works

```
                              EDOG DevMode — The Full Pipeline
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │                                                                              │
    │   ┌─────────────┐     ┌─────────────────┐     ┌───────────────────────┐     │
    │   │  Silent CBA  │────▶│  Bearer Token    │────▶│  DevMode Token        │     │
    │   │  (cert-based)│     │  (PowerBI API)   │     │  (EDOG audience)      │     │
    │   └─────────────┘     └─────────────────┘     └───────────┬───────────┘     │
    │                                                            │                 │
    │                                                            ▼                 │
    │   ┌─────────────┐     ┌─────────────────┐     ┌───────────────────────┐     │
    │   │  FLT Service │◀────│  Build & Launch  │◀────│  Auto-Patch Codebase  │     │
    │   │  (dotnet run)│     │  (dotnet build)  │     │  (6 surgical edits)   │     │
    │   └──────┬──────┘     └─────────────────┘     └───────────────────────┘     │
    │          │                                                                   │
    │          ▼                                                                   │
    │   ┌──────────────────────────────────────────────────────────────────┐       │
    │   │  🔄 Token auto-refresh (bearer + DevMode, independent timers)   │       │
    │   │  👀 Git watcher (re-patches after pull/branch switch)           │       │
    │   │  🛡️ Pre-commit hook (blocks EDOG marker commits)                │       │
    │   │  🏷️ Terminal title (workspace context at a glance)              │       │
    │   └──────────────────────────────────────────────────────────────────┘       │
    │                                                                              │
    │   On Ctrl+C:  Stop → Revert Patches → Remove Hook → Session Summary         │
    └──────────────────────────────────────────────────────────────────────────────┘
```

### What Gets Patched (and Un-Patched)

Every `edog` run applies **6 surgical code changes** to your FLT service, then **reverts them all cleanly on exit**:

| Patch | What It Does |
|-------|-------------|
| **GTSBasedSparkClient** | Replaces MWC token generation with file-based bearer bypass |
| **Web Log Viewer** | Injects `EdogLogServer.cs` and friends for real-time browser logs |
| **Program.cs** | Registers the log viewer HTTP server |
| **WorkloadApp.cs** | Wires up telemetry interception |
| **ParametersManifest.json** | Adds `DisableFLTAuth` parameter |
| **Test.json** | Sets `DisableFLTAuth = true` |

All changes are tracked in `.edog-changes.patch` and reverted via direct function calls (not `git checkout`).

If EDOG crashes or your machine reboots mid-session, **crash recovery** detects leftover patches on the next run and offers to clean them up automatically.

<br/>

---

<br/>

## 📖 Command Reference

### Core

| Command | Description |
|---------|-------------|
| `edog` | **The big one.** Auth → patch → build → launch → monitor → revert on exit |
| `edog --debug` | **Debug mode.** Everything above + Debugger.Launch() → VS attaches from line 1 |
| `edog --no-launch` | Auth + patch only (skip build/launch — useful for token-only workflows) |
| `edog --revert` | Revert all EDOG patches from the codebase |
| `edog --status` | Show current DevMode status and what's patched |
| `edog --setup` | Re-run first-time setup (Python, .NET SDK, token-helper build) |

### Diagnostics & Tools

| Command | Description |
|---------|-------------|
| `edog --doctor` | One-shot diagnostic — checks all 14 dependencies and config |
| `edog --bearer` | Show bearer token path, copy to clipboard, print curl/PowerShell examples |
| `edog --api` | Interactive authenticated REPL — GET/POST with bearer auth, JSON pretty-print |
| `edog --logs` | Open the web log viewer in your browser |

### Configuration

| Command | Description |
|---------|-------------|
| `edog --config` | Show current config, then offer interactive editing |
| `edog --config -u <email>` | Set CBA username (e.g. `Admin1CBA@FabricFMLV08PPE.ccsctp.net`) |
| `edog --config -w <guid>` | Set workspace ID |
| `edog --config -a <guid>` | Set artifact ID |
| `edog --config -c <guid>` | Set capacity ID (auto-syncs with `workload-dev-mode.json`) |
| `edog --config -r <path>` | Set FLT repo path (usually auto-detected) |

> **Tip:** Run `edog --config` with no flags to see your current config and edit any field interactively.

### Maintenance

| Command | Description |
|---------|-------------|
| `edog --clear-token` | Clear cached auth tokens |
| `edog --no-update` | Skip auto-update check on startup |
| `edog --install-hook` | Install git pre-commit safety hook (auto-installed on patch apply) |
| `edog --uninstall-hook` | Remove git pre-commit hook |

<br/>

---

<br/>

## 🔧 Configuration

Config lives in `edog-config.json` (gitignored):

```json
{
  "username": "Admin1CBA@FabricFMLV08PPE.ccsctp.net",
  "workspace_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "artifact_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "capacity_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "flt_repo_path": "auto-detect"
}
```

### Interactive Editing

Run `edog --config` with no flags — it shows your current config, then asks if you want to edit. Say yes and it walks you through each field, showing the current value and letting you update or skip.

### Finding Your IDs

All three IDs are in your EDOG API URL:

```
https://{capacity_id}.pbidedicated.windows-int.net/.../capacities/{capacity_id}/.../workspaces/{workspace_id}/artifacts/.../{artifact_id}/...
```

### Cert Discovery

EDOG finds your CBA certificate automatically:
1. **Memory cache** → **Disk cache** → **token-helper `--list-certs`** → **Windows Certificate Store**
2. If not found anywhere → prompts you for a `.pfx` file and imports it (no password needed for CBA certs)

### Capacity Sync

`capacity_id` stays in sync with `workload-dev-mode.json` automatically. EDOG detects drift on every startup.

<br/>

---

<br/>

## 🔍 Repo Auto-Detection

EDOG finds your `workload-fabriclivetable` repo automatically:

```
1. Configured path  →  2. Current directory  →  3. Parent dirs  →  4. Home (~8 levels deep)
```

Override: `edog --config -r C:\path\to\workload-fabriclivetable`

<br/>

---

<br/>

## 🔒 Security

| Aspect | Implementation |
|--------|---------------|
| **Auth** | Silent CBA (certificate-based) — no browser, no popups |
| **Tokens** | Dual-token architecture: bearer (PowerBI API) + DevMode (EDOG audience) |
| **Refresh** | Auto-refresh before expiry with cached fallback |
| **Change Tracking** | All patches recorded in `.edog-changes.patch` |
| **Rollback** | Clean revert on Ctrl+C — always leaves your repo pristine |
| **Crash Safety** | Stale patches from crashed sessions detected and cleaned on next run |
| **Pre-commit Hook** | Auto-installed hook blocks accidental commits of EDOG markers |
| **Secrets** | Tokens and config are gitignored; certs stay in Windows cert store |

<br/>

---

<br/>

## 📊 Log Viewer

EDOG injects a web-based log viewer into the FLT service. Once the service starts:

- Open `http://localhost:<port>/edog-logs` in your browser
- Real-time log streaming with color-coded levels
- Telemetry event visualization (SSR events, durations, success rates)
- Filter by level, component, activity
- Search across all logs

No separate tool needed — it's baked into the service while EDOG is running.

Pre-connection service logs also stream to your terminal with **colored output** — errors in red, warnings in yellow, info in cyan — for quick visual scanning while the service boots.

<br/>

---

<br/>

## 📁 Project Structure

```
flt-edog-devmode/
├── edog.py                     The whole show — CLI, auth, patching, monitoring
├── edog.cmd                    Windows batch launcher
├── install.ps1                 One-liner remote installer
├── Setup-DevmodeResources.ps1  Pre-devmode workspace/lakehouse creator
├── build-html.py               Builds modular log viewer into single HTML
├── scripts/
│   └── token-helper/           C# Silent CBA token acquisition helper
│       ├── Program.cs
│       └── token-helper.csproj
└── src/
    ├── Edog*.cs                C# files injected into FLT service
    ├── .editorconfig           StyleCop config for injected files
    └── edog-logs/              Modular log viewer UI (HTML/CSS/JS)
```

<br/>

---

<br/>

## ❓ Troubleshooting

| Problem | Fix |
|---------|-----|
| Certificate not found | EDOG will prompt for `.pfx` path and import it automatically |
| Token expired/invalid | `edog --clear-token` then `edog` |
| Build fails after patching | `edog --revert` to clean up, then check for upstream changes |
| Repo not found | `edog --config -r <path>` to set manually |
| First run fails | `edog --setup` to re-run setup |
| Ctrl+C leaves patches | `edog --revert` (shouldn't happen — crash recovery catches this next run) |
| Not sure what's wrong | `edog --doctor` — 14-point health check with clear pass/fail |
| Need bearer for Postman | `edog --bearer` — copies token to clipboard with usage examples |
| Want to test APIs quickly | `edog --api` — interactive REPL with authenticated requests |
| Patches vanish after git pull | They don't — git watcher auto-re-patches for you 🐕 |
| Debug mode: no JIT dialog | Check VS installation — `edog --doctor` validates this |
| Debug mode: breakpoints not hit | Ensure you're using `--debug` flag — builds with Debug config for PDB symbols |

<br/>

---

<br/>

## 🔍 Debug Mode

Attach Visual Studio's debugger to the FLT service from the very first line:

```powershell
edog --debug
```

**What happens:**
1. EDOG runs all normal steps (auth, patch, build)
2. Injects `Debugger.Launch()` at the top of `Main()` in Program.cs
3. Builds with `--configuration Debug` (PDB symbols for breakpoints)
4. Launches the service → .NET JIT debugger dialog appears
5. Pick your Visual Studio instance → debugger attaches from startup
6. Set breakpoints anywhere — they work from line 1

**Debug mode differences:**
- ⏳ No connection timeout (service pauses at `Debugger.Launch()`)
- 🚫 Git auto-reapply disabled (avoids breakpoint drift and VS "file changed" warnings)
- 🏷️ Terminal title shows `[DEBUG]`
- 🔁 Service restart re-triggers `Debugger.Launch()` automatically
- 🧹 All patches (including debugger) reverted cleanly on exit

<br/>

---

<br/>

## 🔒 Instance Protection

EDOG prevents multiple instances from running simultaneously — no more accidental double-launches or conflicting reverts.

**What's protected:**
| Scenario | Behavior |
|----------|----------|
| `edog` when daemon already running | ❌ Blocked — shows running PID |
| `edog --revert` when daemon running | ❌ Blocked — "stop daemon first" |
| `edog --debug` when daemon running | ❌ Blocked — same as above |
| `edog --doctor`, `--status`, `--bearer` | ✅ Allowed — read-only commands |

**How it works:**
- PID lock file (`.edog.lock`) created when daemon starts
- On startup, checks if lock PID is still alive (Windows kernel API)
- Stale locks from crashes are auto-cleaned
- Lock released on normal exit (Ctrl+C) and crash recovery

<br/>

---

<br/>

## 💼 Daily Workflow

```powershell
# Morning: one command
edog

# All day: code normally
#   - Logs at http://localhost:PORT/edog-logs
#   - git pull? Patches auto-reapply
#   - Need an API call? edog --api in another terminal
#   - Need the bearer token? edog --bearer

# Done for the day: Ctrl+C
#   → Service stops
#   → Patches revert
#   → Pre-commit hook removed
#   → Session summary printed
#   → Commit your actual work — repo is clean
```

<br/>

---

<div align="center">
<sub>v3.2.0 · Microsoft Internal · Built for FabricLiveTable developers who'd rather code than configure</sub>
</div>
