/**
 * EDOG Real-Time Log Viewer - Filter Manager
 */

// ===== SEARCH & FILTER =====

class FilterManager {
  constructor(state, renderer) {
    this.state = state;
    this.renderer = renderer;
    this.searchTimeout = null;
    this.timeFilterInterval = null;
  }
  
  setSearch = (text) => {
    // Debounce search
    clearTimeout(this.searchTimeout);
    this.searchTimeout = setTimeout(() => {
      this.state.searchText = text.trim();
      this.applyFilters();
    }, 300);
  }
  
  toggleLevel = (level) => {
    if (this.state.activeLevels.has(level)) {
      this.state.activeLevels.delete(level);
    } else {
      this.state.activeLevels.add(level);
    }
    
    // Update button visual state
    const button = document.querySelector(`[data-level="${level}"]`);
    if (button) {
      button.classList.toggle('active', this.state.activeLevels.has(level));
    }
    
    this.applyFilters();
  }
  
  setCorrelationFilter = (rootActivityId) => {
    this.state.correlationFilter = rootActivityId;
    this.showCorrelationBadge(rootActivityId);
    this.applyFilters();
  }
  
  clearCorrelationFilter = () => {
    this.state.correlationFilter = null;
    this.hideCorrelationBadge();
    this.applyFilters();
  }

  updateTimeFilter = (seconds) => {
    this.state.timeRangeSeconds = seconds;
    if (this.timeFilterInterval) clearInterval(this.timeFilterInterval);
    if (seconds > 0) {
      this.timeFilterInterval = setInterval(() => this.applyFilters(), 10000);
    }
    this.applyFilters();
  }
  
  showCorrelationBadge = (id) => {
    const badge = document.getElementById('correlation-badge');
    const idSpan = document.getElementById('correlation-id');
    if (badge && idSpan) {
      idSpan.textContent = id.substring(0, 8) + '...';
      badge.style.display = 'block';
    }
  }
  
  hideCorrelationBadge = () => {
    const badge = document.getElementById('correlation-badge');
    if (badge) {
      badge.style.display = 'none';
    }
  }
  
  applyFilters = () => {
    this.renderer.rerenderAllLogs();
    this.renderer.rerenderTelemetry();
  }
  
  // Component presets — regex patterns to EXCLUDE
  static COMPONENT_PRESETS = {
    all: { exclude: [] },
    flt: { exclude: [/^WCL-/i, /^IntervalTimer/i, /^MonitoredScope/i, /^FutureConsumption/i, /^HealthCheck/i, /^Kestrel/i, /^Microsoft\.AspNetCore/i, /^System\./i, /^HiccupMonitor/i] },
    dag: { include: [/DagExecution/i, /NodeExec/i, /Hook/i, /InsightsMetrics/i, /RunMetrics/i, /Orchestrat/i, /Pipeline/i] },
    spark: { include: [/Spark/i, /GTS/i, /Notebook/i, /Session/i, /Livy/i, /Transform/i] },
  };
  
  applyPreset = (presetName) => {
    this.state.activePreset = presetName;
    this.state.excludedComponents.clear();
    
    const preset = FilterManager.COMPONENT_PRESETS[presetName];
    if (!preset) return;
    
    if (preset.exclude) {
      // Exclude components matching ANY exclude pattern
      const allComponents = new Set();
      this.state.logs.forEach(entry => {
        if (entry.component) allComponents.add(entry.component);
      });
      
      allComponents.forEach(component => {
        if (preset.exclude.some(pattern => pattern.test(component))) {
          this.state.excludedComponents.add(component);
        }
      });
    } else if (preset.include) {
      // Exclude everything EXCEPT components matching ANY include pattern  
      const allComponents = new Set();
      this.state.logs.forEach(entry => {
        if (entry.component) allComponents.add(entry.component);
      });
      
      allComponents.forEach(component => {
        if (!preset.include.some(pattern => pattern.test(component))) {
          this.state.excludedComponents.add(component);
        }
      });
    }
    
    this.applyFilters();
  }
  
  excludeComponent = (component) => {
    this.state.excludedComponents.add(component);
    // Reset preset to 'all' since user manually excluded
    this.state.activePreset = 'all';
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.preset === 'all');
    });
    this.applyFilters();
  }

  clearAll = () => {
    // Clear search
    this.state.searchText = '';
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = '';
    
    // Reset levels
    this.state.activeLevels = new Set(['Verbose', 'Message', 'Warning', 'Error']);
    document.querySelectorAll('.level-btn').forEach(btn => {
      btn.classList.add('active');
    });
    
    // Reset component filters
    this.state.excludedComponents.clear();
    this.state.activePreset = 'all';
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.preset === 'all');
    });
    
    // Reset time filter
    this.updateTimeFilter(0);
    document.querySelectorAll('.time-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.range === '0');
    });
    
    // Clear correlation
    this.clearCorrelationFilter();
    
    this.applyFilters();
  }
}
