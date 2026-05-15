/**
 * GVD Enterprise Bulk Scanning Frontend - Complete Implementation
 * Replaces handleScanAll() in dashboard.js with proper backend integration
 * 
 * This implementation:
 * - Calls /scan-all endpoint to create backend job
 * - Polls /scan-all/<job_id> for real-time updates
 * - Shows live logs, progress, and statistics
 * - Handles scan completion with report integration
 * - Updates dashboard stats after completion
 */

// ADD THIS TO window.GVD.dashboard object:

bulkScanPollInterval: null,

/**
 * Handle scan all repositories - ENTERPRISE VERSION
 * Calls backend /scan-all endpoint and polls for status
 */
handleScanAll: async function() {
  // Open modal immediately
  window.GVD.modal.open('bulk-scan-modal');
  
  // Reset UI
  this.resetBulkScanUI();
  
  // Add loading state to button
  const scanAllBtn = document.getElementById('scan-all-button');
  if (scanAllBtn) {
    scanAllBtn.disabled = true;
    window.GVD.loading.show(scanAllBtn);
  }

  try {
    // Get visibility filter from dashboard
    const visibilityFilter = document.getElementById('repo-visibility-filter');
    const visibility = visibilityFilter?.value || 'both';

    // Create bulk scan job on backend
    const response = await window.GVD.utils.api.post('/scan-all', {
      visibility: visibility
    });

    const jobId = response.job_id;
    const totalRepos = response.total_repositories;

    this.addBulkLog(`Bulk scan job started (ID: ${jobId})`, 'info');
    this.addBulkLog(`Total repositories to scan: ${totalRepos}`, 'info');
    
    // Store job ID for reference
    this.bulkScanJobId = jobId;
    this.bulkScanStartTime = Date.now();
    
    // Start polling for job status
    this.startBulkScanPolling(jobId);

  } catch (error) {
    console.error('Failed to start bulk scan:', error);
    this.addBulkLog(`Failed to start scan: ${error.message}`, 'error');
    window.GVD.toast.show('Failed to start bulk scan: ' + error.message, 'error');
  } finally {
    if (scanAllBtn) {
      scanAllBtn.disabled = false;
      window.GVD.loading.hide(scanAllBtn);
    }
  }
},

/**
 * Start polling mechanism for bulk scan job
 */
startBulkScanPolling: function(jobId) {
  // Clear any existing poll interval
  if (this.bulkScanPollInterval) {
    clearInterval(this.bulkScanPollInterval);
  }

  // Poll every 1 second for updates
  this.bulkScanPollInterval = setInterval(async () => {
    try {
      const status = await window.GVD.utils.api.get(`/scan-all/${jobId}`);
      this.updateBulkScanUI(status);

      // Stop polling when job is complete or failed
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(this.bulkScanPollInterval);
        this.bulkScanPollInterval = null;
        
        // Handle completion
        if (status.status === 'completed') {
          this.onBulkScanCompleted(status);
        } else {
          this.onBulkScanFailed(status);
        }
      }
    } catch (error) {
      console.error('Polling error:', error);
      // Continue polling on error
    }
  }, 1000);
},

/**
 * Update bulk scan UI with live job status
 */
updateBulkScanUI: function(jobStatus) {
  if (!jobStatus) return;

  const {
    status,
    total_repositories,
    scanned_repositories,
    failed_repositories,
    pending_repositories,
    logs,
    current_repo,
    repositories
  } = jobStatus;

  // Update progress bar
  const progress = total_repositories > 0 
    ? (scanned_repositories / total_repositories) * 100 
    : 0;
  const progressBar = document.getElementById('bulk-progress-bar');
  if (progressBar) {
    progressBar.style.width = progress + '%';
  }

  // Update progress text
  const progressText = document.getElementById('bulk-progress-text');
  if (progressText) {
    progressText.textContent = `${scanned_repositories} / ${total_repositories} repositories scanned`;
  }

  // Update stat cards
  document.getElementById('bulk-stat-completed').textContent = scanned_repositories || 0;
  document.getElementById('bulk-stat-failures').textContent = failed_repositories || 0;

  // Calculate total findings from completed repositories
  let totalFindings = 0;
  let criticalCount = 0;
  if (repositories && repositories.length > 0) {
    repositories.forEach(repo => {
      totalFindings += repo.total_findings || 0;
      const counts = repo.severity_counts || {};
      criticalCount += (counts.CRITICAL || 0) + (counts.HIGH || 0);
    });
  }
  document.getElementById('bulk-stat-findings').textContent = totalFindings;
  document.getElementById('bulk-stat-critical').textContent = criticalCount;

  // Update current repo display (if scanning)
  if (current_repo) {
    this.addBulkLog(`Now scanning: ${current_repo}`, 'info');
  }

  // Sync logs from backend
  this.syncBulkLogs(logs || []);
},

/**
 * Sync backend logs to UI
 */
syncBulkLogs: function(backendLogs) {
  const logsPanel = document.getElementById('bulk-scan-logs');
  if (!logsPanel) return;

  // Get existing log count
  const existingLogs = logsPanel.querySelectorAll('.log-entry').length;

  // Add only new logs to avoid re-rendering everything
  if (backendLogs.length > existingLogs) {
    const newLogs = backendLogs.slice(existingLogs);
    newLogs.forEach(logMessage => {
      // Parse log format: [HH:MM:SS] message
      const match = logMessage.match(/^\[(\d{2}:\d{2}:\d{2})\]\s(.+)$/);
      const timeStr = match ? match[1] : '00:00:00';
      const message = match ? match[2] : logMessage;
      
      // Determine log type from message
      let type = 'info';
      if (message.includes('✓') || message.includes('Completed')) type = 'success';
      else if (message.includes('✗') || message.includes('Failed')) type = 'error';
      else if (message.includes('Warning') || message.includes('Skipped')) type = 'warning';

      const entry = document.createElement('div');
      entry.className = `log-entry log-entry-${type}`;
      entry.innerHTML = `<span class="log-time">${timeStr}</span><span class="log-message">${window.GVD.utils.escapeHtml(message)}</span>`;
      logsPanel.appendChild(entry);
    });

    // Auto-scroll to bottom
    logsPanel.scrollTop = logsPanel.scrollHeight;
  }
},

