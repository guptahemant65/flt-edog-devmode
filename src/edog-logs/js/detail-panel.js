/**
 * EDOG Real-Time Log Viewer - Detail Panel
 */

// ===== DETAIL PANEL =====

class DetailPanel {
  constructor() {
    this.isVisible = false;
  }
  
  show = (entry, type) => {
    const panel = document.getElementById('detail-panel');
    if (!panel) return;
    
    // Populate content based on type
    if (type === 'log') {
      this.showLogDetail(panel, entry);
    } else if (type === 'telemetry') {
      this.showTelemetryDetail(panel, entry);
    }
    
    // Show panel with animation
    panel.classList.add('visible');
    this.isVisible = true;
    
    // Focus close button for accessibility
    const closeBtn = panel.querySelector('#detail-close');
    if (closeBtn) closeBtn.focus();
  }
  
  showLogDetail = (panel, entry) => {
    const title = panel.querySelector('#detail-title');
    const content = panel.querySelector('.detail-content');
    
    if (title) title.textContent = 'Log Entry Details';
    
    if (content) {
      const customDataJson = JSON.stringify(entry.customData || {}, null, 2);
      const shouldCollapseJson = customDataJson.split('\n').length > 4;
      
      content.innerHTML = `
        <div class="detail-section">
          <h4>Basic Information</h4>
          <div class="detail-grid">
            <div class="detail-field">
              <label>Timestamp:</label>
              <span>${entry.timestamp || 'N/A'}</span>
            </div>
            <div class="detail-field">
              <label>Level:</label>
              <span class="level-badge ${(entry.level || '').toLowerCase()}">${entry.level || 'N/A'}</span>
            </div>
            <div class="detail-field">
              <label>Component:</label>
              <span>${this.escapeHtml(entry.component || 'N/A')}</span>
            </div>
            <div class="detail-field">
              <label>Event ID:</label>
              <span>${this.escapeHtml(entry.eventId || 'N/A')}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section">
          <h4>Message 
            <button class="copy-btn" data-copy="message" title="Copy message to clipboard">📋</button>
          </h4>
          <div class="detail-message">${this.escapeHtml(entry.message || 'No message')}</div>
        </div>
        
        <div class="detail-section">
          <h4>Correlation</h4>
          <div class="detail-field">
            <label>Root Activity ID:</label>
            <span class="clickable-id" data-id="${this.escapeHtml(entry.rootActivityId || '')}">${this.escapeHtml(entry.rootActivityId || 'N/A')}</span>
            ${entry.rootActivityId ? `<button class="copy-btn" data-copy="activityId" title="Copy Activity ID to clipboard">📋</button>` : ''}
          </div>
          <div class="cross-link" data-action="filterSSR">🔗 Find in SSR</div>
        </div>
        
        <div class="detail-section">
          <h4>Custom Data 
            <button class="copy-btn" data-copy="customData" title="Copy JSON to clipboard">📋</button>
          </h4>
          ${shouldCollapseJson ? 
            `<details class="json-details">
              <summary>Custom Data (${Object.keys(entry.customData || {}).length} fields) ▸</summary>
              <pre class="json-content">${syntaxHighlightJson(customDataJson)}</pre>
            </details>` :
            `<pre class="json-container">${syntaxHighlightJson(customDataJson)}</pre>`
          }
        </div>
      `;

      // Bind copy buttons safely via addEventListener (no inline onclick)
      const copyData = {
        message: entry.message || 'No message',
        activityId: entry.rootActivityId || '',
        customData: customDataJson
      };
      content.querySelectorAll('.copy-btn[data-copy]').forEach(btn => {
        btn.addEventListener('click', () => {
          copyToClipboard(btn, copyData[btn.dataset.copy]);
        });
      });
      content.querySelector('[data-action="filterSSR"]')?.addEventListener('click', () => {
        filterSSRByCorrelation(entry.rootActivityId || '');
      });
      
      // Add click handlers for correlation IDs
      content.querySelectorAll('.clickable-id').forEach(el => {
        el.addEventListener('click', (e) => {
          const id = e.target.dataset.id;
          if (id && window.edogViewer && window.edogViewer.filter) {
            window.edogViewer.filter.setCorrelationFilter(id);
            this.hide();
          }
        });
      });
    }
  }
  
