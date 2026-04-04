/**
 * SmartContextBar — Renders and updates the auto-detected execution context bar.
 * Appears automatically when a DAG execution OR any FLT API call is detected.
 */
class SmartContextBar {
  constructor(autoDetector) {
    this.autoDetector = autoDetector;
    this.element = document.getElementById('smart-context-bar');
    this.updateInterval = null;
    this.mode = null; // 'execution' | 'apicall'

    // Wire up auto-detector callbacks — iteration-based executions
    autoDetector.onExecutionDetected = (exec, id) => this.showExecution(exec, id);
    autoDetector.onExecutionUpdated = (exec, id) => this.updateExecution(exec, id);

    // Wire up auto-detector callbacks — RAID-based API calls
    autoDetector.onApiCallDetected = (call, id) => this.showApiCall(call, id);
    autoDetector.onApiCallUpdated = (call, id) => this.updateApiCall(call, id);
  }

  // === Iteration-based execution display ===

  showExecution = (exec, iterationId) => {
    if (!this.element) return;
    this.mode = 'execution';
    this.element.classList.add('active');
    this.updateExecution(exec, iterationId);
    if (this.updateInterval) clearInterval(this.updateInterval);
    this.updateInterval = setInterval(() => {
      const elapsed = this.autoDetector.getElapsedTime();
      const elapsedEl = this.element.querySelector('.elapsed');
      if (elapsedEl && elapsed) elapsedEl.textContent = elapsed + 's';
    }, 1000);
  }

  updateExecution = (exec, iterationId) => {
    if (!this.element) return;
    // Execution takes priority over API call
    this.mode = 'execution';
    const statusClass = (exec.status || 'unknown').toLowerCase();
    const completedTotal = exec.nodeCount || '?';
    const completed = exec.completedNodes || 0;
    const failed = exec.failedNodes || 0;
    const elapsed = this.autoDetector.getElapsedTime() || '—';
    const shortId = iterationId.substring(0, 8) + '…' + iterationId.substring(iterationId.length - 4);

    this.element.innerHTML = `
      <span class="ctx-type">🔄 Execution</span>
      <span class="dag-status ${statusClass}">● ${exec.status || 'Detected'}</span>
      <span class="dag-name">${exec.dagName || 'DAG Execution'}</span>
      <span class="node-progress">${completed}${failed ? '+' + failed + ' err' : ''} / ${completedTotal} nodes</span>
      <span class="elapsed">${elapsed}s</span>
      ${exec.endpoint ? '<span class="endpoint">' + exec.endpoint + '</span>' : ''}
      <span class="iter-id">${shortId}</span>
      <span class="dismiss" onclick="document.getElementById('smart-context-bar').classList.remove('active')">✕</span>
    `;
    this.element.classList.add('active');
  }

  // === RAID-based API call display ===

  showApiCall = (call, raidId) => {
    if (!this.element) return;
    // Don't override active execution context
    if (this.mode === 'execution') return;
    this.mode = 'apicall';
    this.element.classList.add('active');
    this.updateApiCall(call, raidId);
  }

  updateApiCall = (call, raidId) => {
    if (!this.element || this.mode === 'execution') return;
    const statusClass = (call.status || 'unknown').toLowerCase();
    const shortRaid = raidId.substring(0, 8) + '…';
    const duration = call.duration ? this._formatDuration(call.duration) : '—';
    const statusIcon = statusClass === 'succeeded' ? '✓' : statusClass === 'failed' ? '✗' : '●';

    this.element.innerHTML = `
      <span class="ctx-type">📡 API</span>
      <span class="dag-status ${statusClass}">${statusIcon} ${call.status}</span>
      <span class="dag-name">${call.endpointName}</span>
      <span class="elapsed">${duration}</span>
      ${call.resultCode && call.resultCode !== 'OK' ? '<span class="endpoint">' + call.resultCode + '</span>' : ''}
      <span class="iter-id" title="${raidId}">${shortRaid}</span>
      ${call.eventCount > 1 ? '<span class="node-progress">' + call.eventCount + ' events</span>' : ''}
      <span class="dismiss" onclick="document.getElementById('smart-context-bar').classList.remove('active')">✕</span>
    `;
    this.element.classList.add('active');
  }

  _formatDuration = (ms) => {
    if (ms < 1000) return Math.round(ms) + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    return Math.floor(ms / 60000) + 'm ' + Math.round((ms % 60000) / 1000) + 's';
  }

  hide = () => {
    if (this.element) this.element.classList.remove('active');
    if (this.updateInterval) clearInterval(this.updateInterval);
    this.mode = null;
  }
}
