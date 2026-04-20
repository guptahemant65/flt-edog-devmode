# Log Viewer Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 enhancements to `src/edog-logs.html` — regex search, error grouping panel, stack trace parsing, and token correlation view.

**Architecture:** All changes are frontend-only within the single `edog-logs.html` file. Each feature adds CSS (in the `<style>` block), HTML (in the markup), and JS (as new classes or modifications to existing classes). The mock at `docs/log-viewer-enhancements-mock.html` is the visual reference — CSS/styling should match it exactly.

**Tech Stack:** Vanilla JS, CSS custom properties, existing design token system.

**Key file:** `src/edog-logs.html` (~6008 lines, single self-contained HTML)

**Mock reference:** `docs/log-viewer-enhancements-mock.html` (67.7KB, approved)

**⚠️ Critical implementation notes (from rubber-duck review):**
1. **Regex `lastIndex` trap:** Never use `rx.test()` with the `'g'` flag. Use `.match()` instead of `.test()` in `passesFilter()` to avoid stateful regex bugs.
2. **Batch handler:** `errorGrouping.processLog()` must be wired into BOTH `handleWebSocketMessage` (L6196) AND `handleWebSocketBatch` (L6219) — batch is the primary code path.
3. **ErrorGrouping._updateUI():** Debounce DOM writes with `requestAnimationFrame` to avoid jank during 100+ log/sec bursts.
4. **ErrorGrouping.groups:** Cap at 200 groups max to prevent unbounded memory growth in long sessions.
5. **Issues panel live-update:** Re-render panel body when open AND new errors arrive (debounced).
6. **Keyboard shortcut:** Use `Alt+R` (not Ctrl+R) to avoid hijacking browser refresh.
7. **No inline onclick:** Use `addEventListener` delegation, not `onclick` attributes, for CSP compatibility and codebase consistency.

---

## File Map

All changes target **one file**: `src/edog-logs.html`

| Section | Line Range | What Changes |
|---------|-----------|--------------|
| CSS — filters section | ~496-882 | Add regex toggle + error tooltip styles |
| CSS — new section after `css/smart.css` | ~1893 | Add Issues Panel, Stack Trace, Token Flow CSS |
| HTML — search wrapper | ~2636-2639 | Add regex toggle button + tooltip container |
| HTML — toolbar actions | ~2668-2673 | Add Issues toggle button |
| HTML — logs panel | ~2686-2696 | Add Issues panel between log-scroll and status bar |
| JS — LogViewerState | ~2877-2934 | Add `regexMode`, `regexValid`, `issuesPanelOpen` state |
| JS — Renderer.passesFilter | ~3732-3741 | Modify text search to support regex |
| JS — Renderer.updateSearchCount | ~3804-3813 | Show regex error state |
| JS — FilterManager.setSearch | ~3886-3893 | Validate regex when in regex mode |
| JS — DetailPanel.showLogDetail | ~4116-4197 | Add stack trace + token flow sections |
| JS — new classes after AnomalyDetector | ~5155 | Add `ErrorGrouping`, `StackTraceParser`, `TokenCorrelation` classes |
| JS — EdogLogViewer constructor | ~5917-5936 | Wire new modules |
| JS — EdogLogViewer.bindEventListeners | ~5978 | Add regex toggle + issues panel keybindings |

---

### Task 1: Regex Search Toggle (Feature 4)

**Why first:** Smallest change, self-contained, touches search system that other features reference.

**Files:**
- Modify: `src/edog-logs.html` — CSS (~496), HTML (~2636), JS state (~2877), JS filter (~3732, ~3886), JS bindings (~5978)

- [ ] **Step 1: Add CSS for regex toggle**

Insert after the `.search-count` rule (after line ~543):

```css
/* Feature 4: Regex Toggle */
.regex-toggle {
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1.3;
}
.regex-toggle:hover { border-color: var(--border-bright); color: var(--text-dim); }
.regex-toggle.active { background: var(--accent); color: white; border-color: var(--accent); }

#search-input.regex-active { font-family: var(--font-mono); font-size: 12px; }
#search-input.regex-error { border-color: var(--level-error) !important; box-shadow: 0 0 0 3px rgba(248,113,113,0.15) !important; }
#search-input.regex-valid { border-color: var(--status-succeeded); box-shadow: 0 0 0 3px rgba(52,211,153,0.1); }

.regex-tooltip {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  background: var(--surface);
  border: 1px solid rgba(248,113,113,0.3);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--level-error);
  font-family: var(--font-mono);
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  z-index: 200;
  display: none;
  animation: tooltipIn 0.15s ease-out;
}
.regex-tooltip.visible { display: block; }

@keyframes tooltipIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 2: Modify HTML search wrapper**

Replace the search wrapper HTML (lines ~2636-2639) from:

```html
<div class="search-wrapper">
  <span class="search-icon">🔍</span>
  <input type="text" id="search-input" placeholder="Search logs... (Ctrl+K)" />
  <span id="search-count" class="search-count"></span>
