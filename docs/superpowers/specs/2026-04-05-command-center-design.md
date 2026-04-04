# Command Center — Tab 4 Control Panel

**Date:** 2026-04-05
**Scope:** Wave 1 — RunDAG, CancelDAG, GetLatestDAG
**Location:** Tab 4 of the EDOG Log Viewer (replaces "Coming soon" placeholder)

## Problem

During development, a developer must constantly switch between the EDOG log viewer and the Fabric UI to trigger DAG executions, cancel stuck runs, or inspect the DAG structure. This context-switching breaks flow and wastes time. The log viewer already has all the observability — it just lacks the ability to act.

## Approach

Add a **Command Center** to Tab 4 that proxies API calls through EdogLogServer to the Fabric backend. Auth tokens and config IDs are already available on disk from edog.py. The web UI calls EdogLogServer proxy endpoints — no direct external calls from the browser.

```
Browser (Tab 4 UI on :5555)
  → EdogLogServer proxy routes (/api/flt/*)
    → Fabric infrastructure (pbidedicated.windows-int.net)
      → Local FLT service (auth disabled in EDOG devmode)
```

---

## Architecture

### Backend: EdogLogServer.cs Additions

#### Configuration Loading (on startup)

Read `edog-config.json` from the edog-devmode directory:
```json
{
  "workspace_id": "1a2ad450-f698-4389-b75b-4a5b21324586",
  "artifact_id": "0d102c74-2b1d-4a33-9784-edabe1f6a6bd",
  "capacity_id": "040ec9ea-3846-42ad-a0df-c2b34a10c194"
}
```

Read `.edog-token-cache` from the user's home directory:
- Format: base64-encoded `expiry_timestamp|token`
- Decode → extract token string and expiry time
- Re-read on each request (edog daemon may refresh the token independently)

Construct base URL:
```
https://{capacity_id}.pbidedicated.windows-int.net/webapi/capacities/{capacity_id}/workloads/Lakehouse/LakehouseService/automatic/v1/workspaces/{workspace_id}/lakehouses/{artifact_id}
```

#### Proxy Endpoints

| Route | Method | Proxies To | Notes |
|-------|--------|-----------|-------|
| `/api/flt/config` | GET | (local) | Returns workspace_id, artifact_id, capacity_id, token_expiry_minutes |
| `/api/flt/getlatestdag` | GET | `{base}/liveTable/getLatestDag?showExtendedLineage=true` | Returns full DAG structure |
| `/api/flt/rundag` | POST | `{base}/liveTableSchedule/runDAG/{iterationId}` | Generates new iterationId server-side, returns it |
| `/api/flt/canceldag/{iterationId}` | POST | `{base}/liveTableSchedule/cancelDAG/{iterationId}` | Cancels the given execution |

#### Proxy Implementation

Each proxy route:
1. Re-reads token from `.edog-token-cache` (edog daemon may have refreshed it)
2. Validates token not expired (if expired: return 401 with `{"error": "token_expired", "message": "Run edog --refresh-token"}`)
3. Constructs full Fabric URL
4. Forwards with headers: `Authorization: Bearer {mwc_token}`, `X-CORRELATION-ID: {new_guid}`
5. Returns the Fabric API response body and status code to the browser
6. On HttpClient exceptions (network, timeout): returns 502 with `{"error": "service_unreachable", "message": "..."}`

#### Token Re-reading Strategy

Do NOT cache the token in memory permanently. On each proxy request:
1. Read `.edog-token-cache` file
2. Decode base64 → split on `|` → parse expiry timestamp and token
3. If expiry < now: return 401 with token_expired error
4. Use the token for the outgoing request

This ensures we always use the latest token refreshed by the edog daemon.

#### Config File Path Discovery

EdogLogServer needs to find `edog-config.json`. Strategy:
1. Check environment variable `EDOG_CONFIG_PATH` (if set by edog.py)
2. Check `{current_directory}/edog-config.json`
3. Check `{user_home}/.edog/edog-config.json`
4. If not found: proxy endpoints return 503 with `{"error": "config_not_found"}`

For `.edog-token-cache`:
1. Check `{user_home}/.edog-token-cache`
2. Check `{edog_config_dir}/.edog-token-cache`

---

### Frontend: New Modules

#### New Files
- `src/edog-logs/js/control-panel.js` — Command Center logic
- `src/edog-logs/css/control.css` — Command Center styling

#### Modified Files
- `src/edog-logs/index.html` — Replace Tab 4 placeholder content
- `src/edog-logs/js/main.js` — Initialize ControlPanel, wire tab switch

---

## UI Design

### Connection Status Bar (top of Tab 4)

Always visible when Tab 4 is active. Three states:

**Connected:**
```
🟢 Connected · Token valid (38 min remaining)
   Workspace:  1a2ad450-f698-4389-b75b-4a5b21324586  [copy]
   Lakehouse:  0d102c74-2b1d-4a33-9784-edabe1f6a6bd  [copy]
   Capacity:   040ec9ea-3846-42ad-a0df-c2b34a10c194  [copy]
```

