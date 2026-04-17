<div align="center">

# 🐕 EDOG DevMode

**One command. Zero popups. FabricLiveTable DevMode on autopilot.**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![.NET](https://img.shields.io/badge/.NET-8.0-512BD4?style=for-the-badge&logo=dotnet&logoColor=white)](https://dotnet.microsoft.com/)
[![Microsoft](https://img.shields.io/badge/Microsoft-Internal-E74C3C?style=for-the-badge&logo=microsoft&logoColor=white)](https://microsoft.com)

<br/>

[Quick Start](#-quick-start) · [Commands](#-command-reference) · [Configuration](#-configuration) · [Architecture](#-how-it-works) · [Troubleshooting](#-troubleshooting)

<br/>

<img src="https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/Dog/3D/dog_3d.png" width="120" alt="EDOG"/>

<br/>

*Silent CBA auth • Live token bypass • Auto-patching • Real-time log viewer*
<br/>
*Type `edog`. Go build things. The dog handles the rest.*

</div>

<br/>

## What Is This?

EDOG DevMode is the **EDOG whisperer** — it takes the painful multi-step FabricLiveTable development setup and collapses it into a single command. No browser popups, no manual token juggling, no remembering which files to patch. Just `edog`.

<br/>

<table>
<tr>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Locked%20with%20Key.png" width="60"/>
<br/><br/>
<b>Silent CBA Auth</b>
<br/>
Certificate-based, zero popups
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Travel%20and%20places/High%20Voltage.png" width="60"/>
<br/><br/>
<b>Dual Token Engine</b>
<br/>
Bearer + DevMode, auto-refresh
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Gear.png" width="60"/>
<br/><br/>
<b>Smart Patching</b>
<br/>
Apply on start, revert on exit
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Magnifying%20Glass%20Tilted%20Left.png" width="60"/>
<br/><br/>
<b>Web Log Viewer</b>
<br/>
Real-time logs in your browser
<br/><br/>
</td>
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
    │   │  🔄  Monitor Loop: token refresh + service health + log viewer  │       │
    │   └──────────────────────────────────────────────────────────────────┘       │
    │                                                                              │
    │   On Ctrl+C:  Stop Service → Revert All Patches → Clean Exit                │
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

<br/>

---

<br/>

## 📖 Command Reference

### Core

| Command | Description |
|---------|-------------|
| `edog` | **The big one.** Auth → patch → build → launch → monitor → revert on exit |
| `edog --no-launch` | Auth + patch only (skip build/launch — useful for token-only workflows) |
| `edog --revert` | Revert all EDOG patches from the codebase |
| `edog --status` | Show current DevMode status and what's patched |
| `edog --setup` | Re-run first-time setup (Python, .NET SDK, token-helper build) |

### Configuration

| Command | Description |
|---------|-------------|
| `edog --config` | Show current config with live cert + capacity sync status |
| `edog --config -u <email>` | Set CBA username (e.g. `Admin1CBA@FabricFMLV08PPE.ccsctp.net`) |
| `edog --config -w <guid>` | Set workspace ID |
| `edog --config -a <guid>` | Set artifact ID |
| `edog --config -c <guid>` | Set capacity ID (auto-syncs with `workload-dev-mode.json`) |
| `edog --config -r <path>` | Set FLT repo path (usually auto-detected) |

### Maintenance

| Command | Description |
|---------|-------------|
| `edog --clear-token` | Clear cached auth tokens |

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
| Ctrl+C leaves patches | `edog --revert` (shouldn't happen — but just in case) |

<br/>

---

<br/>

## 💼 Daily Workflow

```powershell
# Morning: one command
edog

# All day: code normally, logs at http://localhost:PORT/edog-logs

# Done for the day: Ctrl+C
# Service stops, patches revert, repo is clean
# Commit your actual work without any EDOG artifacts
```

<br/>

---

<div align="center">
<sub>Microsoft Internal · Built for FabricLiveTable developers who'd rather code than configure</sub>
</div>
