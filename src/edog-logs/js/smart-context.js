/**
 * SmartContextBar — Renders and updates the auto-detected execution context bar.
 * Appears automatically when a DAG execution is detected. No user action needed.
 */
class SmartContextBar {
  constructor(autoDetector) {
    this.autoDetector = autoDetector;
    this.element = document.getElementById('smart-context-bar');
    this.updateInterval = null;

    // Wire up auto-detector callbacks
    autoDetector.onExecutionDetected = (exec, id) => this.show(exec, id);
    autoDetector.onExecutionUpdated = (exec, id) => this.update(exec, id);
  }

  show = (exec, iterationId) => {
    if (!this.element) return;
    this.element.classList.add('active');
    this.update(exec, iterationId);
    // Start elapsed time ticker
    if (this.updateInterval) clearInterval(this.updateInterval);
    this.updateInterval = setInterval(() => {
      const elapsed = this.autoDetector.getElapsedTime();
      const elapsedEl = this.element.querySelector('.elapsed');
      if (elapsedEl && elapsed) elapsedEl.textContent = elapsed + 's';
    }, 1000);
  }

  update = (exec, iterationId) => {
    if (!this.element) return;
    const statusClass = (exec.status || 'unknown').toLowerCase();
    const completedTotal = exec.nodeCount || '?';
    const completed = exec.completedNodes || 0;
    const failed = exec.failedNodes || 0;
    const elapsed = this.autoDetector.getElapsedTime() || '—';
    const shortId = iterationId.substring(0, 8) + '…' + iterationId.substring(iterationId.length - 4);

    this.element.innerHTML = `
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

  hide = () => {
    if (this.element) this.element.classList.remove('active');
    if (this.updateInterval) clearInterval(this.updateInterval);
  }
}