</div>
```

To:

```html
<div class="search-wrapper" id="search-wrapper">
  <span class="search-icon">🔍</span>
  <input type="text" id="search-input" placeholder="Search logs... (Ctrl+K)" />
  <div class="search-right-controls" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);display:flex;align-items:center;gap:6px;">
    <span id="search-count" class="search-count"></span>
    <button id="regex-toggle" class="regex-toggle" title="Toggle regex mode (Alt+R)">/.*/</button>
  </div>
  <div id="regex-tooltip" class="regex-tooltip"></div>
</div>
```

- [ ] **Step 3: Add regex state to LogViewerState**

In `LogViewerState.constructor()` (after line ~2889 `this.timeRangeSeconds = 0;`), add:

```javascript
// Feature 4: Regex search
this.regexMode = false;
this.regexValid = true;
this.compiledRegex = null;
```

- [ ] **Step 4: Modify passesFilter for regex support**

Replace the text search block in `Renderer.passesFilter` (lines ~3732-3741) from:

```javascript
// Text search
if (this.state.searchText) {
  const searchLower = this.state.searchText.toLowerCase();
  const msg = (entry.message || '').toLowerCase();
  const comp2 = (entry.component || '').toLowerCase();
  const raid = (entry.rootActivityId || '').toLowerCase();
  if (!msg.includes(searchLower) && !comp2.includes(searchLower) && !raid.includes(searchLower)) {
    const custom = entry.customData ? JSON.stringify(entry.customData).toLowerCase() : '';
    if (!custom.includes(searchLower)) return false;
  }
}
```

With:

```javascript
// Text search (plain text or regex)
if (this.state.searchText) {
  if (this.state.regexMode && this.state.compiledRegex) {
    const rx = this.state.compiledRegex;
    const msg = entry.message || '';
    const comp2 = entry.component || '';
    const raid = entry.rootActivityId || '';
    // Use .match() not .test() — avoids lastIndex statefulness trap if 'g' flag ever added
    if (!msg.match(rx) && !comp2.match(rx) && !raid.match(rx)) {
      const custom = entry.customData ? JSON.stringify(entry.customData) : '';
      if (!custom.match(rx)) return false;
    }
  } else if (!this.state.regexMode) {
    const searchLower = this.state.searchText.toLowerCase();
    const msg = (entry.message || '').toLowerCase();
    const comp2 = (entry.component || '').toLowerCase();
    const raid = (entry.rootActivityId || '').toLowerCase();
    if (!msg.includes(searchLower) && !comp2.includes(searchLower) && !raid.includes(searchLower)) {
      const custom = entry.customData ? JSON.stringify(entry.customData).toLowerCase() : '';
      if (!custom.includes(searchLower)) return false;
    }
  }
}
```

- [ ] **Step 5: Modify FilterManager.setSearch for regex validation**

Replace `FilterManager.setSearch` (lines ~3886-3893) from:

```javascript
setSearch = (text) => {
  // Debounce search
  clearTimeout(this.searchTimeout);
  this.searchTimeout = setTimeout(() => {
    this.state.searchText = text.trim();
    this.applyFilters();
  }, 300);
}
```

With:

```javascript
setSearch = (text) => {
  clearTimeout(this.searchTimeout);
  this.searchTimeout = setTimeout(() => {
    this.state.searchText = text.trim();

    // Regex validation
    if (this.state.regexMode && this.state.searchText) {
      try {
        this.state.compiledRegex = new RegExp(this.state.searchText, 'i');
        this.state.regexValid = true;
      } catch (e) {
        this.state.compiledRegex = null;
        this.state.regexValid = false;
      }
    } else {
      this.state.compiledRegex = null;
      this.state.regexValid = true;
    }

    this._updateRegexUI();
    this.applyFilters();
  }, 300);
}

toggleRegexMode = () => {
  this.state.regexMode = !this.state.regexMode;
  const btn = document.getElementById('regex-toggle');
  const input = document.getElementById('search-input');
  if (btn) btn.classList.toggle('active', this.state.regexMode);
  if (input) {
    input.classList.toggle('regex-active', this.state.regexMode);
    input.placeholder = this.state.regexMode ? 'Search with regex... (Ctrl+K)' : 'Search logs... (Ctrl+K)';
  }
  // Re-evaluate current search text
  if (this.state.searchText) {
    this.setSearch(this.state.searchText);
  } else {
    this._updateRegexUI();
  }
}

