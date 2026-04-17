# EDOG DevMode — UI/UX Design Brief

## What is EDOG?

EDOG DevMode is a **localhost developer tool** (web UI at `http://localhost:5555`) used by Microsoft engineers while developing **FabricLiveTable (FLT)** — a service that materializes SQL/PySpark-defined views into Delta Lake tables. 

The tool runs alongside the FLT service on the developer's machine. It automates token management, patches the FLT code for local development, launches the service, and provides a real-time dashboard for monitoring, debugging, and controlling the service.

Think of it as **Chrome DevTools but for FLT** — a single browser tab that gives the developer everything they need without leaving their IDE.

---

## Who uses it?

Senior C# backend engineers at Microsoft. They:
- Live in Visual Studio, terminals, and Azure Data Explorer (Kusto)
- Are debugging distributed systems daily
- Value information density and keyboard shortcuts
- Run this tool 8+ hours a day while developing
- Switch between this UI, their IDE, and occasionally Fabric portal

---

## What does the UI need to do?

The UI has **6 main views** + an always-visible top status bar + a sidebar nav + a command palette (Ctrl+K).

### Always-Visible Top Bar
Shows at all times:
- **Service status**: Running/Stopped/Building with uptime
- **Token health**: MWC token expiry countdown (color shifts as it approaches expiry), click to see decoded JWT claims
- **Git info**: Current branch, number of uncommitted files, whether EDOG patches are applied
- **Quick actions**: Restart service button

### Sidebar Navigation (6 views)

---

### View 1: Workspace Explorer ⭐ (default view on launch)

**This is the star feature.** A three-panel layout:

**Left panel — Object Tree:**
- Hierarchical tree: Tenant → Workspaces → Artifacts (Lakehouses, Notebooks, Pipelines)
- Each item shows: name, type indicator, status
- Expand/collapse with arrows
- Right-click for context menu (Rename, Delete, Open in Fabric, Copy ID)

**Center panel — Content:**
When a Lakehouse is selected, shows:
- Lakehouse header (name, ID, capacity, last modified)
- **Tables section**: Name, Type (Delta/Parquet), Row count, Size, Last Modified, Column count
  - Click a table → populates the right panel
- **MLV Definitions section**: Materialized view definitions with status, refresh mode, last run

**Right panel — Inspector:**
When a table is selected:
- Schema (column names, types, nullable)
- Data preview (first few rows)
- Stats (row count, file count, size, partitions)

**Bottom: New Test Environment wizard**
A collapsible inline wizard (not a modal) that creates a complete test setup:
1. Create Workspace → 2. Create Lakehouse → 3. Add MLV definitions → 4. Configure capacity → 5. Review & Create

---

### View 2: Logs

Real-time streaming log viewer (WebSocket, up to 10,000 entries):
- Each log row: timestamp, level (Verbose/Message/Warning/Error), component, message
- Level shown as colored left border on each row
- Filters: by level, component, text search, time range, execution ID
- **Breakpoint logs**: Set regex patterns that highlight matching rows (like conditional breakpoints)
- **Bookmarks**: Star/pin important log entries, view them in a sidebar, export as report
- **Error clustering**: Group repeated error patterns into "NullRef in SparkClient ×7" 
- Virtual scroll for performance

---

### View 3: DAG Studio

FLT executes DAGs (directed acyclic graphs) of SQL/PySpark transformations. This view shows:

**Top: Interactive DAG Graph**
- Nodes = SQL or PySpark transformations (rectangular boxes with name + type)
- Edges = dependencies between nodes (which must complete before which)
- During execution: nodes change color by status (pending → running → completed/failed/skipped)
- Click a node → see its logs, SQL code, metrics, errors

**Bottom: Execution Controls + Timeline**
- Run DAG / Cancel DAG / Refresh buttons
- Gantt chart showing per-node execution timing
- Execution history (last 10 runs with status, duration)
- Run comparison: diff two executions to spot regressions

---

### View 4: Spark Inspector

FLT talks to Spark via HTTP REST. This view is like Fiddler/Postman for Spark traffic:

**Left: Request List**
- Each Spark HTTP call: method (PUT/GET/DELETE), endpoint, status code, duration, retry count

**Right: Request Detail**
- Request: headers, SQL/PySpark code (syntax highlighted), session properties
- Response: status, body, error details
- Timing: waterfall visualization
- Retry chain: all attempts with delays between them

---

### View 5: API Playground

Test Fabric API calls directly from the UI (like Postman but pre-configured):
- Method selector, URL with auto-filled template variables (workspaceId, artifactId, etc.)
- Headers pre-populated with MWC token
- Body editor
- Response viewer with syntax highlighting
- Request history with replay
- cURL export
- Saved/bookmarked requests

---

### View 6: Environment

**Feature Flags**: Table of 50+ flags with toggle switches for local overrides
**Lock Monitor**: Show DAG execution lock state, force-unlock button (stuck locks are a common local dev issue)
**Orphaned Resources**: List of orphaned OneLake folders from failed runs, with cleanup buttons

---

### Command Palette (Ctrl+K)
Floating overlay, keyboard-navigable. Type to search across:
- Workspaces, Lakehouses, Tables
- Commands (Run DAG, Cancel, Restart Service)
- Log entries, Feature flags

---

### Token Inspector (drawer, not modal)
Slides in from the right when token countdown is clicked:
- Decoded JWT: header, payload claims, signature
- Expiry countdown with progress bar
- Scope list (what APIs this token can access)
- Refresh & Copy buttons

---

## Technical Constraints
- Single HTML file with inline CSS + JS (no React/Vue/Angular)
- Must work in Edge/Chrome
- Handles 10,000+ log entries with virtual scrolling
- Real-time WebSocket data streaming
- Dark theme preferred (devs use dark mode)

---

## Data Architecture

The UI gets data from:
1. **WebSocket** (`ws://localhost:5555/ws/logs`) — real-time batched log + telemetry stream (150ms batches)
2. **REST APIs** on the same server:
   - `GET /api/logs` — filtered logs
   - `GET /api/telemetry` — telemetry events
   - `GET /api/stats` — count summaries
   - `GET /api/executions` — execution history grouped by iteration
   - `GET /api/flt/config` — workspace/artifact/capacity IDs + MWC token
3. **Direct Fabric API calls** from the browser using the MWC token (for DAG operations, workspace browsing, etc.)

---

## Mock Data to Include

- 2 tenants, 3 workspaces, 4 lakehouses
- 10+ tables with names like: CustomerOrders_Gold, ProductInventory_Silver, SalesMetrics_Agg
- Table schemas with 5-8 columns each (Id, Name, Amount, CreatedDate, etc.)
- 15-20 log entries with mixed levels
- 6-node DAG: RefreshSource → TransformSales, TransformProducts → JoinSalesProducts → AggregateMetrics → UpdateGoldTable
- 5 Spark HTTP requests with mixed status codes
- 8 feature flags (FLTParallelNodeLimit20, FLTIRDeletesDisabled, etc.)
- 1 active lock on a lakehouse

---

## What Makes This Different

This is NOT a generic dashboard. It's an **operations cockpit for one specific service**. Every pixel should serve a purpose. The user spends 8 hours/day here — it needs to be:
- **Dense but readable** — lots of information, clear hierarchy
- **Fast** — instant tab switches, smooth scrolling, no lag
- **Keyboard-first** — Ctrl+K, number keys for tabs, arrow keys in trees/tables
- **Zero context switches** — everything a dev needs without opening Fabric portal or Kusto
