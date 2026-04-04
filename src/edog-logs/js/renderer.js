/**
 * EDOG Real-Time Log Viewer - DOM Renderer
 */

// ===== RENDERER =====

class Renderer {
  constructor(state) {
    this.state = state;
    this.renderScheduled = false;
    this.maxDomRows = 300; // Max log rows in DOM
  }
  
  scheduleRender = () => {
    if (!this.renderScheduled) {
      this.renderScheduled = true;
      requestAnimationFrame(() => this.flush());
    }
  }
  
  flush = () => {
    this.renderScheduled = false;
    
    // Process pending logs
    if (this.state.pendingLogs.length > 0) {
      this.renderPendingLogs();
      this.state.pendingLogs = [];
    }
    
    // Process pending telemetry
    if (this.state.pendingTelemetry.length > 0) {
      this.renderPendingTelemetry();
      this.state.pendingTelemetry = [];
    }
    
    // Update stats
    this.updateStats();
  }
  
  renderPendingLogs = () => {
    const container = document.getElementById('logs-container');
    if (!container) return;
    
    const wasAtBottom = this.isScrolledToBottom(container);
    
    // Filter pending logs first
    const filteredPendingLogs = this.state.pendingLogs.filter(entry => 
      !this.state.paused && this.passesFilter(entry)
    );
    
    // Add new log rows using DocumentFragment for better performance
    if (filteredPendingLogs.length > 0) {
      const fragment = document.createDocumentFragment();
      filteredPendingLogs.forEach(entry => {
        const row = this.createLogRow(entry);
        fragment.appendChild(row);
      });
      container.appendChild(fragment);
      
      // Trigger animations for new rows
      const newRows = Array.from(container.children).slice(-filteredPendingLogs.length);
      requestAnimationFrame(() => {
        newRows.forEach(row => row.classList.add('fade-in-complete'));
      });
    }
    
    // Cap DOM rows with scroll position preservation
    this.capDomRows(container);
    
    // Update status counter
    this.updateLogsStatus();
    
    // Auto-scroll if was at bottom and auto-scroll enabled
    if (this.state.autoScroll && wasAtBottom) {
      this.scrollToBottom(container);
    }
  }
  
  renderPendingTelemetry = () => {
    const container = document.getElementById('telemetry-container');
    if (!container) return;
    
    this.state.pendingTelemetry.forEach(event => {
      if (!this.state.paused) {
        const card = this.createTelemetryCard(event);
        container.insertBefore(card, container.firstChild); // Add to top
        
        // Trigger animation
        requestAnimationFrame(() => card.classList.add('fade-in-complete'));
      }
    });
    
    // Cap telemetry cards (keep latest 100)
    while (container.children.length > 100) {
      container.removeChild(container.lastChild);
    }
  }
  
  createLogRow = (entry) => {
    const row = document.createElement('div');
    row.className = 'log-row fade-in';
    row.dataset.rootActivityId = entry.rootActivityId || '';
    
    const level = entry.level || 'Message';
    if (level === 'Error') row.classList.add('error-row');
    const levelLetter = this.getLevelLetter(level);
    const time = this.formatTime(entry.timestamp);
    const component = entry.component || 'Unknown';
    const message = this.truncateMessage(entry.message || '', 200);
    
    row.innerHTML = `
      <span class="log-time">${time}</span>
      <span class="level-badge ${level.toLowerCase()}">${levelLetter}</span>
      <span class="log-component" title="Click to exclude this component">${this.escapeHtml(component)}</span>
      <span class="log-message">${this.escapeHtml(message)}</span>
    `;
    
    // Click handler for detail panel
    row.addEventListener('click', () => {
      if (window.edogViewer && window.edogViewer.detail) {
        window.edogViewer.detail.show(entry, 'log');
      }
    });
    
    // Click handler for component pill exclusion
    const componentSpan = row.querySelector('.log-component');
    if (componentSpan) {
      componentSpan.addEventListener('click', (e) => {
        e.stopPropagation();
        if (window.edogViewer && window.edogViewer.filter) {
          window.edogViewer.filter.excludeComponent(component);
        }
      });
    }
    
    return row;
  }
  
