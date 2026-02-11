# FLT EDOG DevMode

One-click MWC token management for FabricLiveTable EDOG development.

## Quick Start

```bash
# First time setup
edog-setup

# Configure your IDs
edog --config -w WORKSPACE_ID -l LAKEHOUSE_ID -c CAPACITY_ID

# Start DevMode
edog
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
- All code changes marked with `// EDOG DevMode` comments
- Run `edog --revert` to clean up before committing

## Configuration

Config file: `~/.edog-config.json`

```json
{
  "workspace_id": "your-workspace-id",
  "lakehouse_id": "your-lakehouse-id",
  "capacity_id": "your-capacity-id",
  "email": "you@microsoft.com"
}
```

## Troubleshooting

**"Python not found"** - Install Python 3.8+ and add to PATH

**"playwright not found"** - Run `edog-setup` again

**"pattern not found"** - The target codebase may have changed, check with `edog --status`

## License

Internal Microsoft use only.