_updateRegexUI = () => {
  const input = document.getElementById('search-input');
  const tooltip = document.getElementById('regex-tooltip');
  if (!input) return;

  input.classList.remove('regex-error', 'regex-valid');
  if (tooltip) tooltip.classList.remove('visible');

  if (this.state.regexMode && this.state.searchText) {
    if (!this.state.regexValid) {
      input.classList.add('regex-error');
      if (tooltip) {
        tooltip.textContent = 'Invalid regex pattern';
        tooltip.classList.add('visible');
      }
    } else {
      input.classList.add('regex-valid');
    }
  }
}
```

- [ ] **Step 6: Add keybinding for Ctrl+R in EdogLogViewer.bindEventListeners**

In `bindEventListeners` (after the search input listener, ~line 5993), add:

```javascript
// Regex toggle: Alt+R (not Ctrl+R — that's browser refresh)
document.addEventListener('keydown', (e) => {
  if (e.altKey && e.key === 'r') {
    e.preventDefault();
    this.filter.toggleRegexMode();
  }
});

// Regex toggle button click
const regexBtn = document.getElementById('regex-toggle');
if (regexBtn) {
  regexBtn.addEventListener('click', () => {
    this.filter.toggleRegexMode();
  });
}
```

- [ ] **Step 7: Verify — open log viewer, test regex mode**

1. Open the log viewer in browser
2. Click `/.*/` button — should turn purple
3. Type `TokenExpired|Unauthorized` — should match entries with either term
4. Type `[invalid` — search input should turn red with error tooltip
5. Press Ctrl+R — should toggle regex mode off, returning to plain text
6. Verify plain text search still works normally

- [ ] **Step 8: Commit**

```bash
git add src/edog-logs.html
git commit -m "feat(log-viewer): add regex search toggle with Ctrl+R shortcut

- Toggle button /.* / next to search count
- Compiles search text as RegExp when active
- Red border + tooltip on invalid regex
- Green border on valid regex with matches
- Ctrl+R keyboard shortcut to toggle

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Error Grouping Panel (Feature 1)

**Files:**
- Modify: `src/edog-logs.html` — CSS (new section), HTML (~2668, ~2686-2696), JS (new `ErrorGrouping` class, wire in EdogLogViewer)

- [ ] **Step 1: Add CSS for Issues Panel**

Insert after the `css/smart.css` section (after line ~1893, before the `api-toast` styles):

```css
/* === css/issues.css === */
/* Feature 1: Error Grouping Panel — Chrome DevTools Issues style */
.issues-panel {
  border-top: 1px solid var(--border);
  background: var(--bg);
  overflow: hidden;
  transition: height 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  flex-shrink: 0;
}
.issues-panel.collapsed { height: 0 !important; }

.issues-resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  cursor: ns-resize;
  z-index: 10;
  background: transparent;
  transition: background 0.15s;
}
.issues-resize-handle:hover,
.issues-resize-handle.dragging { background: var(--accent); }

.issues-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.issues-header h4 {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  border: none;
  padding: 0;
}
.issues-header-count {
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(248,113,113,0.15);
  color: var(--level-error);
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 16px;
}
.issues-collapse-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  border-radius: 3px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s;
}
.issues-collapse-btn:hover { background: var(--surface-3); color: var(--text); }

.issues-body {
  overflow-y: auto;
  padding: 8px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.issue-group-card {
  background: rgba(248, 113, 113, 0.05);
  border: 1px solid rgba(248, 113, 113, 0.15);
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.issue-group-card:hover { border-color: rgba(248, 113, 113, 0.35); background: rgba(248, 113, 113, 0.08); }
.issue-group-card.active { border-color: var(--level-error); background: rgba(248, 113, 113, 0.1); }

.issue-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.issue-group-code {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--level-error);
  flex: 1;
}
.issue-group-count {
  display: inline-block;
  padding: 0 5px;
  border-radius: 8px;
  background: var(--level-error);
  color: #000;
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 16px;
}
.issue-group-chevron {
  color: var(--text-muted);
  font-size: 10px;
  transition: transform 0.15s;
  flex-shrink: 0;
}
.issue-group-card.expanded .issue-group-chevron { transform: rotate(90deg); }

.issue-group-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 10px;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.issue-group-components { display: flex; gap: 4px; flex-wrap: wrap; }

.issue-group-samples {
  display: none;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(248,113,113,0.1);
  flex-direction: column;
  gap: 4px;
}
.issue-group-card.expanded .issue-group-samples { display: flex; }
.issue-sample {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  padding: 4px 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.5;
}

.issues-empty {
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
  padding: 16px;
  font-style: italic;
}

/* Issues toggle button in toolbar */
.issues-toggle {
  color: var(--level-error);
  border-color: rgba(248,113,113,0.3);
  position: relative;
}
.issues-toggle:hover { background: rgba(248,113,113,0.1); color: var(--level-error); border-color: var(--level-error); }
.issues-toggle.active { background: rgba(248,113,113,0.15); border-color: var(--level-error); color: var(--level-error); }
.issues-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--level-error);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
  line-height: 1;
}
```

- [ ] **Step 2: Add Issues toggle button in toolbar HTML**

In the toolbar actions div (line ~2668-2673), add after the `↓E` button:

```html
<button id="issues-toggle-btn" class="action-btn issues-toggle" title="Toggle error grouping panel" style="display:none">
  ⚡ Issues <span class="issues-count-badge" id="issues-badge-count">0</span>
</button>
```

- [ ] **Step 3: Add Issues panel HTML in logs panel**

Between `<div id="logs-container" class="log-scroll">...</div>` and `<div class="logs-status">` (after line ~2692, before line ~2693), insert:

```html
<!-- Feature 1: Error Grouping Panel -->
<div id="issues-panel" class="issues-panel collapsed" style="height: 220px;">
  <div class="issues-resize-handle" id="issues-resize-handle"></div>
  <div class="issues-header">
    <h4>Error Groups <span class="issues-header-count" id="issues-count">0</span></h4>
    <button class="issues-collapse-btn" id="issues-collapse-btn" title="Collapse issues">▾</button>
  </div>
  <div class="issues-body" id="issues-body"></div>
</div>
```

- [ ] **Step 4: Add ErrorGrouping class**

Insert after the `AnomalyDetector` class (after line ~5155):

```javascript
// === js/error-grouping.js ===
/**
 * ErrorGrouping — Groups errors by error code/pattern for the Issues panel.
 */
class ErrorGrouping {
  static MAX_GROUPS = 200; // Cap to prevent unbounded memory growth

  constructor(state) {
    this.state = state;
    this.groups = new Map(); // errorCode -> { code, count, firstSeen, lastSeen, components, samples }
    this.panelOpen = false;
    this._uiDirty = false;
  }

  processLog = (entry) => {
    if ((entry.level || '').toLowerCase() !== 'error') return;
    const code = this._extractErrorCode(entry.message || '');

    // Cap group count to prevent memory leak in long sessions
    if (!this.groups.has(code) && this.groups.size >= ErrorGrouping.MAX_GROUPS) return;

    if (!this.groups.has(code)) {
      this.groups.set(code, {
        code,
        count: 0,
        firstSeen: entry.timestamp,
        lastSeen: entry.timestamp,
        components: new Set(),
        samples: []
      });
    }
    const group = this.groups.get(code);
    group.count++;
    group.lastSeen = entry.timestamp;
    group.components.add(entry.component || 'Unknown');
    if (group.samples.length < 3) {
      group.samples.push(entry.message || '');
    }

    // Debounce DOM updates with rAF to avoid jank during batch processing
    if (!this._uiDirty) {
      this._uiDirty = true;
      requestAnimationFrame(() => {
        this._updateUI();
        // Live-update panel body if open
        if (this.panelOpen) this.renderGroups();
        this._uiDirty = false;
      });
    }
  }

  _extractErrorCode = (message) => {
    const codeMatch = message.match(/ErrorCode[=:]\s*(\w+)/i)
      || message.match(/Error[=:]\s*(\w+)/i)
      || message.match(/(\w+Error)\b/);
    return codeMatch ? codeMatch[1] : message.substring(0, 60).replace(/[^a-zA-Z0-9 ]/g, '').trim() || 'Unknown';
  }

  _updateUI = () => {
    const badge = document.getElementById('issues-badge-count');
    const headerCount = document.getElementById('issues-count');
    const toggleBtn = document.getElementById('issues-toggle-btn');
    const count = this.groups.size;
    if (badge) badge.textContent = count;
    if (headerCount) headerCount.textContent = count;
    if (toggleBtn) toggleBtn.style.display = count > 0 ? '' : 'none';
  }

  togglePanel = () => {
    this.panelOpen = !this.panelOpen;
    const panel = document.getElementById('issues-panel');
    const btn = document.getElementById('issues-toggle-btn');
    if (panel) panel.classList.toggle('collapsed', !this.panelOpen);
    if (btn) btn.classList.toggle('active', this.panelOpen);
    if (this.panelOpen) this.renderGroups();
  }

  renderGroups = () => {
    const body = document.getElementById('issues-body');
    if (!body) return;

    if (this.groups.size === 0) {
      body.innerHTML = '<div class="issues-empty">No errors detected</div>';
      return;
    }

    const sorted = [...this.groups.values()].sort((a, b) => b.count - a.count);
    body.innerHTML = sorted.map(g => {
      const comps = [...g.components].map(c => {
        const cat = this._getComponentCategory(c);
        return `<span class="log-component" data-category="${cat}">${this._escapeHtml(c)}</span>`;
      }).join('');
      const samples = g.samples.map(s =>
        `<div class="issue-sample">${this._escapeHtml(s)}</div>`
      ).join('');
      const firstTime = g.firstSeen ? new Date(g.firstSeen).toLocaleTimeString() : '—';
      const lastTime = g.lastSeen ? new Date(g.lastSeen).toLocaleTimeString() : '—';
      return `
        <div class="issue-group-card" data-code="${this._escapeHtml(g.code)}">
          <div class="issue-group-header">
            <span class="issue-group-code">${this._escapeHtml(g.code)}</span>
            <span class="issue-group-count">${g.count}</span>
            <span class="issue-group-chevron">▸</span>
          </div>
          <div class="issue-group-meta">
            <span>First: ${firstTime}</span>
            <span>Last: ${lastTime}</span>
          </div>
          <div class="issue-group-components">${comps}</div>
          <div class="issue-group-samples">${samples}</div>
        </div>`;
    }).join('');

    // Bind click handlers
    body.querySelectorAll('.issue-group-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.issue-group-samples')) return;
        card.classList.toggle('expanded');
      });
      card.addEventListener('dblclick', () => {
        const code = card.dataset.code;
        if (code && window.edogViewer) {
          window.edogViewer.filter.setSearch(code);
        }
      });
    });
  }

  _getComponentCategory = (comp) => {
    const c = (comp || '').toLowerCase();
    if (c.includes('controller') || c.includes('livetable')) return 'controller';
    if (c.includes('dag') || c.includes('execution')) return 'dag';
    if (c.includes('onelake') || c.includes('lakehouse')) return 'onelake';
    if (c.includes('dq') || c.includes('insight')) return 'dq';
    if (c.includes('retry') || c.includes('token')) return 'retry';
    return 'default';
  }

  _escapeHtml = (text) => {
    if (!text) return '';
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  clear = () => {
    this.groups.clear();
    this._updateUI();
    const body = document.getElementById('issues-body');
    if (body) body.innerHTML = '<div class="issues-empty">No errors detected</div>';
  }
}
```

- [ ] **Step 5: Wire ErrorGrouping into EdogLogViewer**

In `EdogLogViewer.constructor()` (after `this.anomaly = new AnomalyDetector(this.state);` ~line 5932), add:

```javascript
this.errorGrouping = new ErrorGrouping(this.state);
```

In **BOTH** `handleWebSocketMessage` (line ~6196, after `this.anomaly.processLog(data);`) AND `handleWebSocketBatch` (line ~6219, after `this.anomaly.processLog(log);`), add:

```javascript
this.errorGrouping.processLog(entry); // use 'data' in handleWebSocketMessage, 'log' in handleWebSocketBatch
```

**IMPORTANT:** Must be wired in both places — batch is the primary code path for server-sent frames.

- [ ] **Step 6: Add Issues panel event bindings in bindEventListeners**

```javascript
// Issues toggle button
const issuesToggle = document.getElementById('issues-toggle-btn');
if (issuesToggle) {
  issuesToggle.addEventListener('click', () => this.errorGrouping.togglePanel());
}
const issuesCollapse = document.getElementById('issues-collapse-btn');
if (issuesCollapse) {
  issuesCollapse.addEventListener('click', () => this.errorGrouping.togglePanel());
}

// Issues panel resize handle
const resizeHandle = document.getElementById('issues-resize-handle');
if (resizeHandle) {
  let startY, startHeight;
  resizeHandle.addEventListener('mousedown', (e) => {
    startY = e.clientY;
    const panel = document.getElementById('issues-panel');
    startHeight = panel ? panel.offsetHeight : 220;
    resizeHandle.classList.add('dragging');
    const onMove = (e2) => {
      const delta = startY - e2.clientY;
      const newHeight = Math.max(100, Math.min(500, startHeight + delta));
      if (panel) panel.style.height = newHeight + 'px';
    };
    const onUp = () => {
      resizeHandle.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}
```

- [ ] **Step 7: Verify error grouping**

1. Send logs with errors to the viewer (or wait for real errors)
2. Verify "⚡ Issues" button appears in toolbar when errors exist
3. Click it — panel expands at bottom of Logs tab
4. Click a group card — expands to show sample messages
5. Double-click a group — filters the log stream to that error code
6. Drag the resize handle — panel resizes
7. Click collapse button — panel hides

- [ ] **Step 8: Commit**

```bash
git add src/edog-logs.html
git commit -m "feat(log-viewer): add error grouping panel (Chrome DevTools Issues-style)

- Collapsible Issues panel at bottom of Logs tab
- Groups errors by extracted error code with counts
- Expand groups to see sample messages
- Double-click to filter log stream by error code
- Resize handle for panel height adjustment
- Auto-shows Issues button when errors detected

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Stack Trace Parsing (Feature 2)

**Files:**
- Modify: `src/edog-logs.html` — CSS (new section), JS (`DetailPanel.showLogDetail`, new `StackTraceParser` class)

- [ ] **Step 1: Add CSS for Stack Trace**

Insert after the Issues Panel CSS:

```css
/* === css/stacktrace.css === */
/* Feature 2: Stack Trace Parsing */
.stack-trace-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.stack-filter-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-dim);
  font-size: 10px;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: all 0.15s;
}
.stack-filter-btn:hover { border-color: var(--accent); color: var(--accent); }
.stack-filter-btn.active { background: var(--accent); color: white; border-color: var(--accent); }