  createTelemetryCard = (event) => {
    const card = document.createElement('div');
    card.className = `telemetry-card fade-in ${(event.activityStatus || 'unknown').toLowerCase()}`;
    
    const status = event.activityStatus || 'Unknown';
    const icon = this.getStatusIcon(status);
    const duration = this.formatDuration(event.durationMs);
    const time = this.formatTime(event.timestamp);
    const resultCode = event.resultCode || 'OK';
    const correlationId = event.correlationId || '';
    
    let resultHtml = '';
    if (resultCode !== 'OK' && resultCode) {
      resultHtml = `<div class="telem-result">${this.escapeHtml(resultCode)}</div>`;
    }
    
    let correlationHtml = '';
    if (correlationId) {
      const shortCorr = correlationId.substring(0, 8);
      correlationHtml = `<div class="telem-correlation" data-correlation="${this.escapeHtml(correlationId)}" title="Filter by ${this.escapeHtml(correlationId)}">${this.escapeHtml(shortCorr)}</div>`;
    }
    
    let attributesHtml = '';
    if (event.attributes) {
      const attrs = [];
      if (event.attributes.WorkspaceId) attrs.push(`<span class="attr-pill">WS: ${this.escapeHtml(event.attributes.WorkspaceId.substring(0, 6))}</span>`);
      if (event.attributes.ArtifactId) attrs.push(`<span class="attr-pill">Art: ${this.escapeHtml(event.attributes.ArtifactId.substring(0, 6))}</span>`);
      if (event.attributes.IterationId) attrs.push(`<span class="attr-pill">Iter: ${this.escapeHtml(event.attributes.IterationId.substring(0, 6))}</span>`);
      if (attrs.length > 0) {
        attributesHtml = `<div class="telem-attrs">${attrs.join('')}</div>`;
      }
    }
    
    card.innerHTML = `
      <div class="telem-header">
        <span class="telem-activity">${this.escapeHtml(event.activityName || 'Unknown')}</span>
        <span class="status-badge ${status.toLowerCase()}">${icon} ${status}</span>
      </div>
      <div class="telem-meta">
        <span class="telem-duration">${duration}</span>
        <span class="telem-time">${time}</span>
      </div>
      ${resultHtml}
      ${correlationHtml}
      ${attributesHtml}
    `;
    
    // Click handler for detail panel
    card.addEventListener('click', (e) => {
      // Handle correlation click
      if (e.target.classList.contains('telem-correlation')) {
        e.stopPropagation();
        const corrId = e.target.dataset.correlation;
        if (corrId && window.edogViewer && window.edogViewer.filter) {
          window.edogViewer.filter.setCorrelationFilter(corrId);
        }
        return;
      }
      
      if (window.edogViewer && window.edogViewer.detail) {
        window.edogViewer.detail.show(event, 'telemetry');
      }
    });
    
    return card;
  }
  
  formatDuration = (ms) => {
    if (ms < 1000) {
      return `${Math.round(ms)}ms`;
    } else if (ms < 60000) {
      return `${(ms / 1000).toFixed(1)}s`;
    } else {
      const minutes = Math.floor(ms / 60000);
      const seconds = Math.round((ms % 60000) / 1000);
      return `${minutes}m ${seconds}s`;
    }
  }
  