**Token expired:**
```
🟡 Token Expired
   Run: edog --refresh-token  [copy command]
   Workspace:  1a2ad450-...  Lakehouse:  0d102c74-...
```

**Config not found:**
```
🔴 Configuration not found
   Ensure edog-config.json exists in the edog-devmode directory
```

Implementation:
- Calls `GET /api/flt/config` on tab open
- Monospace font for GUIDs
- Copy button next to each ID (navigator.clipboard.writeText)
- Token remaining time updates every 60s

---

### Section 1: DAG Overview

Auto-fetches GetLatestDAG when Tab 4 is opened (debounced — only if last fetch was >30s ago).

**Success state:**
```
┌─────────────────────────────────────────────────────────┐
│  DAG: MyLiveTableDag  ·  12 nodes  ·  IncrementalRefresh│
│  [↻ Refresh]                                            │
├─────────────────────────────────────────────────────────┤
│  Node Name          │ Type      │ Dependencies          │
│  ─────────────────────────────────────────────────────  │
│  FactSales           │ Table     │ —                     │
│  DimCustomer         │ Table     │ —                     │
│  AggDailySales       │ Table     │ FactSales, DimCustomer│
│  DqCheck_Sales       │ DQ        │ AggDailySales         │
│  ...                                                    │
└─────────────────────────────────────────────────────────┘
```

- DAG name extracted from response
- Node count and refresh mode as badges
- Node table: sortable by name, shows dependency edges
- Refresh button to re-fetch

**Error states:**

| HTTP Status | Display |
|-------------|---------|
| 401/403 | Yellow banner: "Authentication failed. Run `edog --refresh-token`" + copy button |
| 404 | Red banner: "Lakehouse not found. Verify IDs in edog-config.json" + shows the IDs |
| 500+ | Red banner: "Server error" + collapsible response body detail |
| Network error | Red banner: "Cannot reach Fabric. Is your VPN/network connected?" + Retry button |
| Empty DAG (no nodes) | Grey state: "No LiveTable definitions found. Create materialized views in Fabric first." |

When any error exists, RunDAG button is disabled with tooltip explaining why.

---

### Section 2: Execution Control

A **two-state card** that switches between Idle and Active based on AutoDetector state.

#### Idle State

```
┌─────────────────────────────────────────────────────────┐
│  ▶ Run DAG                              [large green]   │
│                                                         │
│  Last execution: ✓ Succeeded · 45.2s · 12/12 nodes     │
│  2 minutes ago · iteration ...f6a6bd                    │
└─────────────────────────────────────────────────────────┘
```

- Big prominent Run button
- Last execution summary (from AutoDetector.detectedExecutions or /api/executions)
- If no previous execution: "No recent executions"
- Clicking Run:
  1. Button shows spinner + "Submitting..."
  2. POST `/api/flt/rundag` → server generates iterationId
  3. On success: transitions to Active state with the new iterationId
  4. On error: inline error message below button (stays in Idle)

#### Active State

```
┌─────────────────────────────────────────────────────────┐
│  ⟳ Running: iteration ...e1f7ed65  ·  38s elapsed      │
│  ████████████░░░░░░░░  5/12 nodes                      │
│                                                         │
│  ✓ FactSales          3.2s                              │
│  ✓ DimCustomer        1.8s                              │
│  ✓ DimProduct         2.1s                              │
│  ✓ DimDate            0.4s                              │
│  ⟳ AggDailySales      12.3s (running)                   │
│  ○ DqCheck_Sales      (waiting)                         │
│  ○ ...                                                  │
│                                                         │
│  [⏹ Cancel]  [↗ Watch Logs]                            │
└─────────────────────────────────────────────────────────┘
```

- Status header with elapsed timer (updates every 1s)
- Progress bar: completed nodes / total nodes
- Node status list (from AutoDetector node tracking):
  - ✓ completed (green) with duration
  - ⟳ running (blue, animated) with elapsed time
  - ✗ failed (red) with error code
  - ○ waiting (grey)
  - ⊘ skipped (muted)
- **Cancel button**: red, inline confirmation ("Cancel? [Yes] [No]"), calls `/api/flt/canceldag/{iterationId}`
- **Watch Logs button**: switches to Tab 1 AND sets correlation filter to this execution's RAID
- On completion: shows final status + duration, transitions to Idle after 5s with the result as "Last execution"

#### Active State — Data Source

Node progress comes from AutoDetector.detectedExecutions (already tracks node-level status from logs and telemetry). The ControlPanel registers as a listener on AutoDetector callbacks:
- `onExecutionDetected` → transition to Active
- `onExecutionUpdated` → update node list + progress bar
- `onErrorDetected` → show error badge on affected node

The RunDAG response returns the iterationId. The ControlPanel tells AutoDetector to watch for this specific iterationId so it picks it up immediately when the first logs arrive.

---

### Section 3: Execution History

Small table below the control card. Data from `/api/executions` endpoint (already exists).

