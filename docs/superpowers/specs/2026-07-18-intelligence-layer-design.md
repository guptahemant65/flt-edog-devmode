# EDOG Intelligence Layer — Feature Design Spec

**Date:** 2026-07-18  
**Scope:** Seven AI-powered features for FabricLiveTable DevMode  
**Constraint:** Offline-first, no ML models, JavaScript heuristics + optional LLM enhancement

---

## Architecture Overview

All intelligence features share a common pipeline:

```
WebSocket batch (150ms) → AutoDetector (main thread, per-log)
  → Fingerprint + Breakpoint check (main thread, O(1)/log)
    → Post to Worker (batched every 500ms)
      → Clustering, Anomaly Stats, Prediction (Worker thread)
        → IndexedDB persistence (on execution complete)
          → UI updates via postMessage callbacks
```

**New module:** `intelligence-worker.js` — a shared Web Worker that owns all compute-intensive operations (clustering aggregation, statistical baselines, prediction engine, IndexedDB I/O).

---

## Feature 1: Smart Error Diagnosis

### Problem
When a DAG node fails, developers must manually trace 200+ log lines to understand what happened, which node was the root cause vs cascade, and what to do.

### Algorithm: Cascade Detection

```javascript
buildCausalChain(errors[], dagTopology, nodeStates):
  1. Sort errors by timestamp ascending
  2. For each error E:
     a. Get failed node N from E.node
     b. Look up N's parent dependencies in dagTopology
     c. If ANY parent has status=Failed with EARLIER timestamp → CASCADE
     d. Else → ROOT_CAUSE
  3. For each ROOT_CAUSE, BFS downstream in DAG to find all Skipped/Faulted
  4. Return: { rootCauses[], cascades[], impactGraph }
```

### Error Registry

New file `error-knowledge.js` maps 20+ known error codes to:
- Category (User vs System)
- Plain-text summary
- Fix suggestion
- Documentation link

### Outputs
- Causal chain: "Node X failed → Node Y skipped → Node Z skipped"
- Root cause identification with fix suggestion
- Impact count: "1 root failure → 3 downstream nodes skipped"
- (With LLM) Plain-English explanation with SQL context

### Progressive Enhancement
- **First run:** Error grouping by code, raw messages
- **5-10 runs:** Full cascade detection (DAG loaded), fix suggestions from ErrorRegistry
- **50+ runs:** Historical error frequency ("This error occurred 8 times in last 20 runs")
- **+ LLM:** Contextual explanation using actual SQL and schema info

---

## Feature 2: Anomaly Detection on Execution Metrics

### Problem
Current hardcoded thresholds (60s slow node, 30s poll gap) don't adapt to the specific DAG. A node that normally takes 40s shouldn't trigger at 60s, while one that normally takes 0.5s should alarm at 5s.

### Algorithm: Modified Z-Score with EMA Baseline

```javascript
detectAnomaly(current, history, { alpha = 0.3, threshold = 3.0 }):
  1. Compute EMA (exponential moving average) — adapts faster than mean
  2. Compute MAD (median absolute deviation) — robust to outliers
  3. Modified Z-score = 0.6745 * (current - ema) / mad
  4. Classify:
     - |z| > 6.0 → CRITICAL
     - |z| > 3.0 → WARNING  
     - |z| > 1.8 → INFO
```

### Detection Rules (5 types)
1. **Duration Anomaly** — Per-node + total DAG duration vs EMA baseline
2. **Novel Failure** — Node that has never failed in recorded history
3. **Consecutive Failures** — Same node failing repeatedly across runs (alert at 2, critical at 5)
4. **Degradation Trend** — Linear regression on last 10 durations; flag if slope > 20% of mean
5. **Environment Health** — Token expiry risk, capacity throttling, Spark instability

### Progressive Enhancement
- **First run:** Hardcoded thresholds (existing behavior)
- **5-10 runs:** EMA baselines, Z-score comparisons, novel failure detection
- **50+ runs:** Full statistical power, trend regression, p95/p99 thresholds

---

## Feature 3: Log Pattern Clustering

### Problem
Developers scan thousands of log lines looking for meaningful signals. Most logs are noise — repeated status messages, polling updates, routine operations.

### Algorithm: Template-Based Fingerprinting