  formatTime = (isoString) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString('en-US', { 
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit' 
      }) + '.' + String(date.getMilliseconds()).padStart(3, '0');
    } catch {
      return '00:00:00.000';
    }
  }
  
  getLevelLetter = (level) => {
    const mapping = {
      'verbose': 'V',
      'message': 'I', 
      'warning': 'W',
      'error': 'E'
    };
    return mapping[level.toLowerCase()] || 'I';
  }
  
  getStatusIcon = (status) => {
    const mapping = {
      'succeeded': '✓',
      'failed': '✗',
      'cancelled': '◌',
      'pending': '⋯'
    };
    return mapping[status.toLowerCase()] || '?';
  }
  
  truncateMessage = (message, maxLength) => {
    if (message.length <= maxLength) return message;
    return message.substring(0, maxLength) + '...';
  }
  
  escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  updateLogsStatus = () => {
    const container = document.getElementById('logs-container');
    const visibleCountEl = document.getElementById('visible-count');
    const totalCountEl = document.getElementById('total-count');
    
    if (container && visibleCountEl && totalCountEl) {
      // Count visible rows (excluding empty state)
      const visibleRows = Array.from(container.children).filter(child => 
        !child.id || child.id !== 'empty-state'
      ).length;
      
      visibleCountEl.textContent = visibleRows;
      totalCountEl.textContent = this.state.logs.length;
    }
  }
  
  capDomRows = (container) => {
    const maxRows = this.maxDomRows;
    const currentCount = container.children.length;
    
    if (currentCount > maxRows + 50) {
      // Preserve scroll position
      const scrollTop = container.scrollTop;
      const scrollHeight = container.scrollHeight;
      
      // Remove 50 rows at once for better performance
      const toRemove = Math.min(50, currentCount - maxRows);
      let removedHeight = 0;
      
      for (let i = 0; i < toRemove; i++) {
        const firstChild = container.firstChild;
        if (firstChild) {
          removedHeight += firstChild.offsetHeight;
          container.removeChild(firstChild);
        }
      }
      
      // Adjust scroll position to prevent jumping
      const newScrollHeight = container.scrollHeight;
      const heightDiff = scrollHeight - newScrollHeight;
      container.scrollTop = Math.max(0, scrollTop - heightDiff);
    }
  }
  
  isScrolledToBottom = (container) => {
    return container.scrollTop + container.clientHeight >= container.scrollHeight - 10;
  }
  
  scrollToBottom = (container) => {
    container.scrollTop = container.scrollHeight;
  }
  
  passesFilter = (entry) => {
    // Level filter
    if (!this.state.activeLevels.has(entry.level)) return false;
    
    // Correlation filter
    if (this.state.correlationFilter && entry.rootActivityId !== this.state.correlationFilter) {
      return false;
    }
    
    // Component filter
    const component = entry.component || 'Unknown';
    if (this.state.excludedComponents.has(component)) {
      return false;
    }
    
    // Time range filter
    if (this.state.timeRangeSeconds > 0) {
      const cutoff = new Date(Date.now() - this.state.timeRangeSeconds * 1000);
      const logTime = new Date(entry.timestamp);
      if (logTime < cutoff) return false;
    }
    
    // Endpoint filter (W0.2)
    if (this.state.endpointFilter) {
      const comp = entry.component || '';
      const match = comp.match(/-([A-Za-z]+)$/);
      const endpoint = match ? match[1] : '';
      if (endpoint.toLowerCase() !== this.state.endpointFilter.toLowerCase()) return false;
    }
    
    // RAID / IterationId filter (W0.3)
    if (this.state.raidFilter) {
      const raidLower = this.state.raidFilter.toLowerCase();
      const iterationId = (entry.iterationId || '').toLowerCase();
      const message = (entry.message || '').toLowerCase();
      const rootId = (entry.rootActivityId || '').toLowerCase();
      if (!iterationId.includes(raidLower) && !message.includes(raidLower) && !rootId.includes(raidLower)) {
        return false;
      }
    }
    
    // Text search
    if (this.state.searchText) {
      const searchLower = this.state.searchText.toLowerCase();
      const searchableText = [
        entry.message || '',
        entry.component || '',
        entry.rootActivityId || '',
        JSON.stringify(entry.customData || {})
      ].join(' ').toLowerCase();
      
      if (!searchableText.includes(searchLower)) return false;
    }
    
    return true;
  }
  
  updateStats = () => {
    const elements = {
      'stat-logs': this.state.stats.totalLogs,
      'stat-ssr': this.state.stats.totalEvents,
      'stat-errors': this.state.stats.error
    };
    
    Object.entries(elements).forEach(([id, value]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = (value || 0).toLocaleString();
    });
  }
  
  rerenderAllLogs = () => {
    const container = document.getElementById('logs-container');
    if (!container) return;
    
    // Clear container
    container.innerHTML = '';
    
    // Re-filter logs
    this.state.filteredLogs = this.state.logs.filter(entry => this.passesFilter(entry));
    
    // Render filtered logs (latest 500)
    const logsToRender = this.state.filteredLogs.slice(-this.maxDomRows);
    logsToRender.forEach(entry => {
      const row = this.createLogRow(entry);
      row.classList.add('fade-in-complete'); // Skip animation for bulk render
      container.appendChild(row);
    });
    
    // Update search count
    this.updateSearchCount();
    
    // Update logs status counter
    this.updateLogsStatus();
    
    // Auto-scroll to bottom
    if (this.state.autoScroll) {
      this.scrollToBottom(container);
    }
  }
  
  updateSearchCount = () => {
    const countEl = document.getElementById('search-count');
    if (countEl) {
      if (this.state.searchText || this.state.correlationFilter || this.state.raidFilter) {
        const count = this.state.filteredLogs.length;
        countEl.textContent = `${count.toLocaleString()} matches`;
        countEl.style.display = 'block';
      } else {
        countEl.style.display = 'none';
      }
    }
  }

  passesTelemetryFilter = (event) => {
    // Endpoint filter (W0.2)
    if (this.state.endpointFilter) {
      const name = event.activityName || '';
      if (!name.toLowerCase().includes(this.state.endpointFilter.toLowerCase())) return false;
    }
    // RAID / IterationId filter (W0.3)
    if (this.state.raidFilter) {
      const raidLower = this.state.raidFilter.toLowerCase();
      const iterationId = ((event.attributes && event.attributes.IterationId) || '').toLowerCase();
      const corrId = (event.correlationId || '').toLowerCase();
      if (!iterationId.includes(raidLower) && !corrId.includes(raidLower)) return false;
    }
    return true;
  }

  rerenderTelemetry = () => {
    const container = document.getElementById('telemetry-container');
    if (!container) return;
    container.innerHTML = '';
    const filtered = this.state.telemetry.filter(e => this.passesTelemetryFilter(e));
    const toRender = filtered.slice(-100).reverse();
    toRender.forEach(event => {
      const card = this.createTelemetryCard(event);
      card.classList.add('fade-in-complete');
      container.appendChild(card);
    });
  }
}