.stack-frames {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.stack-frame {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  border-bottom: 1px solid var(--border);
  transition: background 0.1s;
  line-height: 1.5;
}
.stack-frame:last-child { border-bottom: none; }
.stack-frame:hover { background: var(--surface-2); }
.stack-frame-icon { color: var(--text-muted); font-size: 8px; flex-shrink: 0; width: 12px; text-align: center; }

.stack-frame.flt-frame {
  background: var(--accent-dim);
  color: var(--accent);
}
.stack-frame.flt-frame .stack-frame-icon { color: var(--accent); }
.stack-frame.flt-frame .stack-frame-method { color: var(--accent); font-weight: 500; }

.stack-frame.framework-frame { color: var(--text-muted); }
.stack-frame.framework-frame .stack-frame-method { color: var(--text-muted); }

.stack-frame-method { color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stack-frame-location { color: var(--text-dim); font-size: 10px; flex-shrink: 0; white-space: nowrap; }

.stack-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.1s;
}
.stack-group-header:hover { background: var(--surface-3); color: var(--text-dim); }
.stack-group-chevron { font-size: 8px; transition: transform 0.15s; }
.stack-group-header.expanded .stack-group-chevron { transform: rotate(90deg); }
.stack-group-frames { display: none; }
.stack-group-header.expanded + .stack-group-frames { display: contents; }
```

- [ ] **Step 2: Add StackTraceParser class**

Insert after the `ErrorGrouping` class:

```javascript
// === js/stack-trace.js ===
/**
 * StackTraceParser — Detects and renders C# stack traces in the detail panel.
 */
class StackTraceParser {
  static STACK_LINE_REGEX = /^\s+at\s+(.+?)(?:\s+in\s+(.+?):line\s+(\d+))?$/;
  static FLT_NAMESPACE = /^Microsoft\.LiveTable\./;
  static FRAMEWORK_NAMESPACES = [
    /^System\./,
    /^Microsoft\.AspNetCore\./,
    /^Microsoft\.Extensions\./,
    /^System\.Runtime\./,
  ];

  static hasStackTrace(message) {
    return /\n\s+at\s+(System\.|Microsoft\.)/m.test(message || '');
  }

  static parse(message) {
    const lines = (message || '').split('\n');
    const frames = [];
    for (const line of lines) {
      const match = line.match(StackTraceParser.STACK_LINE_REGEX);
      if (match) {
        const method = match[1];
        const file = match[2] || '';
        const lineNum = match[3] || '';
        const isFlt = StackTraceParser.FLT_NAMESPACE.test(method);
        const isFramework = StackTraceParser.FRAMEWORK_NAMESPACES.some(rx => rx.test(method));
        frames.push({ method, file, lineNum, isFlt, isFramework });
      }
    }
    return frames;
  }

  static renderSection(frames, escapeHtml) {
    if (frames.length === 0) return '';

    // Group consecutive framework frames
    const rendered = [];
    let frameworkGroup = [];
    const flushFrameworkGroup = () => {
      if (frameworkGroup.length === 0) return;
      if (frameworkGroup.length <= 2) {
        frameworkGroup.forEach(f => rendered.push(StackTraceParser._renderFrame(f, escapeHtml)));
      } else {
        const ns = frameworkGroup[0].method.split('.').slice(0, 2).join('.');
        rendered.push(`<div class="stack-group-header" data-action="toggle-group">
          <span class="stack-group-chevron">▸</span>
          ${escapeHtml(ns)} (${frameworkGroup.length} frames)
        </div><div class="stack-group-frames">`);
        frameworkGroup.forEach(f => rendered.push(StackTraceParser._renderFrame(f, escapeHtml)));
        rendered.push('</div>');
      }
      frameworkGroup = [];
    };

    for (const frame of frames) {
      if (frame.isFramework && !frame.isFlt) {
        frameworkGroup.push(frame);
      } else {
        flushFrameworkGroup();
        rendered.push(StackTraceParser._renderFrame(frame, escapeHtml));
      }
    }
    flushFrameworkGroup();

    return `
      <div class="detail-section stack-trace-section">
        <h4>Stack Trace (${frames.length} frames)
          <button class="stack-filter-btn" data-action="flt-only">FLT only</button>
          <button class="copy-btn" data-copy="stackTrace">copy</button>
        </h4>
        <div class="stack-frames">${rendered.join('')}</div>
      </div>`;
  }

  static _renderFrame(frame, escapeHtml) {
    const cls = frame.isFlt ? 'flt-frame' : (frame.isFramework ? 'framework-frame' : '');
    const loc = frame.file ? `${frame.file}:${frame.lineNum}` : '';
    return `<div class="stack-frame ${cls}">
      <span class="stack-frame-icon">▸</span>
      <span class="stack-frame-method">${escapeHtml(frame.method)}</span>
      ${loc ? `<span class="stack-frame-location">${escapeHtml(loc)}</span>` : ''}
    </div>`;
  }
}
```

- [ ] **Step 3: Modify DetailPanel.showLogDetail to include stack trace section**

In `showLogDetail` (line ~4169), after the custom data section and before the closing of `content.innerHTML`, add the stack trace section. Replace the closing of `content.innerHTML = \`...\`;` to include:

After the customData section template literal, before the closing backtick, add:

```javascript
${StackTraceParser.hasStackTrace(entry.message) ? StackTraceParser.renderSection(
  StackTraceParser.parse(entry.message), this.escapeHtml
) : ''}
```

Then after `content.innerHTML = ...`, add event binding for the FLT-only toggle and stack group headers:

```javascript
// Stack trace group headers — addEventListener, not inline onclick (CSP-safe)
content.querySelectorAll('.stack-group-header').forEach(h => {
  h.addEventListener('click', () => h.classList.toggle('expanded'));
});

// Stack trace FLT-only toggle
const fltBtn = content.querySelector('[data-action="flt-only"]');
if (fltBtn) {
  fltBtn.addEventListener('click', () => {
    fltBtn.classList.toggle('active');
    const frames = content.querySelectorAll('.stack-frame.framework-frame, .stack-group-header, .stack-group-frames');
    const hide = fltBtn.classList.contains('active');
    frames.forEach(f => f.style.display = hide ? 'none' : '');
  });
}

// Stack trace copy
if (content.querySelector('[data-copy="stackTrace"]')) {
  const stackText = StackTraceParser.parse(entry.message || '')
    .map(f => `  at ${f.method}${f.file ? ` in ${f.file}:${f.lineNum}` : ''}`)
    .join('\n');
  copyData.stackTrace = stackText;
}
```

- [ ] **Step 4: Verify stack traces**

1. Click on a log entry that has a C# stack trace in its message
2. Detail panel should show a "STACK TRACE" section with parsed frames
3. FLT frames (`Microsoft.LiveTable.*`) should be highlighted in purple
4. Framework frames should be grouped and collapsible
5. "FLT only" button should toggle framework frame visibility
6. Copy button should copy cleaned stack trace

- [ ] **Step 5: Commit**

```bash
git add src/edog-logs.html
git commit -m "feat(log-viewer): add C# stack trace parsing in detail panel

- Auto-detects stack traces in log messages
- FLT frames (Microsoft.LiveTable.*) highlighted with accent color
- Framework frames grouped and collapsible
- 'FLT only' toggle to hide framework noise
- Copy cleaned stack trace button

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Token Correlation View (Feature 3)

**Files:**
- Modify: `src/edog-logs.html` — CSS (new section), JS (new `TokenCorrelation` class, modify `DetailPanel`)

- [ ] **Step 1: Add CSS for Token Flow**

Insert after the Stack Trace CSS:

```css
/* === css/tokenflow.css === */
/* Feature 3: Token Correlation View */
.token-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.token-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}
.token-step:first-child { border-radius: 6px 0 0 6px; }
.token-step:last-child { border-radius: 0 6px 6px 0; }
.token-step:only-child { border-radius: 6px; }
.token-step:hover { background: var(--surface-2); border-color: var(--border-bright); z-index: 1; }
.token-step + .token-step { margin-left: -1px; }