```javascript
normalizeToTemplate(msg):
  1. Replace GUIDs → {GUID}
  2. Replace timestamps → {TIMESTAMP}
  3. Replace numbers (3+ digits) → {N}
  4. Replace durations → {DURATION}
  5. Replace IP addresses → {IP}
  6. Replace long quoted strings → {STRING}
  7. Replace hex sequences → {HEX}
  8. Collapse whitespace

fingerprint = FNV-1a hash of normalized template (32-bit)
```

### Ranking Formula
```
score = severityWeight[maxLevel] × log₂(count + 1) × (0.3 + 0.7 × recencyDecay)
```
Where recencyDecay = e^(-(now - lastSeen) / 60000)

### Novelty Detection
A cluster is "novel" if its fingerprint doesn't exist in IndexedDB pattern history from any previous session. Flagged with 🆕 badge.

### Outputs
- Cluster list ranked by composite score
- Template pattern with variable parts highlighted
- Click cluster → filter log view to matching entries
- Novel patterns surfaced prominently

---

## Feature 4: Intelligent Breakpoints

### Problem
Regex breakpoints are too crude. Developers need semantic conditions: "pause when something unexpected happens."

### Breakpoint Types

| Type | Condition | Evaluation | Cost |
|------|-----------|------------|------|
| First Error | First error in {component} | Main thread, O(1) | Cheap |
| Metric Threshold | Node duration > {N}ms | Main thread on telemetry | Cheap |
| Novel Pattern | Never-before-seen log pattern | Worker, hash lookup | Cheap |
| Anomalous Duration | Node 3σ+ slower than baseline | Worker, Z-score | Cheap |
| Regex | Message matches /pattern/ | Main thread, regex test | Varies |

### Auto-Suggested Breakpoints
After each failure, suggest breakpoints for the next run based on:
- Root cause error code → watch for recurrence
- Anomalous node duration → alert at p95 threshold
- Consecutive failures → watch specific node
- Novel error patterns → alert on error family

---

## Feature 5: Execution Prediction

### Problem
Before running a DAG, developers have no visibility into expected behavior.

### Algorithms

**Duration Prediction:**
1. Get per-node median durations from history
2. Walk DAG topology to find critical path
3. Return: estimated total time + [p25, p75] range

**Success Prediction:**
1. Base rate = success count / total in last 20 runs
2. Environmental adjustments (multiplicative):
   - Token expires in <5 min → ×0.7
   - Recent throttles → ×0.8
   - Last run failed → ×0.9
   - 5+ consecutive successes → ×1.05
3. Risk nodes = nodes with >20% failure rate in recent history

### Outputs
- Estimated duration with confidence range
- Success probability (High/Medium/Low)
- Per-node risk badges
- Environment health check

---

## Feature 6: Smart Log Search

### Problem
Exact text search misses semantic intent. "Show me auth errors" doesn't match "token expired" or "401 Unauthorized."

### Three Search Modes

**1. Semantic Aliases** — Local thesaurus mapping intent to patterns:
```javascript
SEARCH_ALIASES = {
  'auth': ['token', '401', '403', 'bearer', 'refresh', 'expired', 'unauthorized'],
  'timeout': ['timeout', 'timed out', 'deadline', 'cancelled'],
  'schema': ['schema', 'column', 'mismatch', 'MLV_SCHEMA', 'type change'],
  'slow': ['slow', 'duration', 'elapsed', 'latency', 'long running'],
  'memory': ['OOM', 'out of memory', 'heap', 'GC pressure'],
  // ... 20+ semantic groups
};
```

**2. Temporal Queries:**
- `before:error` — 5s window before last error
- `around:FactSales` — ±3s around node events
- `during:running` — Only logs while DAG was Running

**3. Correlation Queries:**
- `@node:FactSales` — Everything related to this node
- `@raid:{id}` — All entries sharing this RootActivityId
- `@error` — Auto-finds error's RAID and shows full context

---

## Feature 7: Root Cause Graph

### Problem
Failures involve multiple correlated events across data streams. Manually correlating IterationId, CorrelationId, RootActivityId, and timestamps is tedious.

### Algorithm

