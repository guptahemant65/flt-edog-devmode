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

<table>
<tr>
<td>

### Option 1: Git Clone &nbsp;`Recommended`

```powershell
git clone https://github.com/guptahemant65/flt-edog-devmode.git
cd flt-edog-devmode
.\edog-setup.cmd
```

</td>
<td>

### Option 2: pip Install

```powershell
pip install flt-edog-devmode \
  --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
```

</td>
</tr>
</table>

<br/>

---

<br/>

## 🚀 Quick Start

```powershell
# Step 1: Run setup (first time only)
edog-setup

# Step 2: Configure your environment
edog --config -w <WORKSPACE_ID> -a <ARTIFACT_ID> -c <CAPACITY_ID>

# Step 3: Start DevMode
edog
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
    │                                                                                     │
    │      ┌───────────────┐       ┌───────────────┐       ┌───────────────────────┐     │
    │      │               │       │               │       │                       │     │
    │      │    Browser    │ ───── │   EDOG Auth   │ ───── │   Token Acquisition   │     │
    │      │    Login      │       │    Portal     │       │                       │     │
    │      │               │       │               │       │                       │     │
    │      └───────────────┘       └───────────────┘       └───────────┬───────────┘     │
    │                                                                  │                 │
    │                                                                  │                 │
    │                                                                  ▼                 │
    │      ┌───────────────┐       ┌───────────────┐       ┌───────────────────────┐     │
    │      │               │       │               │       │                       │     │
    │      │    Active     │ ◄──── │    Apply      │ ◄──── │    Configure FLT      │     │
    │      │   DevMode     │       │   Changes     │       │      Codebase         │     │
    │      │               │       │               │       │                       │     │
    │      └───────┬───────┘       └───────────────┘       └───────────────────────┘     │
    │              │                                                                     │
    │              │                                                                     │
    │              └─────────────── Auto-refresh Token Every 45 Minutes ─────────────┘   │
    │                                                                                     │
    └─────────────────────────────────────────────────────────────────────────────────────┘
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
<td>Start DevMode daemon with automatic token refresh</td>
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

### Git Integration

<table>
<tr>
<th width="300">Command</th>
<th>Description</th>
</tr>
<tr>
<td><code>edog --install-hook</code></td>
<td>Install pre-commit hook to prevent accidental commits</td>
</tr>
<tr>
<td><code>edog --uninstall-hook</code></td>
<td>Remove pre-commit hook</td>
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

### Finding Your IDs

<table>
<tr>
<th width="150">Parameter</th>
<th>Where to Find</th>
</tr>
<tr>
<td><b>Workspace ID</b></td>
<td>Fabric Portal URL → <code>app.fabric.microsoft.com/groups/<b>{workspace_id}</b>/...</code></td>
</tr>
<tr>
<td><b>Artifact ID</b></td>
<td>Fabric Portal URL → <code>.../<b>{artifact_id}</b>?experience=...</code></td>
</tr>
<tr>
<td><b>Capacity ID</b></td>
<td>Fabric Admin Portal → Capacities → Select capacity → Copy from URL</td>
</tr>
</table>

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
├── install.ps1             PowerShell installer
│
├── pip-package/            PyPI distribution package
│
└── extensions/
    └── vs2022/             Visual Studio 2022 extension
```

<br/>

---

<div align="center">
<sub>Microsoft Internal Use Only</sub>
</div>