.token-step-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.token-step-dot.success { background: var(--status-succeeded); box-shadow: 0 0 4px var(--status-succeeded); }
.token-step-dot.failed { background: var(--level-error); box-shadow: 0 0 4px var(--level-error); }
.token-step-dot.pending { background: var(--text-muted); }

.token-step-label { font-weight: 500; color: var(--text); white-space: nowrap; }
.token-step.failed-step { border-color: rgba(248,113,113,0.3); background: rgba(248,113,113,0.05); }
.token-step.failed-step .token-step-label { color: var(--level-error); }

.token-step-arrow {
  color: var(--text-muted);
  font-size: 10px;
  flex-shrink: 0;
  margin: 0 -1px;
  z-index: 2;
  background: var(--bg);
  padding: 0 2px;
}

.token-detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 3px 0;
}
.token-detail-label { color: var(--text-muted); font-size: 10px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.3px; font-weight: 500; }
.token-detail-value { font-family: var(--font-mono); color: var(--text); font-size: 11px; }
.token-detail-value.error { color: var(--level-error); }
```

- [ ] **Step 2: Add TokenCorrelation class**

Insert after the `StackTraceParser` class:

```javascript
// === js/token-correlation.js ===
/**
 * TokenCorrelation — Detects token-related logs and renders breadcrumb trail.
 */
