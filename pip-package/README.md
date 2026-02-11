# FLT EDOG DevMode

MWC Token Manager for FabricLiveTable EDOG Development.

## Installation

### From Azure Artifacts (Internal)
```bash
pip install flt-edog-devmode --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
```

### First-Time Setup
```bash
edog --setup
```

This installs the Chromium browser for automation.

## Usage

### Configure Your IDs
```bash
edog --config -w YOUR_WORKSPACE_ID -a YOUR_ARTIFACT_ID -c YOUR_CAPACITY_ID
```

### Start DevMode
```bash
edog
```

This will:
1. Open browser for Microsoft login
2. Fetch MWC token from EDOG
3. Apply bypass changes to the codebase
4. Auto-refresh token every 45 minutes

### Other Commands
```bash
edog --revert     # Revert all code changes
edog --status     # Check if changes are applied
edog --config     # View current configuration
```

## Requirements

- Python 3.8+
- Microsoft Account with EDOG access
- Must run from the workload-fabriclivetable repo root

## Security

- Requires Microsoft OAuth login
- Tokens are short-lived (1 hour) and auto-refreshed
- All code changes are marked with `// EDOG DevMode` comments
