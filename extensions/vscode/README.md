# FLT EDOG DevMode

VS Code extension for automating FabricLiveTable EDOG development workflow.

## Features

- 🔐 **One-click token management** - Fetch MWC tokens via browser automation
- 🔄 **Auto-refresh** - Automatically refreshes tokens before expiry
- 📊 **Status bar countdown** - Shows remaining token time in status bar
- ⚡ **Quick commands** - Start, stop, revert, copy token
- 🔍 **Auto-detect** - Reads IDs from `workload-dev-mode.json`
- 📋 **Clipboard support** - Copy token with one click

## Installation

### Build from source

```bash
cd tools/flt-edog-devmode
npm install
npm run compile
npm run package   # Creates .vsix file
```

Then install the `.vsix` file in VS Code:
- Open VS Code
- Ctrl+Shift+P → "Extensions: Install from VSIX..."
- Select the generated `.vsix` file

### Prerequisites

- Python 3.8+ with `playwright` installed
- Edge browser for authentication

## Commands

| Command | Description |
|---------|-------------|
| `FLT EDOG: Start DevMode` | Start token monitoring and apply changes |
| `FLT EDOG: Stop DevMode` | Stop monitoring (changes remain applied) |
| `FLT EDOG: Revert Changes` | Undo all code changes |
| `FLT EDOG: Refresh Token Now` | Force immediate token refresh |
| `FLT EDOG: Copy Token to Clipboard` | Copy current MWC token |
| `FLT EDOG: Show Status` | Show detailed status in output panel |

## Configuration

Configure in VS Code settings (Ctrl+,):

| Setting | Description | Default |
|---------|-------------|---------|
| `flt-edog.username` | Login email/username | (empty) |
| `flt-edog.workspaceId` | Workspace GUID | (empty) |
| `flt-edog.artifactId` | Lakehouse/Artifact GUID | (empty) |
| `flt-edog.capacityId` | Capacity GUID | (empty) |
| `flt-edog.autoDetect` | Auto-detect from workload-dev-mode.json | true |
| `flt-edog.checkIntervalMins` | Token check interval | 5 |
| `flt-edog.refreshThresholdMins` | Refresh when less than X mins remaining | 10 |

## Status Bar

The extension shows token status in the status bar:

- `$(shield) FLT EDOG: Ready` - Extension ready, not running
- `$(sync~spin) FLT EDOG: Starting...` - Fetching token
- `$(shield) FLT EDOG: 45m` - Token valid for 45 minutes
- `$(warning) FLT EDOG: 8m` - Token expiring soon (≤10 mins)
- `$(warning) FLT EDOG: Expired` - Token has expired

## How It Works

1. **Start DevMode** opens Edge browser for EDOG authentication
2. Captures Bearer token from network requests
3. Calls `generatemwctoken` API to get MWC token
4. Applies token and auth bypass changes to 4 files
5. Monitors expiry and auto-refreshes when ≤10 mins remaining
6. **Revert** undoes all changes using pattern matching

## Files Modified

When DevMode is active, these files are modified:

- `LiveTableController.cs` - Auth filters commented out
- `LiveTableSchedulerRunController.cs` - Auth filters commented out  
- `GTSOperationManager.cs` - MWC V1 token hardcoded
- `GTSBasedSparkClient.cs` - Token generation bypassed

All changes are marked with `// EDOG DevMode` for easy identification.

## Troubleshooting

### "Could not find get-edog-token.py"
Make sure you're in the `workload-fabriclivetable` repository root.

### Browser doesn't open
Install Playwright browsers: `playwright install msedge`

### 401 Unauthorized after token refresh
MWC tokens are workspace-specific. Make sure the workspace/artifact IDs match your EDOG environment.

### Changes won't revert
Check if files are locked by VS or another process. Close any editors and try again.

## Development

```bash
npm run watch   # Compile on change
F5              # Launch extension development host
```