```
┌────────────────────────────────────────────────────────────┐
│  Recent Executions                          [↻ Refresh]    │
├────────────────────────────────────────────────────────────┤
│  Iteration     │ Status    │ Duration │ Nodes │ Time       │
│  ...e1f7ed65   │ ✓ Success │ 45.2s    │ 12/12 │ 2 min ago  │
│  ...a3cc6eb9   │ ✗ Failed  │ 23.1s    │ 8/12  │ 15 min ago │
│  ...b75b4a5b   │ ✓ Success │ 41.8s    │ 12/12 │ 1 hr ago   │
│  ...9784edab   │ ⊘ Cancel  │ 12.0s    │ 3/12  │ 2 hr ago   │
└────────────────────────────────────────────────────────────┘
```

- Shows last 10 executions
- Status badges: green ✓, red ✗, grey ⊘
- Click row → expands inline with node breakdown + error details
- Auto-refreshes when tab is active

---

## Implementation Details

### control-panel.js Module Structure

```javascript
class ControlPanel {
  constructor(containerEl, { autoDetector, stateManager }) { ... }

  // Lifecycle
  async activate()    // Called when Tab 4 becomes active
  deactivate()        // Called when leaving Tab 4

  // API calls
  async _fetchConfig()      // GET /api/flt/config
  async _fetchLatestDag()   // GET /api/flt/getlatestdag
  async _runDag()           // POST /api/flt/rundag
  async _cancelDag(id)      // POST /api/flt/canceldag/{id}
  async _fetchHistory()     // GET /api/executions (existing endpoint)

  // Rendering
  _renderConnectionBar(config)
  _renderDagOverview(dagData)
  _renderExecutionControl(state)  // idle or active
  _renderNodeProgress(nodes)
  _renderHistory(executions)
  _renderError(section, error)

  // AutoDetector integration
  _onExecutionDetected(execution)
  _onExecutionUpdated(execution)
  _onErrorDetected(error)

  // State
  _isActive = false         // Tab 4 visible?
  _dagData = null           // Cached GetLatestDAG response
  _lastDagFetch = 0         // Timestamp for debounce
  _activeIterationId = null // Currently running execution
  _elapsedTimer = null      // setInterval for elapsed time
}
```

### EdogLogServer.cs Additions

New class: `EdogApiProxy` — handles config reading, token management, and HTTP forwarding.

```csharp
internal class EdogApiProxy
{
    private readonly string edogConfigPath;
    private readonly string tokenCachePath;
    private readonly HttpClient httpClient;

    // Called on each request — always re-reads from disk
    public (string token, DateTime expiry) ReadToken()
    public EdogConfig ReadConfig()
    public string BuildBaseUrl(EdogConfig config)

    // Proxy methods
    public Task<ProxyResult> GetLatestDag()
    public Task<ProxyResult> RunDag()        // Generates iterationId
    public Task<ProxyResult> CancelDag(string iterationId)
    public Task<ProxyResult> GetConfig()     // Returns config + token info
}
```

Route registration in `ConfigureRoutes()`:
```csharp
app.MapGet("/api/flt/config", proxy.HandleConfig);
app.MapGet("/api/flt/getlatestdag", proxy.HandleGetLatestDag);
app.MapPost("/api/flt/rundag", proxy.HandleRunDag);
app.MapPost("/api/flt/canceldag/{iterationId}", proxy.HandleCancelDag);
```

### Config and Token Discovery

**edog-config.json path:**
1. `EDOG_CONFIG_PATH` environment variable (if set)
2. Walk up from EdogLogServer assembly location looking for `edog-config.json`
3. `%USERPROFILE%\.edog\edog-config.json`

**.edog-token-cache path:**
1. Same directory as edog-config.json
2. `%USERPROFILE%\.edog-token-cache`

### Error Response Format

All proxy errors return JSON:
```json
{
  "error": "token_expired|config_not_found|service_unreachable|api_error",
  "message": "Human-readable description",
  "statusCode": 401,
  "detail": "Optional response body from upstream"
}
```

---

## Integration Points

| Existing Module | Integration |
|----------------|-------------|
| **AutoDetector** | ControlPanel subscribes to execution/error callbacks. After RunDAG, tells AutoDetector to expect the new iterationId |
| **SmartContextBar** | RunDAG triggers context bar update. CancelDAG clears it |
| **main.js Tab System** | Tab 4 activate/deactivate calls ControlPanel.activate()/deactivate() |
| **Filters** | "Watch Logs" button calls main.js filterLogsByCorrelation() + tab switch |
| **State Manager** | History section reads knownIterationIds from state |

---

## Styling Principles

- Consistent with existing DevTools-inspired theme (dark background, monospace IDs, tight sections)
- Status badges match existing color scheme: green=success, red=failed, blue=running, grey=idle
- Cards use 1px border with subtle shadow, matching detail.css sections
- Buttons: filled for primary actions (Run=green, Cancel=red), outlined for secondary (Refresh, Watch Logs)
- Progress bar: thin (4px), same blue as running status
- Node list: compact rows (28px height), left-aligned with status icon prefix

---

## Out of Scope (Wave 2+)

- GetDAGExecMetrics display
- MLV Execution Definition CRUD
- DAG Settings management
- Refresh Trigger management
- Maintenance operations (force unlock, orphan cleanup)
- DAG dependency graph visualization
- Execution comparison (diff two runs)
