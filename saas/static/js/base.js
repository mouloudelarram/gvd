/**
 * GVD Professional Design System - Base JavaScript
 * Cleaner + modernized version
 */

window.GVD = {
  state: {
    user: null,
    isLoading: false,
    modals: {},
    toasts: []
  },

  /**
   * Utilities
   */
  utils: {
    escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    },

    debounce(func, wait) {
      let timeout;

      return function (...args) {
        clearTimeout(timeout);

        timeout = setTimeout(() => {
          func.apply(this, args);
        }, wait);
      };
    },

    timeAgo(dateString) {
      const date = new Date(dateString);
      const now = new Date();

      const seconds = Math.floor((now - date) / 1000);

      if (seconds < 60) return "just now";
      if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
      if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
      if (seconds < 2592000) return `${Math.floor(seconds / 86400)} days ago`;
      if (seconds < 31536000) return `${Math.floor(seconds / 2592000)} months ago`;

      return `${Math.floor(seconds / 31536000)} years ago`;
    },

    api: {
      async get(url) {
        try {
          const response = await fetch(url);

          if (!response.ok) {
            throw new Error(
              `HTTP ${response.status}: ${response.statusText}`
            );
          }

          return await response.json();
        } catch (error) {
          console.error("API GET error:", error);
          throw error;
        }
      },

      async post(url, data) {
        try {
          const response = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json"
            },
            body: JSON.stringify(data)
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));

            throw new Error(
              errorData.error ||
              errorData.details ||
              `HTTP ${response.status}: ${response.statusText}`
            );
          }

          return await response.json();
        } catch (error) {
          console.error("API POST error:", error);
          throw error;
        }
      }
    }
  },

  /**
   * Modal system
   */
  modal: {
    open(modalId) {
      const modal = document.getElementById(modalId);

      if (!modal) return;

      modal.hidden = false;
      modal.style.display = "flex";

      document.body.classList.add("modal-open");

      window.GVD.state.modals[modalId] = true;

      // Focus first element
      setTimeout(() => {
        const focusable = modal.querySelector(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );

        if (focusable) {
          focusable.focus();
        }
      }, 50);
    },

    close(modalId) {
      const modal = document.getElementById(modalId);

      if (!modal) return;

      modal.hidden = true;
      modal.style.display = "none";

      document.body.classList.remove("modal-open");

      window.GVD.state.modals[modalId] = false;
    }
  },

  /**
   * Toast system
   */
  toast: {
    show(message, type = "info", duration = 4000) {
      const container = document.getElementById("toast-container");

      if (!container) return;

      const toast = document.createElement("div");

      toast.className = `toast toast-${type}`;

      toast.innerHTML = `
        <div class="toast-content">
          <span>${window.GVD.utils.escapeHtml(message)}</span>
        </div>
      `;

      container.appendChild(toast);

      // Remove automatically
      setTimeout(() => {
        this.remove(toast);
      }, duration);

      // Remove on click
      toast.addEventListener("click", () => {
        this.remove(toast);
      });

      window.GVD.state.toasts.push(toast);
    },

    remove(toast) {
      if (!toast || !toast.parentNode) return;

      toast.classList.add("toast-exit");

      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }

        const index = window.GVD.state.toasts.indexOf(toast);

        if (index > -1) {
          window.GVD.state.toasts.splice(index, 1);
        }
      }, 250);
    }
  },

  /**
   * Dropdown system
   */
  dropdown: {
    toggle(dropdownElement) {
      if (!dropdownElement) return;

      dropdownElement.classList.toggle("open");
    },

    close(dropdownElement) {
      if (!dropdownElement) return;

      dropdownElement.classList.remove("open");
    },

    closeAll() {
      document.querySelectorAll(".dropdown.open").forEach(dropdown => {
        dropdown.classList.remove("open");
      });
    }
  },

  /**
   * Notification system - PRODUCTION GRADE
   */
  notifications: {
    list: [],
    unreadCount: 0,
    pollInterval: null,
    
    async init() {
      // Load initial notifications
      await this.refresh();
      
      // Poll for new notifications every 5 seconds
      this.pollInterval = setInterval(() => this.refresh(), 5000);
    },
    
    async refresh() {
      try {
        const response = await window.GVD.utils.api.get('/api/notifications');
        this.list = response.notifications || [];
        this.unreadCount = response.unread_count || 0;
        this.updateBadge();
      } catch (error) {
        console.warn('Failed to fetch notifications:', error);
      }
    },
    
    updateBadge() {
      const btn = document.getElementById('notifications-btn');
      if (!btn) return;
      
      let badge = document.getElementById('notifications-badge');
      
      if (this.unreadCount > 0) {
        if (!badge) {
          badge = document.createElement('span');
          badge.id = 'notifications-badge';
          badge.className = 'notification-badge';
          btn.appendChild(badge);
        }
        badge.textContent = this.unreadCount;
      } else if (badge) {
        badge.remove();
      }
    },
    
    async markAsRead(notificationId) {
      try {
        await window.GVD.utils.api.post(`/api/notifications/${notificationId}/read`, {});
        await this.refresh();
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    },
    
    async clearAll() {
      try {
        await window.GVD.utils.api.post('/api/notifications/clear', {});
        await this.refresh();
      } catch (error) {
        console.error('Failed to clear notifications:', error);
      }
    },
    
    show() {
      const btn = document.getElementById('notifications-btn');
      if (!btn) return;
      
      // Create notification dropdown if not exists
      let dropdown = document.getElementById('notifications-dropdown');
      if (!dropdown) {
        dropdown = document.createElement('div');
        dropdown.id = 'notifications-dropdown';
        dropdown.className = 'notifications-dropdown';
        btn.parentElement.appendChild(dropdown);
      }
      
      if (this.list.length === 0) {
        dropdown.innerHTML = '<div class="notification-empty">No notifications</div>';
      } else {
        dropdown.innerHTML = this.list.map(n => `
          <div class="notification-item ${n.read ? '' : 'unread'}" data-notification-id="${window.GVD.utils.escapeHtml(n.id)}">
            <div class="notification-content">
              <div class="notification-title">${window.GVD.utils.escapeHtml(n.title)}</div>
              <div class="notification-message">${window.GVD.utils.escapeHtml(n.message)}</div>
              <div class="notification-time">${window.GVD.utils.timeAgo(n.created_at)}</div>
            </div>
          </div>
        `).join('');
        
        // Wire up click handlers
        dropdown.querySelectorAll('.notification-item').forEach(item => {
          item.addEventListener('click', () => {
            const notifId = item.dataset.notificationId;
            window.GVD.notifications.markAsRead(notifId);
          });
        });
      }
      
      dropdown.hidden = false;
    },
    
    hide() {
      const dropdown = document.getElementById('notifications-dropdown');
      if (dropdown) {
        dropdown.hidden = true;
      }
    }
  },

  /**
   * Loading helpers
   */
  loading: {
    show(element) {
      if (typeof element === "string") {
        element = document.getElementById(element);
      }

      if (element) {
        element.classList.add("loading");
      }
    },

    hide(element) {
      if (typeof element === "string") {
        element = document.getElementById(element);
      }

      if (element) {
        element.classList.remove("loading");
      }
    }
  }
};

