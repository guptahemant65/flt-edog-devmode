<div align="center">

# EDOG DevMode

**Automated MWC Token Management for FabricLiveTable Development**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Microsoft](https://img.shields.io/badge/Microsoft-Internal-E74C3C?style=for-the-badge&logo=microsoft&logoColor=white)](https://microsoft.com)

<br/>

[Quick Start](#-quick-start) · [Commands](#-command-reference) · [Configuration](#-configuration) · [Troubleshooting](#-troubleshooting)

<br/>

<img src="https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/Dog/3D/dog_3d.png" width="120" alt="EDOG"/>

</div>

<br/>

## Overview

EDOG DevMode streamlines the developer experience by automating authentication and token management for FabricLiveTable EDOG environments. It eliminates manual token handling, allowing developers to focus on building features.

<br/>

<table>
<tr>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Locked%20with%20Key.png" width="60"/>
<br/><br/>
<b>Automated Auth</b>
<br/>
Browser-based Microsoft OAuth
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Travel%20and%20places/High%20Voltage.png" width="60"/>
<br/><br/>
<b>Token Management</b>
<br/>
Auto-refresh every 45 min
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Gear.png" width="60"/>
<br/><br/>
<b>Code Injection</b>
<br/>
Seamless bypass config
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Magnifying%20Glass%20Tilted%20Left.png" width="60"/>
<br/><br/>
<b>Auto-Detection</b>
<br/>
Finds your FLT repo
<br/><br/>
</td>
</tr>
</table>

<br/>

---

<br/>

## 📥 Installation

```powershell
git clone https://github.com/guptahemant65/flt-edog-devmode.git
cd flt-edog-devmode
.\edog-setup.cmd
```

<br/>

---

<br/>

## 🚀 Quick Start

```powershell
# Step 1: Run setup (first time only)
edog-setup

# Step 2: Start DevMode
edog
# On first run, you'll be prompted to enter your Workspace ID, Artifact ID, and Capacity ID
```

<br/>

---

<br/>

## ⚙️ How It Works

<br/>

```
                                    EDOG DevMode Pipeline
    ┌─────────────────────────────────────────────────────────────────────────────────────┐
    │                                                                                     │
    │      ┌───────────────┐       ┌───────────────┐       ┌───────────────────────┐     │
    │      │               │       │               │       │                       │     │
    │      │    Browser    │ ───── │   EDOG Auth   │ ───── │   Token Acquisition   │     │
    │      │    Login      │       │    Portal     │       │                       │     │
    │      │               │       │               │       │                       │     │
    │      └───────────────┘       └───────────────┘       └───────────┬───────────┘     │
    │                                                                  │                 │
    │                                                                  ▼                 │
    │      ┌───────────────┐       ┌───────────────┐       ┌───────────────────────┐     │
    │      │               │       │               │       │                       │     │
    │      │  FLT Service  │ ◄──── │    Apply      │ ◄──── │    Configure FLT      │     │
    │      │  Auto-Launch  │       │   Changes     │       │      Codebase         │     │
    │      │               │       │               │       │                       │     │
    │      └───────┬───────┘       └───────────────┘       └───────────────────────┘     │
    │              │                                                                     │
    │              ▼                                                                     │
    │      ┌───────────────┐                                                             │
    │      │  Auto-Select  │  (Handles DevMode account picker popup automatically)       │
    │      │   Account     │                                                             │
    │      └───────┬───────┘                                                             │
    │              │                                                                     │
    │              │    ┌─────────────────────────────────────────────────────────┐      │
    │              └───►│  Monitor: Token refresh + Service health + Ctrl+C      │──────┘
    │                   └─────────────────────────────────────────────────────────┘      │
    │                                                                                     │
    └─────────────────────────────────────────────────────────────────────────────────────┘

    On Ctrl+C:  Stop Service (graceful) → Revert Code Changes → Exit
```

<br/>

---

<br/>

## 📖 Command Reference

<br/>

### Core Operations

<table>
<tr>
<th width="300">Command</th>
<th>Description</th>
</tr>
<tr>
<td><code>edog</code></td>
<td>Start DevMode: fetch token, apply changes, <b>launch FLT service</b>, auto-select account, auto-refresh tokens</td>
</tr>
<tr>
<td><code>edog --no-launch</code></td>
<td>Token management only (doesn't start FLT service)</td>
</tr>
<tr>
<td><code>edog --revert</code></td>
<td>Revert all EDOG modifications to the codebase</td>
</tr>
<tr>
<td><code>edog --status</code></td>
<td>Display current DevMode status and applied changes</td>
</tr>
</table>

<br/>

### Configuration

<table>
<tr>
<th width="300">Command</th>
<th>Description</th>
</tr>
<tr>
<td><code>edog --config</code></td>
<td>Display current configuration</td>
</tr>
<tr>
<td><code>edog --config -u &lt;email&gt;</code></td>
<td>Set Microsoft account email</td>
</tr>
<tr>
<td><code>edog --config -w &lt;guid&gt;</code></td>
<td>Set Fabric workspace ID</td>
</tr>
<tr>
<td><code>edog --config -a &lt;guid&gt;</code></td>
<td>Set artifact ID</td>
</tr>
<tr>
<td><code>edog --config -c &lt;guid&gt;</code></td>
<td>Set capacity ID</td>
</tr>
<tr>
<td><code>edog --config -r &lt;path&gt;</code></td>
<td>Set FabricLiveTable repository path</td>
</tr>
</table>

<br/>

### Maintenance

<table>
<tr>
<th width="300">Command</th>
<th>Description</th>
</tr>
<tr>
<td><code>edog --clear-token</code></td>
<td>Clear cached authentication token</td>
</tr>
</table>

<br/>

---

<br/>

## 🔧 Configuration

Configuration is stored in `edog-config.json`:

```json
{
  "username": "alias@microsoft.com",
  "workspace_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "artifact_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "capacity_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "flt_repo_path": "C:\\repos\\workload-fabriclivetable"
}
```

<br/>

### Capacity ID Sync

EDOG automatically syncs `capacity_id` with the `CapacityGuid` in `workload-dev-mode.json` (used by the FLT service's dev mode):

| Scenario | Behavior |
|----------|----------|
| **First-time setup** | Auto-detects from `workload-dev-mode.json` and prompts for confirmation |
| **On startup** | Checks for drift and auto-syncs from `workload-dev-mode.json` |
| **Manual update** | `edog --config -c <guid>` updates both files |
| **View sync status** | `edog --config` shows sync status with workload-dev-mode.json |

The path to `workload-dev-mode.json` is read from `launchSettings.json` in the FLT repository.

<br/>

### Finding Your IDs

All three IDs can be found in your EDOG API URL:

```
https://{capacity_id}.pbidedicated.windows-int.net/.../capacities/{capacity_id}/.../workspaces/{workspace_id}/artifacts/.../{artifact_id}/...
         ├─────────────────┘                        └─────────────────┘              └──────────────────┘                 └────────────┘
         │                                                   │                                │                                  │
         │                                                   │                                │                                  │
         ▼                                                   ▼                                ▼                                  ▼
    CAPACITY_ID                                        CAPACITY_ID                      WORKSPACE_ID                       ARTIFACT_ID
```

**Example URL:**
```
https://040ec9ea384642ada0dfc2b34a10c194.pbidedicated.windows-int.net/webapi/capacities/040ec9ea-3846-42ad-a0df-c2b34a10c194/workloads/.../workspaces/1a2ad450-f698-4389-b75b-4a5b21324586/artifacts/.../0d102c74-2b1d-4a33-9784-edabe1f6a6bd/...
```

| Parameter | Value from Example |
|-----------|-------------------|
| Capacity ID | `040ec9ea-3846-42ad-a0df-c2b34a10c194` |
| Workspace ID | `1a2ad450-f698-4389-b75b-4a5b21324586` |
| Artifact ID | `0d102c74-2b1d-4a33-9784-edabe1f6a6bd` |

<br/>

---

<br/>

## 🔍 Repository Detection

EDOG automatically locates your FabricLiveTable repository:

<br/>

```
    Detection Priority
    ─────────────────────────────────────────────────────────────

    1. ▶ Configured Path      Checks flt_repo_path in config
                                        │
                                        ▼ not found
    2. ▶ Current Directory    Scans current working directory
                                        │
                                        ▼ not found
    3. ▶ Parent Directories   Traverses up from current location
                                        │
                                        ▼ not found
    4. ▶ Home Directory       Searches up to 8 levels deep

    ─────────────────────────────────────────────────────────────
```

<br/>

To manually specify:
```powershell
edog --config -r C:\path\to\workload-fabriclivetable
```

<br/>

---

<br/>

## 🔒 Security

<table>
<tr>
<th width="200">Aspect</th>
<th>Implementation</th>
</tr>
<tr>
<td><b>Authentication</b></td>
<td>Microsoft OAuth 2.0 via corporate identity</td>
</tr>
<tr>
<td><b>Token Lifetime</b></td>
<td>1 hour with automatic 45-minute refresh cycle</td>
</tr>
<tr>
<td><b>Change Tracking</b></td>
<td>All modifications recorded in <code>.edog-changes.patch</code></td>
</tr>
<tr>
<td><b>Rollback</b></td>
<td>Clean revert using <code>git apply -R</code></td>
</tr>
<tr>
<td><b>Commit Protection</b></td>
<td>Optional pre-commit hook prevents accidental check-ins</td>
</tr>
</table>

<br/>

---

<br/>

## ❓ Troubleshooting

<table>
<tr>
<th width="250">Issue</th>
<th>Resolution</th>
</tr>
<tr>
<td>Python not found</td>
<td>Install Python 3.8+ and ensure it's in PATH</td>
</tr>
<tr>
<td>Playwright not found</td>
<td>Re-run <code>edog-setup</code></td>
</tr>
<tr>
<td>Pattern not found</td>
<td>Codebase may have changed; run <code>edog --status</code></td>
</tr>
<tr>
<td>Token invalid</td>
<td>Run <code>edog --clear-token</code> then <code>edog</code></td>
</tr>
<tr>
<td>Repository not found</td>
<td>Configure manually: <code>edog --config -r &lt;path&gt;</code></td>
</tr>
<tr>
<td>Permission denied</td>
<td>Run terminal as Administrator</td>
</tr>
</table>

<br/>

---

<br/>

## 💼 Typical Workflow

```powershell
# ┌─────────────────────────────────────────────────────────┐
# │  Morning: Start Development Session                     │
# └─────────────────────────────────────────────────────────┘

PS C:\> edog
✓ DevMode active. Token refreshes automatically.

# ┌─────────────────────────────────────────────────────────┐
# │  During the Day: Develop Normally                       │
# └─────────────────────────────────────────────────────────┘

#   ... write code, debug, test ...

# ┌─────────────────────────────────────────────────────────┐
# │  Before Commit: Clean Up EDOG Changes                   │
# └─────────────────────────────────────────────────────────┘

PS C:\> edog --revert
✓ All EDOG changes reverted

PS C:\> git add .
PS C:\> git commit -m "feat: implement new feature"
```

<br/>

---

<br/>

## 📁 Project Structure

```
flt-edog-devmode/
│
├── edog.py                 Core application logic
├── edog.cmd                Windows command wrapper
├── edog-setup.cmd          Installation script
├── edog-config.json        User configuration (gitignored)
├── edog-logs.py            Log & telemetry viewer
├── edog-logs.cmd           Log viewer launcher
└── install.ps1             PowerShell installer
```

<br/>

---

<br/>

## 📊 Log Viewer

A beautiful real-time log and telemetry viewer for monitoring your FLT DevMode session.

<br/>

### Features

<table>
<tr>
<td width="25%" align="center">
<br/>
<b>📋 Live Logs</b>
<br/>
Real-time log streaming with color-coded levels
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<b>📡 Telemetry</b>
<br/>
Visualize SSR events with status and duration
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<b>📊 Statistics</b>
<br/>
Track success rates and error counts
<br/><br/>
</td>
<td width="25%" align="center">
<br/>
<b>🎯 Activity</b>
<br/>
Breakdown by operation type
<br/><br/>
</td>
</tr>
</table>

<br/>

### How It Works

EDOG automatically injects console output into the FLT telemetry reporter. When you run `edog`, it modifies `CustomLiveTableTelemetryReporter.cs` to output telemetry events to the console in magenta color:

```
[TELEMETRY] Activity: RunDag | Status: Succeeded | Duration: 1234ms | Result: OK
            Attributes: {"nodeCount":"5","dagVersion":"v2"}
```

This allows the log viewer to capture and display real FLT telemetry events during your DevMode session.

<br/>

### Usage

```powershell
# Run with demo data (to test the UI)
edog-logs --demo

# Pipe FLT service output
dotnet run 2>&1 | edog-logs

# Read from log file
edog-logs < service.log
```

<br/>

### Screenshot

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        🐕 EDOG Log Viewer  │  FabricLiveTable DevMode        │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────── 📋 Live Logs ───────────────┐  ┌────── Statistics ────────┐ │
│ │ Time       │Level│ Component     │ Message │  │ 📊 Total Logs    1,247   │ │
│ │ 10:23:45   │INFO │ DagHandler    │ Start.. │  │ ℹ️  Info           892   │ │
│ │ 10:23:46   │INFO │ GTSClient     │ Submit. │  │ ⚠️  Warnings       312   │ │
│ │ 10:23:47   │WARN │ TokenManager  │ Expiry. │  │ ❌ Errors          43   │ │
│ │ 10:23:48   │INFO │ NodeExecutor  │ Node 3. │  │                          │ │
│ │ 10:23:49   │ERROR│ CatalogHandler│ Failed. │  │ 📡 Telemetry       156   │ │
│ └────────────────────────────────────────────┘  │ ✅ Succeeded       142   │ │
│ ┌──────────── 📡 Telemetry Events ───────────┐  │ ❌ Failed           14   │ │
│ │ Time    │ Activity      │ Status  │Duration│  └──────────────────────────┘ │
│ │ 10:23   │ RunDag        │ ✓ Pass  │ 1,234ms│  ┌── Activity Breakdown ────┐ │
│ │ 10:22   │ GetLatestDag  │ ✓ Pass  │   456ms│  │ RunDag          45  98%  │ │
│ │ 10:21   │ NodeExecution │ ✗ Fail  │ 2,100ms│  │ GetLatestDag    32 100%  │ │
│ └────────────────────────────────────────────┘  │ NodeExecution   79  95%  │ │
├──────────────────────────────────────────────────────────────────────────────┤
│              Press q to quit │ c to clear │ ? for help                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

<br/>

---

<div align="center">
<sub>Microsoft Internal Use Only</sub>
</div>
