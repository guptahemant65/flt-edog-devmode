# FLT EDOG DevMode

One-click MWC token management for FabricLiveTable EDOG development.

## Quick Start

```bash
# First time setup
edog-setup

# Configure your IDs
edog --config -w WORKSPACE_ID -a ARTIFACT_ID -c CAPACITY_ID

# Start DevMode (from FLT repo directory)
edog
```

## Run From Anywhere

The setup script automatically:
- **Auto-detects** the FabricLiveTable repo (searches `newrepo`, `repos`, etc.)
- **Adds edog to PATH** so you can run it from any terminal

If auto-detection fails, set the path manually:
```bash
edog --config -r C:\path\to\workload-fabriclivetable
```

## What It Does

1. Opens browser for Microsoft login
2. Fetches MWC token from EDOG
3. Applies bypass changes to FabricLiveTable codebase
4. Auto-refreshes token every 45 minutes

## Commands

| Command | Description |
|---------|-------------|
| `edog` | Start DevMode |
| `edog --revert` | Revert all code changes |
| `edog --status` | Check current status |
| `edog --config` | View/update configuration |
| `edog --config -r <path>` | Set FLT repo path (enables global usage) |
| `edog --install-hook` | Install git pre-commit hook |

## Requirements

- Python 3.8+
- Microsoft account with EDOG access
- FabricLiveTable repo cloned

## Project Structure

```
flt-edog-devmode/
├── edog.py              # Core Python script
├── edog.cmd             # Windows command wrapper
├── edog-setup.cmd       # One-time setup script
├── edog-config.json     # Local config (gitignored)
├── extensions/
│   ├── vscode/          # VS Code extension
│   └── vs2022/          # Visual Studio 2022 extension
└── pip-package/         # Pip installable package
```

## Distribution Options

### Option 1: Clone this repo (Recommended)
```bash
git clone <this-repo>
cd flt-edog-devmode
edog-setup
```

### Option 2: Pip install (Azure Artifacts)
```bash
pip install flt-edog-devmode --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
edog --setup
```

### Option 3: VS Code Extension
Install `extensions/vscode/flt-edog-devmode-1.0.0.vsix`

## Security

- Requires Microsoft OAuth login - only Microsoft employees can authenticate
- Tokens are short-lived (1 hour) and auto-refreshed
- All code changes tracked via git patch file (`.edog-changes.patch`)
- Run `edog --revert` to cleanly undo all changes using `git apply -R`

## Configuration

Config file location: `<edog-install-dir>/edog-config.json`

```json
{
  "username": "you@microsoft.com",
  "workspace_id": "your-workspace-id",
  "artifact_id": "your-artifact-id",
  "capacity_id": "your-capacity-id",
  "flt_repo_path": "C:\\path\\to\\workload-fabriclivetable"
}
```

## Troubleshooting

**"Python not found"** - Install Python 3.8+ and add to PATH

**"playwright not found"** - Run `edog-setup` again

**"pattern not found"** - The target codebase may have changed, check with `edog --status`

## License

Internal Microsoft use only.