```javascript
buildRootCauseGraph(error, executionState):
  1. ERROR NODE — the failure event
  2. CONTRIBUTING LOGS — same component, ±5s window, same iterationId
  3. RELATED TELEMETRY — same RAID or iterationId, before error timestamp
  4. UPSTREAM DAG DEPENDENCIES — parent nodes from DAG topology
  Link all via edges with time deltas and relationship labels
```

### Visualization
- Top-down tree layout (Canvas-based, ~200 lines custom renderer)
- Color-coded nodes: Error (red), Warning (amber), Telemetry (cyan), DAG Node (blue)
- SVG edges with time delta labels
- Click-to-expand for full details, "View in Logs" to jump to timestamp

---

## Data Pipeline

| Stage | Thread | Frequency | Operation |
|-------|--------|-----------|-----------|
| 1. Ingest | Main | 150ms batches | WebSocket → state.addLog() |
| 2. Detect | Main | Per log | autoDetector.processLog() |
| 3. Fingerprint | Main | Per log | normalize() → fnv1a() → post to Worker |
| 4. Breakpoint | Main | Per log | breakpointEngine.evaluate() |
| 5. Aggregate | Worker | 500ms debounced | Update clusters, anomaly scores, search index |
| 6. Persist | Worker | On exec complete | Write to IndexedDB |
| 7. Present | Main | On Worker message | Update UI overlays |

---

## Storage Strategy

### Three-Tier Architecture

| Tier | Technology | Data | Size | Retention |
|------|-----------|------|------|-----------|
| Hot | RingBuffer (memory) | Current session logs/telemetry | ~8 MB | Session only |
| Warm | IndexedDB | Execution summaries, pattern DB, baselines | ~50 MB | 200 runs or 30 days |
| Cold | localStorage | UI prefs, breakpoint configs, search history | ~100 KB | Indefinite |

### IndexedDB Schema ("edog-intelligence")

**executions** — per-DAG-run records with node breakdown, errors, environment state  
**patterns** — log pattern fingerprints (hash → template, first/last seen, count)  
**baselines** — per-node statistical baselines (EMA, MAD, recent durations, failure rate)

### Retention: Keep 200 runs or 30 days. Pattern fingerprints evicted after 90 days unused. Hard cap 50 MB.

---

## Performance Budget

At 10,000 logs/min (167/sec), per-log intelligence overhead on main thread: **~0.07ms**.  
Per batch (25 logs): **~1.75ms** — well under the 16ms frame budget.

All heavy work (statistics, clustering aggregation, prediction) runs in the Worker.

---

## New Files

| File | Est. Size | Purpose |
|------|-----------|---------|
| `js/intelligence-worker.js` | ~3 KB | Web Worker for compute-intensive operations |
| `js/error-knowledge.js` | ~2 KB | Error Registry: codes → fixes |
| `js/breakpoint-engine.js` | ~2 KB | Breakpoint evaluation + auto-suggest |
| `js/smart-search.js` | ~2 KB | Query parser, semantic aliases, temporal queries |
| `js/history-store.js` | ~2 KB | IndexedDB wrapper |
| `js/root-cause-graph.js` | ~3 KB | Graph construction + Canvas renderer |
| `css/intelligence.css` | ~1 KB | Styles for all intelligence UI surfaces |

## Modified Files

- `anomaly.js` — Replace hardcoded thresholds with Worker-based adaptive detection
- `error-intel.js` — Wire to ErrorRegistry + cascade analysis
- `auto-detect.js` — Add fingerprinting, Worker posting, history persistence
- `filters.js` — Integrate smart-search.js query parsing
- `main.js` — Initialize Worker, BreakpointEngine, HistoryStore
- `control-panel.js` — Add prediction card to pre-run state
- `index.html` — Add new panel containers

---

## Novel Ideas (Future)

1. **Execution Replay** — Record full event stream, scrub timeline like a video (~2 MB/exec)
2. **"What If" Simulator** — Modify node assumptions, see projected DAG outcome
3. **Cross-Execution Diff** — Structured diff between two runs (like git diff for DAGs)
4. **Failure DNA Fingerprinting** — Hash failure signatures, auto-recognize recurring issues
5. **Proactive Alerts** — Detect leading indicators mid-execution, show live confidence meter
6. **Developer Intent Detection** — Track post-failure behavior, auto-suggest resolution patterns
