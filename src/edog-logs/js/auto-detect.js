/**
 * AutoDetector — Automatically detects active DAG executions, IterationIds, 
 * RAIDs, and API endpoints from the incoming log stream.
 * 
 * The tool does the thinking — no manual filter entry needed.
 */
class AutoDetector {
  constructor(state) {
    this.state = state;
    this.detectedExecutions = new Map(); // iterationId -> { dagName, status, startTime, nodeCount, completedNodes, failedNodes, skippedNodes, errors, endpoint, raids }
    this.activeExecutionId = null;
    this.onExecutionDetected = null; // callback
    this.onExecutionUpdated = null;  // callback
    this.onErrorDetected = null;     // callback
  }

  /**
   * Process an incoming log entry — extract execution context automatically.
   */
  processLog = (entry) => {
    const msg = entry.message || '';
    const iterationId = entry.iterationId || this.extractIterationId(msg);
    
    if (iterationId) {
      this.ensureExecution(iterationId);
      const exec = this.detectedExecutions.get(iterationId);
      
      // Track RAID
      if (entry.rootActivityId && entry.rootActivityId !== '00000000-0000-0000-0000-000000000000') {
        exec.raids.add(entry.rootActivityId);
      }

      // Detect DAG name
      if (msg.includes('Creating Dag from Catalog') || msg.includes('Creating Dag')) {
        const nameMatch = msg.match(/Creating Dag.*?['""]([^'""]+)['""]|Dag(?:Name)?[=: ]+(\S+)/i);
        if (nameMatch) exec.dagName = nameMatch[1] || nameMatch[2];
      }

      // Detect DAG status transitions
      if (msg.includes('[DAG STATUS]') || msg.includes('[DAG_STATUS]')) {
        if (msg.includes('Starting') || msg.includes('started')) {
          exec.status = 'Running';
          exec.startTime = exec.startTime || entry.timestamp;
        }
        if (msg.includes('Completed') || msg.includes('completed') || msg.includes('successfully')) {
          exec.status = msg.includes('error') || msg.includes('fault') ? 'Failed' : 'Completed';
          exec.endTime = entry.timestamp;
        }
        if (msg.includes('failed') || msg.includes('Failed')) {
          exec.status = 'Failed';
          exec.endTime = entry.timestamp;
        }
        if (msg.includes('cancelled') || msg.includes('Cancelled')) {
          exec.status = 'Cancelled';
          exec.endTime = entry.timestamp;
        }
      }

      // Detect node counts
      const nodeCountMatch = msg.match(/(\d+)\s*nodes?\s*ready|DagNodesCount[=: ]+(\d+)/i);
      if (nodeCountMatch) exec.nodeCount = parseInt(nodeCountMatch[1] || nodeCountMatch[2]);

      // Detect parallel limit
      const parallelMatch = msg.match(/ParallelNodeLimit[=: ]+(\d+)/i);
      if (parallelMatch) exec.parallelLimit = parseInt(parallelMatch[1]);

      // Detect refresh mode
      const refreshMatch = msg.match(/RefreshMode[=: ]+(\w+)/i);
      if (refreshMatch) exec.refreshMode = refreshMatch[1];

      // Detect node execution events
      if (msg.includes('Executed node') || msg.includes('executed node')) {
        const nodeMatch = msg.match(/[Ee]xecuted node\s+['""]?(\w+)['""]?\s+.*?status\s+(\w+)/);
        if (nodeMatch) {
          const [, nodeName, status] = nodeMatch;
          if (!exec.nodes) exec.nodes = new Map();
          exec.nodes.set(nodeName, { status, timestamp: entry.timestamp });
          if (status === 'Completed') exec.completedNodes++;
          else if (status === 'Failed') exec.failedNodes++;
        }
      }
      if (msg.includes('Executing node') && !msg.includes('Executed')) {
        const nodeMatch = msg.match(/[Ee]xecuting node\s+['""]?(\w+)['""]?/);
        if (nodeMatch) {
          if (!exec.nodes) exec.nodes = new Map();
          exec.nodes.set(nodeMatch[1], { status: 'Running', timestamp: entry.timestamp });
        }
      }

      // Detect skipped nodes
      if (msg.includes('[DAG_FAULTED_NODES]') || msg.includes('skipped')) {
        const skipMatch = msg.match(/['""](\w+)['""].*?skipped|skipped.*?['""](\w+)['""]|faulted.*?['""](\w+)['""]|['""](\w+)['""].*?faulted/i);
        if (skipMatch) {
          const nodeName = skipMatch[1] || skipMatch[2] || skipMatch[3] || skipMatch[4];
          if (!exec.nodes) exec.nodes = new Map();
          exec.nodes.set(nodeName, { status: 'Skipped', timestamp: entry.timestamp });
          exec.skippedNodes++;
        }
      }

      // Detect errors
      if ((entry.level || '').toLowerCase() === 'error') {
        const errorCodeMatch = msg.match(/\b(MLV_\w+|FLT_\w+|SPARK_\w+)\b/);
        const errorCode = errorCodeMatch ? errorCodeMatch[1] : 'UNKNOWN_ERROR';
        exec.errors.push({ code: errorCode, message: msg.substring(0, 200), timestamp: entry.timestamp, node: this.inferNodeFromContext(msg) });
        exec.failedNodes = Math.max(exec.failedNodes, exec.errors.length > 0 ? 1 : 0);
        if (this.onErrorDetected) this.onErrorDetected(exec, exec.errors[exec.errors.length - 1]);
      }

      // Auto-set as active execution (most recent one wins)
      if (!this.activeExecutionId || this.activeExecutionId === iterationId) {
        this.activeExecutionId = iterationId;
        if (this.onExecutionUpdated) this.onExecutionUpdated(exec, iterationId);
      } else {
        // New execution detected — switch to it
        this.activeExecutionId = iterationId;
        if (this.onExecutionDetected) this.onExecutionDetected(exec, iterationId);
      }
    }

    // Detect API endpoint from component/CodeMarkerName
    if (entry.codeMarkerName) {
      const epMatch = entry.codeMarkerName.match(/-([A-Za-z]+)$/);
      if (epMatch && iterationId) {
        const exec = this.detectedExecutions.get(iterationId);
        if (exec) exec.endpoint = epMatch[1];
      }
    }
  }

  /**
   * Process an incoming SSR telemetry event.
   */
  processTelemetry = (event) => {
    const iterationId = event.iterationId || (event.attributes && event.attributes.IterationId);
    if (iterationId) {
      this.ensureExecution(iterationId);
      const exec = this.detectedExecutions.get(iterationId);

      // Extract node info from NodeExecution activities
      if (event.activityName === 'NodeExecution' && event.attributes) {
        const nodeName = event.attributes.NodeName;
        if (nodeName) {
          if (!exec.nodes) exec.nodes = new Map();
          exec.nodes.set(nodeName, {
            status: event.activityStatus || 'Unknown',
            duration: event.durationMs,
            errorCode: event.attributes.ErrorCode,
            timestamp: event.timestamp
          });
          if (event.activityStatus === 'Succeeded') exec.completedNodes++;
          else if (event.activityStatus === 'Failed') exec.failedNodes++;
        }
      }

      // Extract DAG-level info from RunDag activity
      if (event.activityName === 'RunDag' || event.activityName === 'RunDAG') {
        if (event.attributes) {
          if (event.attributes.DagNodesCount) exec.nodeCount = parseInt(event.attributes.DagNodesCount);
          if (event.attributes.ParallelNodeLimit) exec.parallelLimit = parseInt(event.attributes.ParallelNodeLimit);
        }
        exec.duration = event.durationMs;
        if (event.activityStatus === 'Succeeded') exec.status = 'Completed';
        else if (event.activityStatus === 'Failed') exec.status = 'Failed';
      }

      if (this.activeExecutionId === iterationId && this.onExecutionUpdated) {
        this.onExecutionUpdated(exec, iterationId);
      }
    }
  }

  ensureExecution = (iterationId) => {
    if (!this.detectedExecutions.has(iterationId)) {
      this.detectedExecutions.set(iterationId, {
        dagName: null, status: 'Unknown', startTime: null, endTime: null,
        nodeCount: 0, completedNodes: 0, failedNodes: 0, skippedNodes: 0,
        parallelLimit: null, refreshMode: null, duration: null,
        errors: [], raids: new Set(), endpoint: null, nodes: new Map()
      });
    }
  }

  extractIterationId = (msg) => {
    const m = msg.match(/(?:\[IterationId\s+|\bIterationId[=: ]+)([0-9a-fA-F-]{36})\b/);
    return m ? m[1] : null;
  }

  inferNodeFromContext = (msg) => {
    const m = msg.match(/[Nn]ode\s+['""]?(\w+)['""]?/);
    return m ? m[1] : null;
  }

  getActiveExecution = () => {
    if (!this.activeExecutionId) return null;
    return { id: this.activeExecutionId, ...this.detectedExecutions.get(this.activeExecutionId) };
  }

  getElapsedTime = () => {
    const exec = this.getActiveExecution();
    if (!exec || !exec.startTime) return null;
    const end = exec.endTime ? new Date(exec.endTime) : new Date();
    const start = new Date(exec.startTime);
    return ((end - start) / 1000).toFixed(1);
  }
}