class TokenCorrelation {
  static TOKEN_PATTERNS = [
    { step: 'Bearer Refresh', regex: /bearer.*(?:refresh|expir|renew)/i },
    { step: 'MWC Generation', regex: /MWC.*(?:token|generat)/i },
    { step: 'API Call', regex: /(?:Unauthorized|403|401|TokenExpired|AccessDenied)/i },
  ];

  static isTokenRelated(message) {
    return /\b(bearer|MWC|token|Unauthorized|403|401)\b/i.test(message || '');
  }

  static detectSteps(entry, allLogs) {
    const raid = entry.rootActivityId;
    if (!raid) return null;

    const relatedLogs = [];
    if (allLogs && allLogs.forEach) {
      allLogs.forEach(log => {
        if (log.rootActivityId === raid && TokenCorrelation.isTokenRelated(log.message)) {
          relatedLogs.push(log);
        }
      });
    }
    if (relatedLogs.length === 0) return null;

    const steps = TokenCorrelation.TOKEN_PATTERNS.map(pattern => {
      const match = relatedLogs.find(l => pattern.regex.test(l.message));
      return {
        label: pattern.step,
        found: !!match,
        failed: match && (match.level || '').toLowerCase() === 'error',
        timestamp: match ? match.timestamp : null,
        message: match ? match.message : null,
      };
    });

    // Only show if at least one step matched
    return steps.some(s => s.found) ? steps : null;
  }

