# EDOG DevMode

Automated MWC token management for FabricLiveTable development.

## Overview

EDOG DevMode streamlines the developer experience by automating authentication and token management for FabricLiveTable EDOG environments. It eliminates manual token handling, allowing developers to focus on building features.

### Key Features

- **Automated Authentication** — Browser-based Microsoft OAuth login
- **Token Management** — Automatic refresh every 45 minutes
- **Code Injection** — Seamless bypass configuration for local development
- **Repository Detection** — Automatic FabricLiveTable repo discovery
- **Change Tracking** — Git-based patch system for clean rollbacks

## Requirements

- Windows 10/11
- Python 3.8 or later
- FabricLiveTable repository (cloned locally)
- Microsoft corporate account with EDOG access

## Installation

### Option 1: Git Clone (Recommended)

```powershell
git clone https://github.com/guptahemant65/flt-edog-devmode.git
cd flt-edog-devmode
.\edog-setup.cmd
```

### Option 2: pip Install

```powershell
pip install flt-edog-devmode --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
```

## Quick Start

```powershell
# 1. Run setup (first time only)
edog-setup

# 2. Configure your environment
edog --config -w <WORKSPACE_ID> -a <ARTIFACT_ID> -c <CAPACITY_ID>

# 3. Start DevMode
edog
```

## How It Works

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            EDOG DevMode Flow                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│    ┌─────────────┐      ┌─────────────┐      ┌─────────────────────┐    │
│    │   Browser   │ ──── │  EDOG Auth  │ ──── │  Token Acquisition  │    │
│    │   Login     │      │   Portal    │      │                     │    │
│    └─────────────┘      └─────────────┘      └──────────┬──────────┘    │
│                                                         │               │
│                                                         ▼               │
│    ┌─────────────┐      ┌─────────────┐      ┌─────────────────────┐    │
│    │   Active    │ ◄─── │   Apply     │ ◄─── │   Configure FLT     │    │
│    │   DevMode   │      │   Changes   │      │   Codebase          │    │
│    └──────┬──────┘      └─────────────┘      └─────────────────────┘    │
│           │                                                             │
│           └──────────── Auto-refresh every 45 minutes ──────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Command Reference

### Core Operations

| Command | Description |
|---------|-------------|
| `edog` | Start DevMode daemon with automatic token refresh |
| `edog --revert` | Revert all EDOG modifications to the codebase |
| `edog --status` | Display current DevMode status and applied changes |

### Configuration

| Command | Description |
|---------|-------------|
| `edog --config` | Display current configuration |
| `edog --config -u <email>` | Set Microsoft account email |
| `edog --config -w <guid>` | Set Fabric workspace ID |
| `edog --config -a <guid>` | Set artifact ID |
| `edog --config -c <guid>` | Set capacity ID |
| `edog --config -r <path>` | Set FabricLiveTable repository path |

### Git Integration

| Command | Description |
|---------|-------------|
| `edog --install-hook` | Install pre-commit hook to prevent accidental commits |
| `edog --uninstall-hook` | Remove pre-commit hook |

### Maintenance

| Command | Description |
|---------|-------------|
| `edog --clear-token` | Clear cached authentication token |

## Configuration

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

### Finding Your IDs

| Parameter | Location |
|-----------|----------|
| Workspace ID | Fabric Portal URL: `app.fabric.microsoft.com/groups/{workspace_id}/...` |
| Artifact ID | Fabric Portal URL: `.../{artifact_id}?experience=...` |
| Capacity ID | Fabric Admin Portal → Capacities → Select capacity → Copy ID from URL |

## Repository Detection

EDOG automatically locates your FabricLiveTable repository using a multi-stage detection strategy:

1. **Configured Path** — Checks `flt_repo_path` in configuration
2. **Current Directory** — Scans current working directory
3. **Parent Directories** — Traverses up from current location
4. **Home Directory Search** — Searches up to 8 levels deep from user home

To manually specify the repository location:

```powershell
edog --config -r C:\path\to\workload-fabriclivetable
```

## Security

| Aspect | Implementation |
|--------|----------------|
| Authentication | Microsoft OAuth 2.0 via corporate identity |
| Token Lifetime | 1 hour with automatic 45-minute refresh cycle |
| Change Tracking | All modifications recorded in `.edog-changes.patch` |
| Rollback | Clean revert using `git apply -R` |
| Commit Protection | Optional pre-commit hook prevents accidental check-ins |

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| Python not found | Install Python 3.8+ and ensure it's added to PATH |
| Playwright not found | Re-run `edog-setup` to install dependencies |
| Pattern not found | Codebase structure may have changed; run `edog --status` |
| Token invalid | Run `edog --clear-token` followed by `edog` |
| Repository not found | Manually configure: `edog --config -r <path>` |
| Permission denied | Run terminal as Administrator |

## Typical Workflow

```powershell
# Start development session
edog
# Output: DevMode active. Token refreshes automatically.

# Develop normally...

# Before committing, revert EDOG changes
edog --revert

# Commit your work
git add .
git commit -m "feat: implement new feature"
```

## Project Structure

```
flt-edog-devmode/
├── edog.py                 # Core application logic
├── edog.cmd                # Windows command wrapper
├── edog-setup.cmd          # Installation script
├── edog-config.json        # User configuration (gitignored)
├── install.ps1             # PowerShell installer
├── pip-package/            # PyPI distribution package
└── extensions/
    └── vs2022/             # Visual Studio 2022 extension
```

## Support

For issues or feature requests, contact the FabricLiveTable team.

---

*Microsoft Internal Use Only*
