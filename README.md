# 🐕 FLT EDOG DevMode

> **One-click MWC token management for FabricLiveTable EDOG development**

[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![Internal](https://img.shields.io/badge/Microsoft-Internal-red.svg)]()

---

## ⚡ Quick Start

```bash
# 1️⃣ First time setup (installs dependencies + adds to PATH)
edog-setup

# 2️⃣ Configure your IDs (one-time)
edog --config -w WORKSPACE_ID -a ARTIFACT_ID -c CAPACITY_ID

# 3️⃣ Start DevMode 🚀
edog
```

That's it! EDOG will handle authentication, token refresh, and code changes automatically.

---

## 🎯 What It Does

```
┌─────────────────────────────────────────────────────────────────┐
│                        EDOG DevMode Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1. 🔐 Opens browser for Microsoft login                       │
│                     ↓                                           │
│   2. 🎟️  Fetches MWC token from EDOG portal                     │
│                     ↓                                           │
│   3. 📝 Applies bypass changes to FLT codebase                  │
│                     ↓                                           │
│   4. 🔄 Auto-refreshes token every 45 minutes                   │
│                                                                 │
│   ✨ You code, EDOG handles the rest!                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Commands Reference

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `edog` | 🚀 Start DevMode daemon | `edog` |
| `edog --revert` | ↩️ Revert all code changes | `edog --revert` |
| `edog --status` | 📊 Check current status | `edog --status` |

### Configuration

| Command | Description | Example |
|---------|-------------|---------|
| `edog --config` | 👁️ View current config | `edog --config` |
| `edog --config -u <email>` | 📧 Set username/email | `edog --config -u you@microsoft.com` |
| `edog --config -w <id>` | 🏢 Set workspace ID | `edog --config -w abc-123-def` |
| `edog --config -a <id>` | 📦 Set artifact ID | `edog --config -a xyz-789-uvw` |
| `edog --config -c <id>` | ⚡ Set capacity ID | `edog --config -c cap-456-ijk` |
| `edog --config -r <path>` | 📁 Set FLT repo path | `edog --config -r C:\repos\flt` |

### Git Integration

| Command | Description |
|---------|-------------|
| `edog --install-hook` | 🪝 Install pre-commit hook (blocks accidental commits) |
| `edog --uninstall-hook` | 🗑️ Remove pre-commit hook |

### Troubleshooting

| Command | Description |
|---------|-------------|
| `edog --clear-token` | 🔑 Clear cached auth token (fixes auth issues) |

---

## 🌍 Run From Anywhere

EDOG auto-detects your FabricLiveTable repo! The setup script:

- ✅ **Auto-detects** the FLT repo (searches up to 8 levels deep)
- ✅ **Adds edog to PATH** so you can run from any terminal
- ✅ **Caches location** for instant startup next time

```bash
# Works from any directory!
C:\Users\you> edog
✅ Auto-detected FLT repo: C:\Users\you\repos\workload-fabriclivetable
```

If auto-detection fails, set the path manually:
```bash
edog --config -r C:\path\to\workload-fabriclivetable
```

---

## 📦 Installation Options

### Option 1: Clone this repo ⭐ Recommended

```bash
git clone https://github.com/guptahemant65/flt-edog-devmode.git
cd flt-edog-devmode
edog-setup
```

### Option 2: Pip install (Azure Artifacts)

```bash
pip install flt-edog-devmode --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
edog --setup
```

### Option 3: VS Code Extension

Install from: `extensions/vscode/flt-edog-devmode-1.0.0.vsix`

---

## 🔧 Configuration

Config is stored in `<edog-install-dir>/edog-config.json`:

```json
{
  "username": "you@microsoft.com",
  "workspace_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "artifact_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "capacity_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "flt_repo_path": "C:\\repos\\workload-fabriclivetable"
}
```

### Where to find your IDs?

| ID | Where to find |
|----|---------------|
| **Workspace ID** | Fabric portal URL: `app.fabric.microsoft.com/groups/{workspace_id}/...` |
| **Artifact ID** | Fabric portal URL: `.../{artifact_id}?experience=...` |
| **Capacity ID** | Fabric Admin portal → Capacities → Select capacity → URL contains ID |

---

## 📁 Project Structure

```
flt-edog-devmode/
├── 🐍 edog.py              # Core Python script
├── 📄 edog.cmd             # Windows command wrapper
├── 🔧 edog-setup.cmd       # One-time setup script
├── ⚙️ edog-config.json     # Local config (gitignored)
├── 📂 extensions/
│   ├── 💻 vscode/          # VS Code extension
│   └── 🖥️ vs2022/          # Visual Studio 2022 extension
└── 📦 pip-package/         # Pip installable package
```

---

## 🔒 Security

| Feature | Description |
|---------|-------------|
| 🔐 **OAuth Login** | Microsoft auth only - requires @microsoft.com account |
| ⏱️ **Short-lived Tokens** | Tokens expire in 1 hour, auto-refreshed every 45 min |
| 📋 **Change Tracking** | All changes saved to `.edog-changes.patch` for easy review |
| ↩️ **Clean Revert** | `edog --revert` uses `git apply -R` for perfect rollback |
| 🪝 **Commit Protection** | Optional pre-commit hook blocks accidental EDOG commits |

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Python not found"** | Install [Python 3.8+](https://www.python.org/downloads/) and add to PATH |
| **"playwright not found"** | Run `edog-setup` again |
| **"pattern not found"** | FLT codebase may have changed - check with `edog --status` |
| **"Token invalid/expired"** | Run `edog --clear-token` then `edog` again |
| **"FLT repo not found"** | Set path manually: `edog --config -r C:\path\to\flt` |
| **"Permission denied"** | Run terminal as Administrator |

---

## 📝 Example Workflow

```bash
# Morning: Start your dev session
C:\> edog
🔐 Opening browser for login...
✅ Token fetched successfully!
📝 Applying EDOG changes...
✅ DevMode active! Token refreshes automatically.

# ... code all day ...

# Evening: Clean up before committing
C:\> edog --revert
✅ All EDOG changes reverted

# Commit your actual work
C:\> git add . && git commit -m "My feature"
```

---

## 📜 License

**Internal Microsoft use only.**

---

<p align="center">
  Made with ❤️ by the FabricLiveTable team
</p>