  static renderSection(steps, escapeHtml) {
    if (!steps) return '';

    const breadcrumbs = steps.map((step, i) => {
      const dotClass = !step.found ? 'pending' : (step.failed ? 'failed' : 'success');
      const stepClass = step.failed ? 'failed-step' : '';
      const arrow = i < steps.length - 1 ? '<span class="token-step-arrow">→</span>' : '';
      return `<div class="token-step ${stepClass}" title="${step.message ? escapeHtml(step.message.substring(0, 100)) : 'Not detected'}">
        <span class="token-step-dot ${dotClass}"></span>
        <span class="token-step-label">${escapeHtml(step.label)}</span>
      </div>${arrow}`;
    }).join('');

    const details = steps.filter(s => s.found).map(s => {
      const time = s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : '—';
      return `<div class="token-detail-row">
        <span class="token-detail-label">${escapeHtml(s.label)}</span>
        <span class="token-detail-value${s.failed ? ' error' : ''}">${time}${s.failed ? ' — FAILED' : ''}</span>
      </div>`;
    }).join('');

    return `
      <div class="detail-section token-flow-section">
        <h4>Token Flow</h4>
        <div class="token-breadcrumbs">${breadcrumbs}</div>
        <div class="token-details">${details}</div>
      </div>`;
  }
}
```

- [ ] **Step 3: Modify DetailPanel.showLogDetail to include token flow**

In `showLogDetail`, after the stack trace insertion, add the token flow section to `content.innerHTML`:

```javascript
${TokenCorrelation.isTokenRelated(entry.message) ?
  TokenCorrelation.renderSection(
    TokenCorrelation.detectSteps(entry, window.edogViewer ? window.edogViewer.state.logBuffer : null),
    this.escapeHtml
  ) : ''}
