# FLT EDOG DevMode - Visual Studio 2022 Extension

VS 2022 extension for automating FabricLiveTable EDOG development workflow.

## Features

- 🔐 **One-click token management** - Fetch MWC tokens via browser automation
- 🔄 **Auto-refresh** - Automatically refreshes tokens before expiry
- 📊 **Status bar** - Shows remaining token time
- ⚡ **Menu commands** - Start, stop, revert, refresh, status

## Installation

### Step-by-step (Recommended)

1. **Open Visual Studio 2022**
2. **Open this project:**
   - File → Open → Project/Solution
   - Navigate to: `tools\FLTEdogDevMode.VS2022\FLTEdogDevMode.csproj`
3. **Build the extension:**
   - Build → Build Solution (or Ctrl+Shift+B)
4. **Install the VSIX:**
   - In Solution Explorer, right-click the project → Open Folder in File Explorer
   - Go to `bin\Debug` (or `bin\Release`)
   - Double-click `FLTEdogDevMode.vsix`
   - Follow the installer prompts
5. **Restart Visual Studio 2022**

### Alternative: Command line build

```cmd
cd tools\FLTEdogDevMode.VS2022
msbuild /p:Configuration=Release
```
Then install the `.vsix` from `bin\Release`.

### Prerequisites

- Visual Studio 2022 (17.0 or later)
- Python 3.8+ with `playwright` installed
- Edge browser for authentication

## Usage

After installation, find commands under **Tools → FLT EDOG DevMode**:

| Command | Description |
|---------|-------------|
| **Start DevMode** | Start token monitoring and apply changes |
| **Stop DevMode** | Stop monitoring (changes remain applied) |
| **Revert Changes** | Undo all code changes |
| **Refresh Token Now** | Force immediate token refresh |
| **Show Status** | Show detailed status dialog |

## Configuration

The extension reads configuration from `edog-config.json` in the repo root.
First run will prompt for workspace, artifact, and capacity IDs.

## How It Works

1. **Start DevMode** opens Edge browser for EDOG authentication
2. Captures Bearer token from network requests
3. Calls `generatemwctoken` API to get MWC token
4. Applies token and auth bypass changes to 4 files
5. Monitors expiry and auto-refreshes when ≤10 mins remaining
6. **Revert Changes** undoes all modifications

## Files Modified

- `LiveTableController.cs` - Auth filters commented out
- `LiveTableSchedulerRunController.cs` - Auth filters commented out
- `GTSOperationManager.cs` - MWC V1 token hardcoded
- `GTSBasedSparkClient.cs` - Token generation bypassed

All changes are marked with `// EDOG DevMode` for easy identification.