/**
 * DOM Ready
 */
document.addEventListener("DOMContentLoaded", () => {

  /**
   * DROPDOWNS
   * Click once = open
   * Click again = close
   */
  document.querySelectorAll(".dropdown-toggle").forEach(toggle => {
    toggle.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      const dropdown = this.closest(".dropdown");

      if (dropdown) {
        dropdown.classList.toggle("open");
      }
    });
  });

  /**
   * Notifications
   */
  // Initialize notification system
  window.GVD.notifications.init();

  // Wire up notifications button
  const notificationsBtn = document.getElementById("notifications-btn");
  if (notificationsBtn) {
    notificationsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.GVD.notifications.show();
    });
  }

  // Close notifications when clicking outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#notifications-btn") && !e.target.closest("#notifications-dropdown")) {
      window.GVD.notifications.hide();
    }
  });

  /**
   * Modal close buttons
   */
  document.querySelectorAll("[data-close-modal]").forEach(button => {
    button.addEventListener("click", () => {
      const modal = button.closest(".modal-overlay");

      if (modal) {
        window.GVD.modal.close(modal.id);
      }
    });
  });

  /**
   * Scan modal close buttons
   */
  document.querySelectorAll("[data-close-scan-modal]").forEach(button => {
    button.addEventListener("click", () => {
      const modal = button.closest(".modal-overlay");

      if (modal) {
        window.GVD.modal.close(modal.id);
      }
    });
  });

  /**
   * Logout link
   */
  const logoutLink = document.querySelector('a[href*="logout"]');

  if (logoutLink) {
    logoutLink.addEventListener("click", () => {
      window.GVD.dropdown.closeAll();
    });
  }

  /**
   * Global JS errors
   */
  window.addEventListener("error", e => {
    console.error("Global error:", e.error);

    if (
      e.error &&
      e.error.name !== "ChunkLoadError" &&
      !String(e.error.message).includes("Network")
    ) {
      window.GVD.toast.show(
        "An unexpected error occurred",
        "error"
      );
    }
  });

  /**
   * Promise rejections
   */
  window.addEventListener("unhandledrejection", e => {
    console.error("Unhandled promise rejection:", e.reason);

    e.preventDefault();

    if (
      e.reason &&
      typeof e.reason === "object" &&
      e.reason.name !== "AbortError"
    ) {
      window.GVD.toast.show(
        "A request failed",
        "error"
      );
    }
  });

  /**
   * Production console cleanup
   */
  const isProduction =
    window.location.hostname !== "localhost" &&
    window.location.hostname !== "127.0.0.1";

  if (isProduction) {
    const originalError = console.error;

    console.log = () => {};
    console.info = () => {};
    console.warn = () => {};

    console.error = originalError;
  }
});

/**
 * Inject minimal animations
 */
const style = document.createElement("style");

style.textContent = `
  .toast-exit {
    opacity: 0;
    transform: translateX(16px);
    transition:
      opacity 0.25s ease,
      transform 0.25s ease;
  }
`;

document.head.appendChild(style);