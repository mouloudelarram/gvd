/**
 * GVD Professional Design System - Base JavaScript
 * Core functionality for the SaaS application
 */

// Global state
window.GVD = {
  state: {
    user: null,
    isLoading: false,
    modals: {},
    toasts: []
  },
  
  // Utility functions
  utils: {
    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml: function(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    },

    /**
     * Debounce function calls
     */
    debounce: function(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    },

    /**
     * Format date relative to now
     */
    timeAgo: function(dateString) {
      const date = new Date(dateString);
      const now = new Date();
      const seconds = Math.floor((now - date) / 1000);
      
      if (seconds < 60) return 'just now';
      if (seconds < 3600) return Math.floor(seconds / 60) + ' minutes ago';
      if (seconds < 86400) return Math.floor(seconds / 3600) + ' hours ago';
      if (seconds < 2592000) return Math.floor(seconds / 86400) + ' days ago';
      if (seconds < 31536000) return Math.floor(seconds / 2592000) + ' months ago';
      return Math.floor(seconds / 31536000) + ' years ago';
    },

    /**
     * Make API requests with error handling
     */
    api: {
      get: async function(url) {
        try {
          const response = await fetch(url);
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }
          return await response.json();
        } catch (error) {
          console.error('API GET error:', error);
          throw error;
        }
      },

      post: async function(url, data) {
        try {
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
          });
          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || errorData.details || `HTTP ${response.status}: ${response.statusText}`);
          }
          return await response.json();
        } catch (error) {
          console.error('API POST error:', error);
          throw error;
        }
      }
    }
  },

  // Modal management
  modal: {
    /**
     * Open a modal
     */
    open: function(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) {
        console.warn(`Modal with ID "${modalId}" not found`);
        return;
      }
      
      // Show modal
      modal.hidden = false;
      modal.style.display = 'flex';
      document.body.classList.add('modal-open');
      window.GVD.state.modals[modalId] = true;
      
      // Focus management
      setTimeout(() => {
        const focusableElements = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusableElements.length > 0) {
          focusableElements[0].focus();
        }
      }, 100);
      
      // Add event listeners
      this.addEventListeners(modalId);
    },

    /**
     * Close a modal
     */
    close: function(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      
      modal.hidden = true;
      modal.style.display = 'none';
      document.body.classList.remove('modal-open');
      window.GVD.state.modals[modalId] = false;
      
      // Remove event listeners
      this.removeEventListeners(modalId);
    },

    /**
     * Add modal event listeners
     */
    addEventListeners: function(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;

      // Close on backdrop click
      const backdrop = modal.querySelector('.modal__backdrop, .modal-overlay');
      if (backdrop) {
        backdrop.addEventListener('click', () => this.close(modalId), { once: true });
      }

      // Close on escape key
      const escapeHandler = (e) => {
        if (e.key === 'Escape') {
          this.close(modalId);
          document.removeEventListener('keydown', escapeHandler);
        }
      };
      document.addEventListener('keydown', escapeHandler);

      // Store handler for cleanup
      modal._escapeHandler = escapeHandler;
    },

    /**
     * Remove modal event listeners
     */
    removeEventListeners: function(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal || !modal._escapeHandler) return;

      document.removeEventListener('keydown', modal._escapeHandler);
      delete modal._escapeHandler;
    }
  },

  // Toast notifications
  toast: {
    /**
     * Show a toast notification
     */
    show: function(message, type = 'info', duration = 5000) {
      const container = document.getElementById('toast-container');
      if (!container) return;

      const toast = document.createElement('div');
      toast.className = `toast toast-${type}`;
      toast.innerHTML = `
        <div class="toast-content">
          ${this.getIcon(type)}
          <span>${window.GVD.utils.escapeHtml(message)}</span>
        </div>
      `;

      container.appendChild(toast);

      // Auto remove after duration
      setTimeout(() => {
        this.remove(toast);
      }, duration);

      // Allow manual dismiss
      toast.addEventListener('click', () => {
        this.remove(toast);
      });

      window.GVD.state.toasts.push(toast);
    },

    /**
     * Remove a toast
     */
    remove: function(toast) {
      if (toast && toast.parentNode) {
        toast.style.animation = 'toastSlideOut 0.3s ease-out';
        setTimeout(() => {
          if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
          }
          const index = window.GVD.state.toasts.indexOf(toast);
          if (index > -1) {
            window.GVD.state.toasts.splice(index, 1);
          }
        }, 300);
      }
    },

    /**
     * Get icon for toast type
     */
    getIcon: function(type) {
      const icons = {
        success: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M13.5 4.5L6 12L2.5 8.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        error: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 2v6M8 10v4M3 8h6M10 8h3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        warning: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 1l6 10H2L8 1z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 5v3M8 10h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        info: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2"/><path d="M8 6v2M8 10h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      };
      return icons[type] || icons.info;
    }
  },

  // Dropdown management
  dropdown: {
    /**
     * Toggle dropdown
     */
    toggle: function(dropdownId) {
      // Try to find by ID first
      let dropdown = document.getElementById(dropdownId);
      
      // If not found, try to find by class or as menu
      if (!dropdown) {
        dropdown = document.querySelector(`#${dropdownId}, .dropdown-menu#${dropdownId}, .dropdown[id="${dropdownId}"]`);
      }
      
      if (!dropdown) {
        return;
      }

      // Check if we're dealing with the menu or the container
      const isMenu = dropdown.classList.contains('dropdown-menu');
      const dropdownContainer = isMenu ? dropdown.closest('.dropdown') : dropdown;
      
      if (!dropdownContainer) {
        return;
      }
      
      const isOpen = dropdownContainer.classList.contains('open');
      
      // Close all other dropdowns
      this.closeAll();
      
      if (!isOpen) {
        dropdownContainer.classList.add('open');
        
        // Add a small delay before adding the outside click listener
        setTimeout(() => {
          document.addEventListener('click', this.handleOutsideClick);
        }, 10);
      }
    },

    /**
     * Close all dropdowns
     */
    closeAll: function() {
      document.querySelectorAll('.dropdown.open').forEach(dropdown => {
        dropdown.classList.remove('open');
      });
      document.removeEventListener('click', this.handleOutsideClick);
    },

    /**
     * Handle outside click
     */
    handleOutsideClick: function(e) {
      if (!e.target.closest('.dropdown')) {
        window.GVD.dropdown.closeAll();
      }
    }
  },

  // Loading states
  loading: {
    /**
     * Show loading state on element
     */
    show: function(element) {
      if (typeof element === 'string') {
        element = document.getElementById(element);
      }
      if (element) {
        element.classList.add('loading');
      }
    },

    /**
     * Hide loading state on element
     */
    hide: function(element) {
      if (typeof element === 'string') {
        element = document.getElementById(element);
      }
      if (element) {
        element.classList.remove('loading');
      }
    }
  }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  // Initialize dropdowns - FIXED VERSION
  document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
    toggle.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      const dropdown = this.closest('.dropdown');
      if (dropdown) {
        // Use the dropdown's ID or generate one
        const dropdownId = dropdown.id || `dropdown-${Date.now()}`;
        dropdown.id = dropdownId;
        window.GVD.dropdown.toggle(dropdownId);
      }
    });
  });

  // Initialize notifications button
  const notificationsBtn = document.getElementById('notifications-btn');
  if (notificationsBtn) {
    notificationsBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      // For now, just show a toast that notifications are coming soon
      window.GVD.toast.show('Notifications coming soon!', 'info');
    });
  }

  // Initialize modal close buttons
  document.querySelectorAll('[data-close-modal]').forEach(button => {
    button.addEventListener('click', function() {
      const modal = this.closest('.modal-overlay');
      if (modal) {
        window.GVD.modal.close(modal.id);
      }
    });
  });

  // Initialize scan modal close buttons
  document.querySelectorAll('[data-close-scan-modal]').forEach(button => {
    button.addEventListener('click', function() {
      const modal = this.closest('.modal-overlay');
      if (modal) {
        window.GVD.modal.close(modal.id);
      }
    });
  });

  // Initialize user dropdown - SPECIFIC HANDLER
  const userDropdownToggle = document.getElementById('user-dropdown-toggle');
  if (userDropdownToggle) {
    userDropdownToggle.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      
      // Find the parent dropdown
      const dropdown = this.closest('.dropdown');
      if (dropdown) {
        // Ensure the dropdown menu has an ID
        const dropdownMenu = dropdown.querySelector('.dropdown-menu');
        if (dropdownMenu) {
          const menuId = dropdownMenu.id || 'user-dropdown';
          dropdownMenu.id = menuId;
          window.GVD.dropdown.toggle(menuId);
        }
      }
    });
  }

  // Initialize logout link - FIXED HANDLER
  const logoutLink = document.querySelector('a[href*="logout"]');
  if (logoutLink) {
    logoutLink.addEventListener('click', function(e) {
      // Close any open dropdowns first
      window.GVD.dropdown.closeAll();
      
      // Allow the link to work normally
      // The browser will handle the navigation
    });
  }

  // Global error handler
  window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    
    // Only show toast for user-facing errors, not for development/debug errors
    if (e.error && e.error.name !== 'ChunkLoadError' && !e.error.message.includes('Network')) {
      window.GVD.toast.show('An unexpected error occurred', 'error');
    }
    
    // Log to service in production
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      // In production, you might want to send errors to a logging service
      // logErrorToService(e.error);
    }
  });

  // Global unhandled promise rejection handler
  window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    
    // Prevent default browser behavior
    e.preventDefault();
    
    // Only show toast for user-facing rejections
    if (e.reason && typeof e.reason === 'object' && e.reason.name !== 'AbortError') {
      window.GVD.toast.show('A request failed', 'error');
    }
    
    // Log to service in production
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      // logErrorToService(e.reason);
    }
  });

  // Console cleanup for production
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    // Override console methods in production to reduce noise
    const originalConsole = {
      log: console.log,
      info: console.info,
      warn: console.warn,
      error: console.error
    };
    
    console.log = function(...args) {
      // Only allow specific log messages in production
      if (args[0] && typeof args[0] === 'string' && 
          (args[0].includes('GVD') || args[0].includes('User') || args[0].includes('Error'))) {
        originalConsole.log.apply(console, args);
      }
    };
    
    console.info = function(...args) {
      if (args[0] && typeof args[0] === 'string' && args[0].includes('GVD')) {
        originalConsole.info.apply(console, args);
      }
    };
    
    console.warn = function(...args) {
      if (args[0] && typeof args[0] === 'string' && args[0].includes('GVD')) {
        originalConsole.warn.apply(console, args);
      }
    };
    
    // Keep error logging for debugging
    console.error = originalConsole.error;
  }
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
  @keyframes toastSlideOut {
    to {
      opacity: 0;
      transform: translateX(100%);
    }
  }
`;
document.head.appendChild(style);
