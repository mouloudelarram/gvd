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
      if (!modal) return;
      
      modal.hidden = false;
      document.body.classList.add('modal-open');
      window.GVD.state.modals[modalId] = true;
      
      // Focus management
      const focusableElements = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
      }
      
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
      const dropdown = document.getElementById(dropdownId);
      if (!dropdown) return;

      const isOpen = dropdown.classList.contains('open');
      
      // Close all other dropdowns
      this.closeAll();
      
      if (!isOpen) {
        dropdown.classList.add('open');
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
  // Initialize dropdowns
  document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
    toggle.addEventListener('click', function(e) {
      e.preventDefault();
      const dropdown = this.closest('.dropdown');
      if (dropdown) {
        window.GVD.dropdown.toggle(dropdown.id);
      }
    });
  });

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

  // Initialize user dropdown
  const userDropdownToggle = document.getElementById('user-dropdown-toggle');
  if (userDropdownToggle) {
    userDropdownToggle.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      window.GVD.dropdown.toggle('user-dropdown');
    });
  }

  // Initialize logout link
  const logoutLink = document.querySelector('a[href*="logout"]');
  if (logoutLink) {
    logoutLink.addEventListener('click', function(e) {
      // Allow the link to work normally, just close any open dropdowns
      window.GVD.dropdown.closeAll();
    });
  }

  // Global error handler
  window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    window.GVD.toast.show('An unexpected error occurred', 'error');
  });

  // Global unhandled promise rejection handler
  window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    window.GVD.toast.show('An unexpected error occurred', 'error');
  });
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