  showTelemetryDetail = (panel, event) => {
    const title = panel.querySelector('#detail-title');
    const content = panel.querySelector('.detail-content');
    
    if (title) title.textContent = 'Telemetry Event Details';
    
    if (content) {
      const status = event.activityStatus || 'Unknown';
      const icon = this.getStatusIcon(status);
      const attributesJson = JSON.stringify(event.attributes || {}, null, 2);
      const shouldCollapseJson = attributesJson.split('\n').length > 4;
      
      content.innerHTML = `
        <div class="detail-section">
          <h4>Activity Information</h4>
          <div class="detail-grid">
            <div class="detail-field">
              <label>Activity Name:</label>
              <span>${this.escapeHtml(event.activityName || 'N/A')}</span>
            </div>
            <div class="detail-field">
              <label>Status:</label>
              <span class="status-badge ${status.toLowerCase()}">${icon} ${status}</span>
            </div>
            <div class="detail-field">
              <label>Duration:</label>
              <span>${this.formatDuration(event.durationMs)}</span>
            </div>
            <div class="detail-field">
              <label>Result Code:</label>
              <span>${this.escapeHtml(event.resultCode || 'OK')}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section">
          <h4>Timing</h4>
          <div class="detail-field">
            <label>Timestamp:</label>
            <span>${event.timestamp || 'N/A'}</span>
          </div>
        </div>
        
        <div class="detail-section">
          <h4>Correlation</h4>
          <div class="detail-field">
            <label>Correlation ID:</label>
            <span class="clickable-id" data-id="${this.escapeHtml(event.correlationId || '')}">${this.escapeHtml(event.correlationId || 'N/A')}</span>
            ${event.correlationId ? `<button class="copy-btn" data-copy="correlation" title="Copy Correlation ID to clipboard">📋</button>` : ''}
          </div>
          <div class="detail-field">
            <label>User ID:</label>
            <span>${event.userId || 'N/A'}</span>
          </div>
          <div class="cross-link" data-action="filter-correlation">🔗 Show related logs</div>
        </div>
        
        <div class="detail-section">
          <h4>Attributes
            <button class="copy-btn" data-copy="attributes" title="Copy JSON to clipboard">📋</button>
          </h4>
          ${shouldCollapseJson ? 
            `<details class="json-details">
              <summary>Attributes (${Object.keys(event.attributes || {}).length} fields) ▸</summary>
              <pre class="json-content">${syntaxHighlightJson(attributesJson)}</pre>
            </details>` :
            `<pre class="json-container">${syntaxHighlightJson(attributesJson)}</pre>`
          }
        </div>
      `;

      // Bind copy buttons safely via addEventListener
      content.querySelectorAll('.copy-btn[data-copy]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const copyType = btn.dataset.copy;
          if (copyType === 'correlation') {
            const text = event.correlationId || '';
            navigator.clipboard.writeText(text).then(() => {
              btn.textContent = '✓';
              setTimeout(() => { btn.textContent = '📋'; }, 1500);
            });
          } else if (copyType === 'attributes') {
            navigator.clipboard.writeText(attributesJson).then(() => {
              btn.textContent = '✓';
              setTimeout(() => { btn.textContent = '📋'; }, 1500);
            });
          }
        });
      });

      // Bind cross-link for filtering
      const crossLink = content.querySelector('[data-action="filter-correlation"]');
      if (crossLink) {
        crossLink.addEventListener('click', () => {
          const rootId = (event.correlationId || '').split('|')[0];
          if (rootId && window.edogViewer && window.edogViewer.filter) {
            window.edogViewer.filter.setCorrelationFilter(rootId);
          }
        });
      }
      
      // Add click handlers for correlation IDs
      content.querySelectorAll('.clickable-id').forEach(el => {
        el.addEventListener('click', (e) => {
          const id = e.target.dataset.id;
          if (id && window.edogViewer && window.edogViewer.filter) {
            // For telemetry, correlation ID might be in format "guid|guid" - use first part
            const rootId = id.split('|')[0];
            window.edogViewer.filter.setCorrelationFilter(rootId);
            this.hide();
          }
        });
      });
    }
  }
  
  hide = () => {
    const panel = document.getElementById('detail-panel');
    if (panel) {
      panel.classList.remove('visible');
    }
    this.isVisible = false;
  }
  
  escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
  
  getStatusIcon = (status) => {
    const mapping = {
      'succeeded': '✓',
      'failed': '✗',
      'cancelled': '◌',
      'pending': '⋯'
    };
    return mapping[status.toLowerCase()] || '?';
  }
}