```

- [ ] **Step 4: Verify token correlation**

1. Trigger a token-related error (or wait for bearer/MWC/Unauthorized logs)
2. Click on a token-related log entry
3. Detail panel should show "TOKEN FLOW" section with breadcrumb trail
4. Steps with successful tokens show green dots
5. Failed steps show red dots
6. Non-token-related logs should NOT show this section

- [ ] **Step 5: Commit**

```bash
git add src/edog-logs.html
git commit -m "feat(log-viewer): add token correlation breadcrumb trail

- Auto-detects bearer/MWC/auth-related log entries
- Shows breadcrumb: Bearer Refresh → MWC Generation → API Call
- Green/red status dots per step
- Failed steps highlighted in red
- Only appears for token-related logs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Integration Test & Version Bump

- [ ] **Step 1: Test all 4 features together**

Open `src/edog-logs.html` via `python edog.py --logs` or directly, and verify:
1. Regex search: toggle works, Ctrl+R shortcut, valid/invalid states
2. Error grouping: Issues button appears on errors, panel expands/collapses, resize, double-click filters
3. Stack trace: appears in detail panel for C# stack trace messages, FLT highlighting, collapse groups
4. Token flow: breadcrumbs appear for auth-related logs, green/red dots correct

- [ ] **Step 2: Bump version**

In `edog.py` (line ~63), bump `EDOG_VERSION`:

```python
EDOG_VERSION = "3.3.0"
```

- [ ] **Step 3: Final commit**

```bash
git add edog.py src/edog-logs.html
git commit -m "chore: bump version to 3.3.0 for log viewer enhancements

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
