/**
 * EDOG Real-Time Log Viewer - State Management
 */

// ===== STATE MANAGEMENT =====

class LogViewerState {
  constructor() {
    this.logs = [];           // All received log entries (max 5000)
    this.telemetry = [];      // All received telemetry events (max 2000)
    this.filteredLogs = [];   // After search/level/correlation filter
    this.activeLevels = new Set(['Message', 'Warning', 'Error']);
    this.searchText = '';
    this.correlationFilter = null;  // rootActivityId to filter by
    this.excludedComponents = new Set();  // Components to exclude
    this.activePreset = 'flt';  // Default: filter out noise components
    this.autoScroll = true;
    this.paused = false;
    this.timeRangeSeconds = 0;  // 0 = all time, >0 = last N seconds
    this.stats = { 
      totalLogs: 0, verbose: 0, message: 0, warning: 0, error: 0, 
      totalEvents: 0, succeeded: 0, failed: 0 
    };
    this.pendingLogs = [];    // Buffer for batched rendering
    this.pendingTelemetry = [];

    // W0.1 — Tab state
    this.activeTab = localStorage.getItem('edog-active-tab') || 'logs';

    // W0.2 — Endpoint filter
    this.endpointFilter = '';        // Currently selected endpoint
    this.knownEndpoints = new Set(); // Auto-discovered endpoints

    // W0.3 — RAID / IterationId filter
    this.raidFilter = '';             // Active RAID/IterationId filter
    this.knownIterationIds = new Map(); // id → { id, firstSeen, dagName, status, logCount, ssrCount }
    this.recentExecutions = [];       // Last 10 unique IterationIds (ordered)
  }
  
  addLog = (entry) => {
    this.logs.push(entry);
    this.pendingLogs.push(entry);
    
    // Cap logs array at 5000
    if (this.logs.length > 5000) {
      this.logs.shift();
    }
    
    // Update stats
    this.stats.totalLogs++;
    const level = entry.level?.toLowerCase();
    if (level && this.stats[level] !== undefined) {
      this.stats[level]++;
    }
  }
  
  addTelemetry = (event) => {
    this.telemetry.push(event);
    this.pendingTelemetry.push(event);
    
    // Cap telemetry array at 2000
    if (this.telemetry.length > 2000) {
      this.telemetry.shift();
    }
    
    // Update stats
    this.stats.totalEvents++;
    const status = event.activityStatus?.toLowerCase();
    if (status === 'succeeded') this.stats.succeeded++;
    else if (status === 'failed') this.stats.failed++;
  }
}