/**
 * Handle bulk scan completion
 */
onBulkScanCompleted: async function(jobStatus) {
  this.addBulkLog('Bulk scan completed successfully!', 'success');
  
  const report = jobStatus.report;
  if (report) {
    // Show report details in modal
    this.showBulkScanReport(report);
    
    // Update dashboard stats
    await this.refreshDashboardStats();
  }

  // Show notification
  window.GVD.toast.show(
    `Bulk scan complete: ${jobStatus.scanned_repositories} succeeded, ${jobStatus.failed_repositories} failed`,
    'success'
  );
},

/**
 * Handle bulk scan failure
 */
onBulkScanFailed: function(jobStatus) {
  this.addBulkLog('Bulk scan failed: ' + (jobStatus.error || 'Unknown error'), 'error');
  window.GVD.toast.show('Bulk scan failed. Check logs for details.', 'error');
},

/**
 * Display bulk scan report in modal
 */
showBulkScanReport: function(report) {
  const reportSection = document.getElementById('bulk-scan-report-section');
  if (!reportSection) return;

  const reportId = report.report_id;
  reportSection.innerHTML = `
    <div class="bulk-report-summary">
      <h3>Scan Summary</h3>
      <div class="report-grid">
        <div class="report-stat">
          <div class="report-stat-value">${report.scanned_repositories}</div>
          <div class="report-stat-label">Repositories Scanned</div>
        </div>
        <div class="report-stat">
          <div class="report-stat-value">${report.total_findings}</div>
          <div class="report-stat-label">Total Findings</div>
        </div>
        <div class="report-stat report-stat-critical">
          <div class="report-stat-value">${report.severity_counts?.CRITICAL || 0}</div>
          <div class="report-stat-label">Critical</div>
        </div>
        <div class="report-stat">
          <div class="report-stat-value">${report.severity_counts?.HIGH || 0}</div>
          <div class="report-stat-label">High</div>
        </div>
      </div>
      <div class="report-actions">
        <a href="/download-report/${reportId}.json" class="btn btn-secondary" download>
          Download JSON Report
        </a>
        <a href="/download-report/${reportId}.pdf" class="btn btn-secondary" download>
          Download PDF Report
        </a>
        <button class="btn btn-ghost" onclick="window.open('/download-report/${reportId}.json', '_blank')">
          View JSON
        </button>
        <button class="btn btn-ghost" onclick="window.open('/download-report/${reportId}.pdf', '_blank')">
          View PDF
        </button>
      </div>
    </div>
  `;
  reportSection.hidden = false;
},

/**
 * Refresh dashboard statistics after scan
 */
refreshDashboardStats: async function() {
  try {
    const stats = await window.GVD.utils.api.get('/bulk-scan-stats');
    
    // Update scanned today metric
    const scannedTodayValue = document.querySelector('[data-metric="scanned-today"] .metric-value');
    if (scannedTodayValue) {
      scannedTodayValue.textContent = stats.scanned_today;
    }

    // Update high risk findings metric
    const riskValue = document.querySelector('[data-metric="high-risk"] .metric-value');
    if (riskValue) {
      riskValue.textContent = stats.high_risk_findings;
    }

    window.GVD.toast.show('Dashboard stats updated', 'success');
  } catch (error) {
    console.error('Failed to refresh stats:', error);
  }
},

/**
 * Reset bulk scan UI
 */
resetBulkScanUI: function() {
  document.getElementById('bulk-progress-bar').style.width = '0%';
  document.getElementById('bulk-progress-text').textContent = '0 / 0 repositories scanned';
  document.getElementById('bulk-stat-completed').textContent = '0';
  document.getElementById('bulk-stat-findings').textContent = '0';
  document.getElementById('bulk-stat-critical').textContent = '0';
  document.getElementById('bulk-stat-failures').textContent = '0';
  
  const logsPanel = document.getElementById('bulk-scan-logs');
  if (logsPanel) {
    logsPanel.innerHTML = '<div class="log-entry log-entry-info"><span class="log-time">00:00:00</span><span class="log-message">Initializing bulk scan...</span></div>';
  }

  const reportSection = document.getElementById('bulk-scan-report-section');
  if (reportSection) {
    reportSection.hidden = true;
    reportSection.innerHTML = '';
  }
},

/**
 * Add log entry
 */
addBulkLog: function(message, type = 'info') {
  const logsPanel = document.getElementById('bulk-scan-logs');
  if (!logsPanel) return;

  const elapsed = this.bulkScanStartTime 
    ? Math.floor((Date.now() - this.bulkScanStartTime) / 1000)
    : 0;
  const hours = Math.floor(elapsed / 3600);
  const minutes = Math.floor((elapsed % 3600) / 60);
  const seconds = elapsed % 60;
  const timeStr = String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');

  const entry = document.createElement('div');
  entry.className = 'log-entry log-entry-' + type;
  entry.innerHTML = '<span class="log-time">' + timeStr + '</span><span class="log-message">' + window.GVD.utils.escapeHtml(message) + '</span>';
  
  logsPanel.appendChild(entry);
  logsPanel.scrollTop = logsPanel.scrollHeight;
},
