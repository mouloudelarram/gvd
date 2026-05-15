/* ========================================================================
   GVD Bulk Scan & Notifications - JavaScript Handler
   ======================================================================== */

(function() {
  'use strict';

  /* ====================================================================
     NOTIFICATION SYSTEM
     ==================================================================== */

  const NotificationSystem = {
    notifications: [],
    maxNotifications: 50,
    
    init() {
      this.setupDOM();
      this.attachEventListeners();
      this.startPolling();
    },
    
    setupDOM() {
      const notificationButton = document.querySelector('[data-notification-button]');
      if (!notificationButton) {
        this.createNotificationUI();
      }
    },
    
    createNotificationUI() {
      const navbar = document.querySelector('.navbar') || document.querySelector('nav');
      if (!navbar) return;
      
      const notificationHTML = `
        <div class="notification-container" style="position: relative;">
          <button id="notifications-button" class="btn btn-icon" data-notification-button title="Notifications">
            <span id="notifications-icon">🔔</span>
            <span id="notifications-badge" hidden>0</span>
          </button>
          <div id="notifications-dropdown" class="notifications-dropdown" hidden>
            <div id="notifications-list"></div>
          </div>
        </div>
      `;
      
      const rightSection = navbar.querySelector('.navbar-right') || navbar;
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = notificationHTML;
      rightSection.insertBefore(tempDiv.firstElementChild, rightSection.firstChild);
      
      this.attachEventListeners();
    },
    
    attachEventListeners() {
      const button = document.getElementById('notifications-button');
      const dropdown = document.getElementById('notifications-dropdown');
      
      if (button && dropdown) {
        button.addEventListener('click', (e) => {
          e.stopPropagation();
          dropdown.toggleAttribute('hidden');
        });
        
        document.addEventListener('click', () => {
          if (!dropdown.hasAttribute('hidden')) {
            dropdown.setAttribute('hidden', '');
          }
        });
      }
    },
    
    async fetchNotifications() {
      try {
        const response = await fetch('/api/notifications');
        if (!response.ok) return;
        
        const data = await response.json();
        this.updateNotifications(data.notifications || []);
      } catch (error) {
        console.error('Failed to fetch notifications:', error);
      }
    },
    
    updateNotifications(newNotifications) {
      this.notifications = newNotifications.slice(0, this.maxNotifications);
      this.render();
    },
    
    addNotification(notification) {
      this.notifications.unshift({
        id: Date.now(),
        timestamp: new Date().toISOString(),
        ...notification
      });
      
      if (this.notifications.length > this.maxNotifications) {
        this.notifications.pop();
      }
      
      this.render();
    },
    
    render() {
      const badge = document.getElementById('notifications-badge');
      const list = document.getElementById('notifications-list');
      
      if (!list) return;
      
      const unreadCount = this.notifications.filter(n => !n.read).length;
      
      if (badge) {
        if (unreadCount > 0) {
          badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
          badge.removeAttribute('hidden');
        } else {
          badge.setAttribute('hidden', '');
        }
      }
      
      if (this.notifications.length === 0) {
        list.innerHTML = '<div class="notification-empty">No notifications</div>';
        return;
      }
      
      list.innerHTML = this.notifications.map(notification => this.renderNotification(notification)).join('');
    },
    
    renderNotification(notification) {
      const timeAgo = this.formatTimeAgo(new Date(notification.timestamp));
      const unreadClass = notification.read ? '' : ' unread';
      
      return `
        <div class="notification-item${unreadClass}" data-notification-id="${notification.id}">
          <div class="notification-content">
            <div class="notification-title">${notification.title || 'Notification'}</div>
            ${notification.message ? `<div class="notification-message">${notification.message}</div>` : ''}
            <div class="notification-time">${timeAgo}</div>
          </div>
        </div>
      `;
    },
    
    formatTimeAgo(date) {
      const seconds = Math.floor((new Date() - date) / 1000);
      
      if (seconds < 60) return 'just now';
      if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
      if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
      return `${Math.floor(seconds / 86400)}d ago`;
    },
    
    startPolling() {
      this.fetchNotifications();
      setInterval(() => this.fetchNotifications(), 30000);
    }
  };

  /* ====================================================================
     BULK SCAN SYSTEM
     ==================================================================== */

  const BulkScanSystem = {
    isScanning: false,
    currentSessionId: null,
    stats: {
      scanned: 0,
      critical: 0,
      high: 0,
      medium: 0,
      low: 0
    },
    logs: [],
    maxLogs: 100,
    
    init() {
      this.attachEventListeners();
    },
    
    attachEventListeners() {
      const startButton = document.getElementById('start-bulk-scan');
      if (startButton) {
        startButton.addEventListener('click', () => this.startBulkScan());
      }
      
      const stopButton = document.getElementById('stop-bulk-scan');
      if (stopButton) {
        stopButton.addEventListener('click', () => this.stopBulkScan());
      }
    },
    
    async startBulkScan() {
      try {
        this.isScanning = true;
        this.currentSessionId = this.generateSessionId();
        this.resetStats();
        this.logs = [];
        
        this.addLog('info', 'Starting bulk scan session...');
        this.showBulkScanModal();
        this.updateUI();
        
        const response = await fetch('/api/bulk-scan/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionId: this.currentSessionId })
        });
        
        if (!response.ok) throw new Error('Failed to start bulk scan');
        
        this.addLog('success', 'Bulk scan session initialized');
        this.monitorScanProgress();
      } catch (error) {
        this.addLog('error', `Failed to start scan: ${error.message}`);
        this.isScanning = false;
      }
    },
    
    async stopBulkScan() {
      try {
        const response = await fetch('/api/bulk-scan/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionId: this.currentSessionId })
        });
        
        if (!response.ok) throw new Error('Failed to stop scan');
        
        this.addLog('warning', 'Bulk scan stopped by user');
        this.isScanning = false;
        this.updateUI();
      } catch (error) {
        this.addLog('error', `Failed to stop scan: ${error.message}`);
      }
    },
    
    async monitorScanProgress() {
      if (!this.isScanning || !this.currentSessionId) return;
      
      try {
        const response = await fetch(`/api/bulk-scan/progress/${this.currentSessionId}`);
        if (!response.ok) throw new Error('Failed to fetch progress');
        
        const data = await response.json();
        
        if (data.status === 'completed') {
          this.handleScanComplete(data);
        } else if (data.status === 'in_progress') {
          this.updateScanProgress(data);
          setTimeout(() => this.monitorScanProgress(), 2000);
        }
      } catch (error) {
        this.addLog('error', `Monitoring error: ${error.message}`);
      }
    },
    
    updateScanProgress(data) {
      this.stats = data.stats || this.stats;
      if (data.logs) {
        data.logs.forEach(log => {
          if (!this.logs.some(l => l.timestamp === log.timestamp)) {
            this.logs.push(log);
          }
        });
      }
      this.updateUI();
    },
    
    handleScanComplete(data) {
      this.isScanning = false;
      this.stats = data.stats || this.stats;
      this.addLog('success', `Scan completed! Scanned ${this.stats.scanned} repositories`);
      this.updateUI();
      this.enableReportButtons();
    },
    
    showBulkScanModal() {
      const modal = document.getElementById('bulk-scan-modal');
      if (modal) {
        modal.classList.remove('hidden');
      }
    },
    
    updateUI() {
      this.updateProgressBar();
      this.updateStats();
      this.updateLogs();
    },
    
    updateProgressBar() {
      const progressBar = document.querySelector('.progress-bar');
      const progressText = document.querySelector('.bulk-scan-progress-text');
      
      if (progressBar && progressText) {
        const progress = this.stats.scanned > 0 ? Math.min((this.stats.scanned / 100) * 100, 100) : 0;
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `${progress.toFixed(0)}% - Scanning repositories...`;
      }
    },
    
    updateStats() {
      const stats = ['critical', 'high', 'medium', 'low', 'scanned'];
      stats.forEach(stat => {
        const element = document.querySelector(`[data-stat="${stat}"]`);
        if (element) {
          element.textContent = this.stats[stat] || 0;
        }
      });
    },
    
    updateLogs() {
      const logsContainer = document.querySelector('.bulk-scan-logs');
      if (!logsContainer) return;
      
      logsContainer.innerHTML = this.logs.slice(-this.maxLogs).map(log => `
        <div class="log-entry log-entry-${log.level}">
          <span class="log-time">[${this.formatTime(log.timestamp)}]</span>
          <span class="log-message">${log.message}</span>
        </div>
      `).join('');
      
      logsContainer.scrollTop = logsContainer.scrollHeight;
    },
    
    addLog(level, message) {
      this.logs.push({
        level,
        message,
        timestamp: new Date()
      });
      
      if (this.logs.length > this.maxLogs) {
        this.logs.shift();
      }
      
      this.updateLogs();
    },
    
    formatTime(date) {
      if (typeof date === 'string') date = new Date(date);
      return date.toLocaleTimeString('en-US', { hour12: false });
    },
    
    enableReportButtons() {
      ['view-json', 'view-pdf', 'download-json', 'download-pdf'].forEach(action => {
        const button = document.getElementById(`bulk-scan-${action}`);
        if (button) button.disabled = false;
      });
    },
    
    resetStats() {
      this.stats = { scanned: 0, critical: 0, high: 0, medium: 0, low: 0 };
    },
    
    generateSessionId() {
      return `scan_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
  };

  /* ====================================================================
     INITIALIZATION
     ==================================================================== */

  document.addEventListener('DOMContentLoaded', () => {
    NotificationSystem.init();
    BulkScanSystem.init();
  });

  /* ====================================================================
     GLOBAL EXPORTS
     ==================================================================== */

  window.NotificationSystem = NotificationSystem;
  window.BulkScanSystem = BulkScanSystem;
})();
