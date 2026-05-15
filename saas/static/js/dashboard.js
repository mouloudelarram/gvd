/**
 * GVD Professional Design System - Dashboard JavaScript
 * Interactive functionality for the repository dashboard
 */

// Dashboard-specific functionality
window.GVD.dashboard = {
  state: {
    repos: [],
    currentFilter: 'both',
    searchQuery: '',
    activeScan: null,
    searchResults: [],
    searchPage: 1,
    searchHasMore: false
  },

  bulkScanState: {
    scanning: false,
    completed: 0,
    failures: 0,
    totalFindings: 0,
    criticalCount: 0,
    startTime: null,
    repos: []
  },

  /**
   * Initialize dashboard functionality
   */
  init: function() {
    this.bindEvents();
    this.initializeSearch();
    this.loadInitialData();
  },

  /**
   * Bind event listeners
   */
  bindEvents: function() {
    // Search functionality
    const searchInput = document.getElementById('repo-search');
    if (searchInput) {
      searchInput.addEventListener('input', window.GVD.utils.debounce(this.handleSearch.bind(this), 300));
      searchInput.addEventListener('focus', this.showSearchResults.bind(this));
    }

    // Visibility filter
    const visibilityFilter = document.getElementById('repo-visibility-filter');
    if (visibilityFilter) {
      visibilityFilter.addEventListener('change', this.handleVisibilityFilter.bind(this));
    }

    // Scan all button
    const scanAllBtn = document.getElementById('scan-all-button');
    if (scanAllBtn) {
      scanAllBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleScanAll();
      });
    }

    // Repository detail buttons - direct binding for reliability
    const detailButtons = document.querySelectorAll('.repo-details-btn');
    detailButtons.forEach(button => {
      button.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleRepoDetails(button);
      });
    });

    // Repository scan buttons - direct binding for reliability
    const scanButtons = document.querySelectorAll('.repo-scan-btn');
    scanButtons.forEach(button => {
      button.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.handleRepoScan(button);
      });
    });

    // Report view buttons - NEW
    const reportButtons = document.querySelectorAll('.report-view-btn, [data-report-url]');
    reportButtons.forEach(button => {
      button.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const reportUrl = button.dataset.reportUrl || button.getAttribute('href');
        const reportTitle = button.dataset.reportTitle || 'Report';
        const reportType = button.dataset.reportType || 'json';
        
        if (reportUrl) {
          if (reportType === 'pdf') {
            this.openPdfReport(reportUrl, reportTitle);
          } else {
            this.openJsonReport(reportUrl, reportTitle);
          }
        }
      });
    });

    // Modal close handlers - IMPROVED
    document.addEventListener('click', (e) => {
      // Handle modal close buttons
      if (e.target.dataset.closeModal || e.target.closest('[data-close-modal]')) {
        e.preventDefault();
        const modal = e.target.closest('.modal-overlay');
        if (modal) {
          window.GVD.modal.close(modal.id);
        }
      }
      // Handle scan modal close buttons
      if (e.target.dataset.closeScanModal || e.target.closest('[data-close-scan-modal]')) {
        e.preventDefault();
        const modal = e.target.closest('.modal-overlay');
        if (modal) {
          window.GVD.modal.close(modal.id);
        }
      }
      // Handle click on modal backdrop
      if (e.target.classList.contains('modal-overlay')) {
        window.GVD.modal.close(e.target.id);
      }
    });

    // Search result clicks
    document.addEventListener('click', (e) => {
      if (e.target.closest('.search-result-item')) {
        this.handleSearchResultClick(e.target.closest('.search-result-item'));
      }
    });

    // Close search results when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-wrapper')) {
        this.hideSearchResults();
      }
    });

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        // Close any open modal
        const openModal = document.querySelector('.modal-overlay:not([hidden])');
        if (openModal) {
          window.GVD.modal.close(openModal.id);
        }
        // Close any open dropdowns
        window.GVD.dropdown.closeAll();
      }
    });
  },

  /**
   * Initialize search functionality
   */
  initializeSearch: function() {
    const searchInput = document.getElementById('repo-search');
    const searchResults = document.getElementById('search-results');
    
    if (searchInput && searchResults) {
      // Set up search results container
      searchResults.hidden = true;
    }
  },

  /**
   * Load initial data
   */
  loadInitialData: function() {
    // Load repositories from page data
    const repoCards = document.querySelectorAll('.repo-card');
    this.state.repos = Array.from(repoCards).map(card => ({
      element: card,
      name: card.querySelector('.repo-name')?.textContent?.trim(),
      visibility: card.dataset.visibility,
      owner: card.dataset.owner,
      repoUrl: card.dataset.repoUrl
    }));
  },

  /**
   * Handle search input
   */
  handleSearch: async function(e) {
    const query = e.target.value.trim();
    this.state.searchQuery = query;

    if (query.length < 2) {
      this.hideSearchResults();
      return;
    }

    try {
      await this.performSearch(query);
    } catch (error) {
      console.error('Search error:', error);
      this.showSearchError(error.message);
    }
  },

  /**
   * Perform repository search
   */
  performSearch: async function(query, loadMore = false) {
    const searchResults = document.getElementById('search-results');
    if (!searchResults) return;

    if (!loadMore) {
      this.state.searchPage = 1;
      this.showSearchLoading();
    }

    try {
      const visibilityFilter = document.getElementById('repo-visibility-filter');
      const visibility = visibilityFilter?.value === 'both' ? 'all' : visibilityFilter?.value || 'all';

      const params = new URLSearchParams({
        q: query,
        visibility: visibility,
        page: this.state.searchPage,
        per_page: '20'
      });

      const result = await window.GVD.utils.api.get(`/search?${params.toString()}`);
      this.renderSearchResults(result, loadMore);
      this.state.searchHasMore = result.has_next;
    } catch (error) {
      this.showSearchError(error.message);
    }
  },

  /**
   * Render search results
   */
  renderSearchResults: function(result, append = false) {
    const searchResults = document.getElementById('search-results');
    if (!searchResults) return;

    const repos = result.repos || [];
    
    if (!append && repos.length === 0) {
      this.showSearchEmpty();
      return;
    }

    const html = repos.map(repo => this.createSearchResultItem(repo)).join('');

    if (append) {
      searchResults.innerHTML += html;
    } else {
      searchResults.innerHTML = html;
    }

    if (this.state.searchHasMore) {
      searchResults.innerHTML += `
        <button class="search-load-more" id="search-load-more">
          Load more results
        </button>
      `;
    }

    searchResults.hidden = false;
    this.bindSearchResultEvents();
  },

  /**
   * Create search result item HTML
   */
  createSearchResultItem: function(repo) {
    return `
      <div class="search-result-item" data-owner="${repo.owner?.login}" data-repo="${repo.name}" data-repo-url="${repo.clone_url}">
        <div class="search-result-header">
          <h4>
            <a href="${repo.html_url || '#'}" target="_blank" rel="noopener noreferrer">
              ${window.GVD.utils.escapeHtml(repo.full_name || repo.name)}
            </a>
          </h4>
          <span class="badge badge-${repo.visibility}">${repo.visibility}</span>
        </div>
        <p class="search-result-description">
          ${window.GVD.utils.escapeHtml(repo.description || 'No description available')}
        </p>
        <div class="search-result-meta">
          <span>Language: ${window.GVD.utils.escapeHtml(repo.language || 'Unknown')}</span>
          <span>Stars: ${repo.stargazers_count || 0}</span>
        </div>
        <div class="search-result-actions">
          <button class="btn btn-ghost btn-sm search-details-btn">
            Details
          </button>
          <button class="btn btn-primary btn-sm search-scan-btn">
            Scan
          </button>
        </div>
      </div>
    `;
  },

  /**
   * Bind search result events
   */
  bindSearchResultEvents: function() {
    // Details buttons
    document.querySelectorAll('.search-details-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const item = e.target.closest('.search-result-item');
        const owner = item.dataset.owner;
        const repo = item.dataset.repo;
        this.handleRepoDetails(null, owner, repo);
      });
    });

    // Scan buttons
    document.querySelectorAll('.search-scan-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const item = e.target.closest('.search-result-item');
        const owner = item.dataset.owner;
        const repo = item.dataset.repo;
        const repoUrl = item.dataset.repoUrl;
        this.handleRepoScan(null, owner, repo, repoUrl);
      });
    });

    // Load more button
    const loadMoreBtn = document.getElementById('search-load-more');
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener('click', () => {
        this.state.searchPage++;
        this.performSearch(this.state.searchQuery, true);
        loadMoreBtn.remove();
      });
    }
  },

  /**
   * Handle search result click
   */
  handleSearchResultClick: function(item) {
    // Handle clicking on the search result item itself
    const link = item.querySelector('a[href]');
    if (link) {
      link.click();
    }
  },

  /**
   * Show search loading state
   */
  showSearchLoading: function() {
    const searchResults = document.getElementById('search-results');
    if (searchResults) {
      searchResults.innerHTML = '<div class="search-loading">Searching...</div>';
      searchResults.hidden = false;
    }
  },

  /**
   * Show search error
   */
  showSearchError: function(message) {
    const searchResults = document.getElementById('search-results');
    if (searchResults) {
      searchResults.innerHTML = `<div class="search-error">${window.GVD.utils.escapeHtml(message)}</div>`;
      searchResults.hidden = false;
    }
  },

  /**
   * Show search empty state
   */
  showSearchEmpty: function() {
    const searchResults = document.getElementById('search-results');
    if (searchResults) {
      searchResults.innerHTML = '<div class="search-empty">No repositories found</div>';
      searchResults.hidden = false;
    }
  },

  /**
   * Show search results
   */
  showSearchResults: function() {
    const searchResults = document.getElementById('search-results');
    if (searchResults && searchResults.innerHTML.trim()) {
      searchResults.hidden = false;
    }
  },

  /**
   * Hide search results
   */
  hideSearchResults: function() {
    const searchResults = document.getElementById('search-results');
    if (searchResults) {
      searchResults.hidden = true;
    }
  },

  /**
   * Handle visibility filter change
   */
  handleVisibilityFilter: function(e) {
    const visibility = e.target.value;
    this.state.currentFilter = visibility;
    
    // Update URL without page reload
    const url = new URL(window.location.href);
    url.searchParams.set('visibility', visibility);
    if (!url.searchParams.get('limit')) {
      url.searchParams.set('limit', '15');
    }
    window.location.href = url.toString();
  },

  /**
   * Handle repository details
   */
  handleRepoDetails: async function(button, owner, repo) {
    if (!owner || !repo) {
      // Extract from button if not provided
      owner = button?.dataset.owner;
      repo = button?.dataset.repo;
    }

    if (!owner || !repo) return;

    try {
      this.setModalLoadingState('repo-modal', repo);
      window.GVD.modal.open('repo-modal');
      
      const details = await window.GVD.utils.api.get(`/repo-details/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`);
      this.renderRepoDetails(details);
    } catch (error) {
      console.error('Failed to load repo details:', error);
      this.setModalErrorState('repo-modal', error.message);
    }
  },

  /**
   * Render repository details in modal
   */
  renderRepoDetails: function(details) {
    const modalTitle = document.getElementById('modal-title');
    const modalMeta = document.getElementById('modal-meta');
    const modalDescription = document.getElementById('modal-description');
    const modalReadme = document.getElementById('modal-readme');
    const modalLink = document.getElementById('modal-link');

    if (modalTitle) {
      modalTitle.textContent = details.full_name || details.name || 'Repository Details';
    }

    if (modalMeta) {
      const metaItems = [
        details.visibility || 'Unknown',
        `Language: ${details.language || 'Unknown'}`,
        `Branch: ${details.default_branch || 'main'}`,
        `Stars: ${details.stargazers_count || 0}`,
        `Forks: ${details.forks_count || 0}`,
        `Issues: ${details.open_issues_count || 0}`
      ];

      if (details.updated_at) {
        metaItems.push(`Updated: ${new Date(details.updated_at).toLocaleDateString()}`);
      }

      modalMeta.innerHTML = metaItems.map(item => 
        `<span class="modal-meta-item">${window.GVD.utils.escapeHtml(item)}</span>`
      ).join('');
    }

    if (modalDescription) {
      modalDescription.textContent = details.description || 'No description provided.';
    }

    if (modalReadme) {
      modalReadme.textContent = details.readme || 'README not available for this repository.';
    }

    if (modalLink) {
      modalLink.href = details.html_url || '#';
      modalLink.hidden = !details.html_url;
    }
  },

  /**
   * Handle repository scan
   */
  handleRepoScan: async function(button, owner, repo, repoUrl) {
    if (!owner || !repo) {
      // Extract from button if not provided
      owner = button?.dataset.owner;
      repo = button?.dataset.repo;
      repoUrl = button?.dataset.repoUrl;
    }

    if (!owner || !repo) return;

    try {
      this.setScanLoadingState(repo);
      window.GVD.modal.open('scan-modal');
      
      const result = await window.GVD.utils.api.post('/scan', {
        owner: owner,
        repo_name: repo,
        repo_url: repoUrl
      });

      this.renderScanResults(result, repo);
    } catch (error) {
      console.error('Scan failed:', error);
      this.setScanErrorState(repo, error.message);
    }
  },

  /**
   * Handle scan all repositories
   */
  handleScanAll: async function() {
    // Open modal immediately
    window.GVD.modal.open('bulk-scan-modal');
    
    // Reset state
    this.bulkScanState = {
      scanning: true,
      completed: 0,
      failures: 0,
      totalFindings: 0,
      criticalCount: 0,
      startTime: Date.now(),
      repos: Array.from(document.querySelectorAll('.repo-card')).map(card => ({
        owner: card.dataset.owner,
        name: card.querySelector('.repo-name')?.textContent?.trim(),
        repoUrl: card.dataset.repoUrl
      }))
    };

    // Reset UI
    this.resetBulkScanUI();

    // Start sequential scanning
    this.startBulkScan();
  },

  /**
   * Reset bulk scan UI
   */
  resetBulkScanUI: function() {
    document.getElementById('bulk-progress-bar').style.width = '0%';
    document.getElementById('bulk-progress-text').textContent = '0 / ' + this.bulkScanState.repos.length + ' repositories scanned';
    document.getElementById('bulk-stat-completed').textContent = '0';
    document.getElementById('bulk-stat-findings').textContent = '0';
    document.getElementById('bulk-stat-critical').textContent = '0';
    document.getElementById('bulk-stat-failures').textContent = '0';
    
    const logsPanel = document.getElementById('bulk-scan-logs');
    logsPanel.innerHTML = '<div class="log-entry log-entry-info"><span class="log-time">00:00:00</span><span class="log-message">Initializing bulk scan...</span></div>';
  },

  /**
   * Start bulk scanning process
   */
  startBulkScan: async function() {
    const state = this.bulkScanState;
    const totalRepos = state.repos.length;

    if (totalRepos === 0) {
      this.addBulkLog('No repositories to scan', 'warning');
      return;
    }

    this.addBulkLog('Starting scan across ' + totalRepos + ' repositories', 'info');

    // Iterate repositories sequentially
    for (let i = 0; i < totalRepos; i++) {
      const repo = state.repos[i];
      
      if (!state.scanning) {
        this.addBulkLog('Scan cancelled by user', 'warning');
        break;
      }

      this.addBulkLog('Scanning: ' + repo.owner + '/' + repo.name, 'info');

      try {
        const result = await window.GVD.utils.api.post('/scan', {
          owner: repo.owner,
          repo_name: repo.name,
          repo_url: repo.repoUrl
        });

        // Update state
        state.completed++;
        state.totalFindings += result.total_findings || 0;
        const counts = result.severity_counts || {};
        state.criticalCount += (counts.CRITICAL || 0) + (counts.HIGH || 0);

        const findings = result.total_findings || 0;
        const message = findings > 0 
          ? findings + ' finding' + (findings !== 1 ? 's' : '')
          : 'clean';
        
        this.addBulkLog('✓ ' + repo.owner + '/' + repo.name + ': ' + message, 'success');
      } catch (error) {
        state.failures++;
        this.addBulkLog('✗ ' + repo.owner + '/' + repo.name + ': ' + error.message, 'error');
      }

      // Update progress UI
      this.updateBulkProgress();
    }

    // Complete
    state.scanning = false;
    const elapsed = Math.floor((Date.now() - state.startTime) / 1000);
    this.addBulkLog('Scan complete in ' + elapsed + 's (' + state.completed + ' succeeded, ' + state.failures + ' failed)', 'success');
  },

  /**
   * Update bulk progress UI
   */
  updateBulkProgress: function() {
    const state = this.bulkScanState;
    const total = state.repos.length;
    const percent = (state.completed / total) * 100;

    document.getElementById('bulk-progress-bar').style.width = percent + '%';
    document.getElementById('bulk-progress-text').textContent = state.completed + ' / ' + total + ' repositories scanned';
    document.getElementById('bulk-stat-completed').textContent = state.completed;
    document.getElementById('bulk-stat-findings').textContent = state.totalFindings;
    document.getElementById('bulk-stat-critical').textContent = state.criticalCount;
    document.getElementById('bulk-stat-failures').textContent = state.failures;
  },

  /**
   * Add log entry
   */
  addBulkLog: function(message, type = 'info') {
    const logsPanel = document.getElementById('bulk-scan-logs');
    if (!logsPanel) return;

    const elapsed = Math.floor((Date.now() - (this.bulkScanState?.startTime || Date.now())) / 1000);
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

  /**
   * Set modal loading state
   */
  setModalLoadingState: function(modalId, repoName) {
    const modalTitle = document.getElementById(`${modalId.replace('-modal', '')}-title`);
    const modalMeta = document.getElementById(`${modalId.replace('-modal', '')}-meta`);
    const modalDescription = document.getElementById(`${modalId.replace('-modal', '')}-description`);
    const modalReadme = document.getElementById(`${modalId.replace('-modal', '')}-readme`);

    if (modalTitle) modalTitle.textContent = `Loading ${repoName}...`;
    if (modalMeta) modalMeta.innerHTML = '';
    if (modalDescription) modalDescription.textContent = 'Loading repository details...';
    if (modalReadme) modalReadme.textContent = 'Loading README...';
  },

  /**
   * Set modal error state
   */
  setModalErrorState: function(modalId, errorMessage) {
    const modalDescription = document.getElementById(`${modalId.replace('-modal', '')}-description`);
    const modalReadme = document.getElementById(`${modalId.replace('-modal', '')}-readme`);

    if (modalDescription) modalDescription.textContent = 'Failed to load repository details.';
    if (modalReadme) modalReadme.textContent = errorMessage;
  },

  /**
   * Set scan loading state
   */
  setScanLoadingState: function(repoName) {
    const modalTitle = document.getElementById('scan-modal-title');
    const scanMeta = document.getElementById('scan-meta');
    const scanSummary = document.getElementById('scan-summary');
    const scanFindings = document.getElementById('scan-findings');
    const scanOutput = document.getElementById('scan-output');

    if (modalTitle) modalTitle.textContent = `Scanning ${repoName}`;
    if (scanMeta) scanMeta.innerHTML = '';
    if (scanSummary) scanSummary.textContent = 'Cloning repository and running security scan...';
    if (scanFindings) scanFindings.innerHTML = '<p class="text-muted">Scan in progress...</p>';
    if (scanOutput) scanOutput.textContent = 'Initializing scanner...';
  },

  /**
   * Set scan error state
   */
  setScanErrorState: function(repoName, errorMessage) {
    const modalTitle = document.getElementById('scan-modal-title');
    const scanSummary = document.getElementById('scan-summary');
    const scanFindings = document.getElementById('scan-findings');
    const scanOutput = document.getElementById('scan-output');

    if (modalTitle) modalTitle.textContent = `Scan Failed - ${repoName}`;
    if (scanSummary) scanSummary.textContent = 'The scan could not be completed.';
    if (scanFindings) scanFindings.innerHTML = `<p class="text-error">${window.GVD.utils.escapeHtml(errorMessage)}</p>`;
    if (scanOutput) scanOutput.textContent = errorMessage;
  },

  /**
   * Render scan results
   */
  renderScanResults: function(result, repoName) {
    const modalTitle = document.getElementById('scan-modal-title');
    const scanMeta = document.getElementById('scan-meta');
    const scanSummary = document.getElementById('scan-summary');
    const scanFindings = document.getElementById('scan-findings');
    const scanOutput = document.getElementById('scan-output');
    const scanViewJson = document.getElementById('scan-view-json');
    const scanViewPdf = document.getElementById('scan-view-pdf');
    const scanDownloadJson = document.getElementById('scan-download-json');
    const scanDownloadPdf = document.getElementById('scan-download-pdf');

    if (modalTitle) {
      modalTitle.textContent = `Scan Results - ${result.repo_name || repoName}`;
    }

    if (scanMeta) {
      const counts = result.severity_counts || {};
      const metaItems = [
        `Repository: ${result.repo_name || repoName}`,
        `Total Findings: ${result.total_findings || 0}`,
        `Critical: ${counts.CRITICAL || 0}`,
        `High: ${counts.HIGH || 0}`,
        `Medium: ${counts.MEDIUM || 0}`,
        `Low: ${counts.LOW || 0}`
      ];

      scanMeta.innerHTML = metaItems.map(item => 
        `<span class="modal-meta-item">${window.GVD.utils.escapeHtml(item)}</span>`
      ).join('');
    }

    if (scanSummary) {
      const findings = result.total_findings || 0;
      scanSummary.textContent = findings > 0 
        ? `Scan completed and found ${findings} potential issue${findings !== 1 ? 's' : ''}.`
        : 'Scan completed and no vulnerabilities were found.';
    }

    if (scanFindings) {
      this.renderFindings(result.findings || []);
    }

    if (scanOutput) {
      scanOutput.textContent = result.command_output || 'No scanner output captured.';
    }

    // Show download/view buttons if reports are available
    const hasReports = result.report_urls && Object.keys(result.report_urls).length > 0;
    if (hasReports) {
      this.setupReportButtons(result.report_urls, result.repo_name || repoName);
    }
  },

  /**
   * Render findings
   */
  renderFindings: function(findings) {
    const scanFindings = document.getElementById('scan-findings');
    if (!scanFindings) return;

    if (!findings.length) {
      scanFindings.innerHTML = '<p class="text-muted">No vulnerabilities were found in this repository.</p>';
      return;
    }

    const html = findings.map(finding => `
      <div class="finding-item">
        <div class="finding-header">
          <span class="finding-severity finding-severity-${(finding.severity || '').toLowerCase()}">
            ${window.GVD.utils.escapeHtml(finding.severity || 'Unknown')}
          </span>
          <span class="finding-type">${window.GVD.utils.escapeHtml(finding.secret_type || 'Unknown type')}</span>
        </div>
        <div class="finding-path">${window.GVD.utils.escapeHtml(finding.file_path || 'Unknown file')}</div>
        <div class="finding-meta">
          Commit: ${window.GVD.utils.escapeHtml(finding.commit_hash || 'N/A')}
          ${finding.line_number ? ` · Line: ${finding.line_number}` : ''}
        </div>
        <div class="finding-fix">${window.GVD.utils.escapeHtml(finding.fix_recommendation || 'No recommendation provided.')}</div>
      </div>
    `).join('');

    scanFindings.innerHTML = html;
  },

  /**
   * Setup report download/view buttons
   */
  setupReportButtons: function(reportUrls, repoName) {
    const buttons = {
      viewJson: document.getElementById('scan-view-json'),
      viewPdf: document.getElementById('scan-view-pdf'),
      downloadJson: document.getElementById('scan-download-json'),
      downloadPdf: document.getElementById('scan-download-pdf')
    };

    // Show buttons
    Object.values(buttons).forEach(btn => {
      if (btn) btn.hidden = false;
    });

    // Setup JSON report
    if (reportUrls.view_json) {
      if (buttons.viewJson) {
        buttons.viewJson.onclick = () => this.openJsonReport(reportUrls.view_json, `${repoName} - JSON Report`);
      }
      if (buttons.downloadJson) {
        buttons.downloadJson.href = reportUrls.download_json || reportUrls.view_json;
      }
    }

    // Setup PDF report
    if (reportUrls.view_pdf) {
      if (buttons.viewPdf) {
        buttons.viewPdf.onclick = () => this.openPdfReport(reportUrls.view_pdf, `${repoName} - PDF Report`);
      }
      if (buttons.downloadPdf) {
        buttons.downloadPdf.href = reportUrls.download_pdf || reportUrls.view_pdf;
      }
    }
  },

  /**
   * Open JSON report in modal
   */
  openJsonReport: async function(url, title) {
    try {
      const text = await fetch(url).then(res => res.text());
      let formattedText;
      
      try {
        const parsed = JSON.parse(text);
        formattedText = JSON.stringify(parsed, null, 2);
      } catch {
        formattedText = text;
      }

      // Open modal and show the JSON
      window.GVD.modal.open('report-viewer-modal');
      const reportTitle = document.getElementById('report-viewer-title');
      const reportContent = document.getElementById('report-content');
      
      if (reportTitle) {
        reportTitle.textContent = title || 'JSON Report';
      }
      
      if (reportContent) {
        reportContent.innerHTML = `<pre class="code-block">${window.GVD.utils.escapeHtml(formattedText)}</pre>`;
      }
    } catch (error) {
      console.error('Failed to load JSON report:', error);
      window.GVD.toast.show('Failed to load report', 'error');
    }
  },

  /**
   * Open PDF report in modal
   */
  openPdfReport: async function(url, title) {
    try {
      window.GVD.modal.open('report-viewer-modal');
      const reportTitle = document.getElementById('report-viewer-title');
      const reportContent = document.getElementById('report-content');
      
      if (reportTitle) {
        reportTitle.textContent = title || 'PDF Report';
      }
      
      if (reportContent) {
        // Show loading state
        reportContent.innerHTML = `
          <div class="pdf-loading">
            <div class="pdf-loading-spinner"></div>
            <p>Loading PDF report...</p>
          </div>
        `;
        
        // First verify the PDF URL is accessible
        try {
          const response = await fetch(url, { method: 'HEAD' });
          if (!response.ok) {
            throw new Error(`PDF not accessible: ${response.status}`);
          }
          
          // Check if it's actually a PDF
          const contentType = response.headers.get('content-type');
          if (!contentType || !contentType.includes('application/pdf')) {
            throw new Error('URL does not point to a PDF file');
          }
        } catch (verifyError) {
          console.error('PDF verification failed:', verifyError);
          reportContent.innerHTML = `
            <div class="pdf-error">
              <h3>PDF Not Found</h3>
              <p>The PDF report could not be found or accessed.</p>
              <p><strong>Error:</strong> ${verifyError.message}</p>
              <div class="pdf-error-actions">
                <a href="${url}" target="_blank" class="btn btn-primary">
                  Try Opening in New Tab
                </a>
                <button class="btn btn-secondary" onclick="window.GVD.modal.close('report-viewer-modal')">
                  Close
                </button>
              </div>
            </div>
          `;
          return;
        }
        
        // Create multiple PDF viewer options for better compatibility
        const createPdfViewer = () => {
          const container = document.createElement('div');
          container.className = 'pdf-viewer-container';
          container.style.cssText = `
            width: 100%;
            height: 70vh;
            display: flex;
            flex-direction: column;
          `;
          
          // Try iframe first
          const iframe = document.createElement('iframe');
          iframe.src = url;
          iframe.className = 'pdf-viewer-iframe';
          iframe.style.cssText = `
            width: 100%;
            height: 100%;
            border: 1px solid var(--color-border-primary);
            border-radius: var(--radius-lg);
            background: white;
          `;
          
          // Add error handling to iframe
          iframe.onerror = () => {
            console.warn('Iframe PDF loading failed, trying embed');
            createEmbedViewer();
          };
          
          container.appendChild(iframe);
          return container;
        };
        
        const createEmbedViewer = () => {
          const embed = document.createElement('embed');
          embed.src = url;
          embed.type = 'application/pdf';
          embed.className = 'pdf-viewer-embed';
          embed.style.cssText = `
            width: 100%;
            height: 70vh;
            border: 1px solid var(--color-border-primary);
            border-radius: var(--radius-lg);
            background: white;
          `;
          
          reportContent.innerHTML = '';
          reportContent.appendChild(embed);
        };
        
        const createObjectViewer = () => {
          const object = document.createElement('object');
          object.data = url;
          object.type = 'application/pdf';
          object.className = 'pdf-viewer-object';
          object.style.cssText = `
            width: 100%;
            height: 70vh;
            border: 1px solid var(--color-border-primary);
            border-radius: var(--radius-lg);
            background: white;
          `;
          
          // Fallback content for object
          object.innerHTML = `
            <div class="pdf-error">
              <h3>PDF Viewer Not Supported</h3>
              <p>Your browser doesn't support PDF viewing.</p>
              <div class="pdf-error-actions">
                <a href="${url}" target="_blank" class="btn btn-primary">
                  Open PDF in New Tab
                </a>
                <a href="${url}" download class="btn btn-secondary">
                  Download PDF
                </a>
              </div>
            </div>
          `;
          
          reportContent.innerHTML = '';
          reportContent.appendChild(object);
        };
        
        // Try iframe first, then fallback to embed, then object
        const pdfViewer = createPdfViewer();
        
        // Set a timeout to check if iframe loaded
        const checkIframeLoaded = () => {
          const iframe = pdfViewer.querySelector('iframe');
          if (iframe && !iframe.contentDocument && !iframe.contentWindow) {
            console.warn('Iframe failed to load, trying embed viewer');
            createEmbedViewer();
          }
        };
        
        // Replace loading state with viewer
        setTimeout(() => {
          if (reportContent.querySelector('.pdf-loading')) {
            reportContent.innerHTML = '';
            reportContent.appendChild(pdfViewer);
            
            // Check iframe loading after a delay
            setTimeout(checkIframeLoaded, 2000);
          }
        }, 1000);
        
        // Final fallback to object if everything fails
        setTimeout(() => {
          if (reportContent.querySelector('.pdf-loading')) {
            console.warn('All viewers failed, using object fallback');
            createObjectViewer();
          }
        }, 5000);
      }
    } catch (error) {
      console.error('Failed to load PDF report:', error);
      window.GVD.toast.show('Failed to load PDF report', 'error');
      
      // Show error in modal
      const reportContent = document.getElementById('report-content');
      if (reportContent) {
        reportContent.innerHTML = `
          <div class="pdf-error">
            <h3>PDF Loading Error</h3>
            <p>An error occurred while loading the PDF report.</p>
            <p><strong>Error:</strong> ${error.message}</p>
            <div class="pdf-error-actions">
              <button class="btn btn-secondary" onclick="window.GVD.modal.close('report-viewer-modal')">
                Close
              </button>
            </div>
          </div>
        `;
      }
    }
  }
};

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  window.GVD.dashboard.init();
});
