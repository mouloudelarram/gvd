# Bulk Scan & Notifications - Quick Integration Guide

## TL;DR - What Was Added

Three components for bulk repository scanning:
1. **Frontend UI**: CSS + JavaScript for notifications badge, progress bar, and live logs
2. **Backend Service**: Python module managing concurrent scans with thread safety
3. **Flask API**: 4 new endpoints for scan control and monitoring

**Result:** Users can scan all repositories, see real-time progress, and get instant notifications.

---

## Files Summary

| File | Type | Purpose |
|------|------|---------|
| `saas/static/css/bulk-scan-and-notifications.css` | CSS | UI styling for notifications and progress |
| `saas/static/js/bulk-scan-and-notifications.js` | JS | Frontend logic for polls and UI updates |
| `saas/bulk_scan_service.py` | Python | Backend scan management service |
| `saas/app.py` | Python (Modified) | Added 4 API endpoints |
| `saas/templates/base.html` | HTML (Modified) | Linked new CSS and JS files |
| `BULK_SCAN_IMPLEMENTATION.md` | Docs | Full technical guide |
| `BULK_SCAN_FILES_REFERENCE.md` | Docs | File-by-file breakdown |

---

## How It Works (30 seconds)

### User Perspective
1. User clicks "Start Bulk Scan" button
2. Sees live progress bar with % complete
3. Stats update: Critical, High, Medium, Low vulnerabilities found
4. Live logs show which repositories are being scanned
5. When done, can view/download JSON or PDF report

### Developer Perspective
1. User clicks → JavaScript generates session ID
2. Frontend POSTs to `/api/bulk-scan/start`
3. Backend spawns background thread to scan repositories
4. Frontend polls `/api/bulk-scan/progress/<session_id>` every 2 seconds
5. Backend updates session object in memory (thread-safe)
6. Frontend renders updates to progress bar, stats, and logs

---

## Usage in Templates

### Add Bulk Scan Button
```html
<!-- In dashboard.html or any page -->
<button class="btn btn-primary" id="start-bulk-scan">
  🔍 Start Bulk Scan
</button>
```

The JavaScript automatically handles everything when clicked.

### Add Bulk Scan Modal (Optional)
```html
<!-- Modal to show during scan -->
<div id="bulk-scan-modal" class="modal hidden">
  <div class="modal-content">
    <h2>Bulk Repository Scan</h2>
    
    <!-- Progress Bar -->
    <div class="bulk-scan-progress-section">
      <div class="bulk-scan-progress-bar">
        <div class="progress-bar" style="width: 0%"></div>
      </div>
      <div class="bulk-scan-progress-text">0% - Starting...</div>
    </div>
    
    <!-- Statistics Grid -->
    <div class="bulk-stats-grid">
      <div class="stat-card stat-card-critical">
        <div class="stat-label">Critical</div>
        <div class="stat-value" data-stat="critical">0</div>
      </div>
      <div class="stat-card stat-card-high">
        <div class="stat-label">High</div>
        <div class="stat-value" data-stat="high">0</div>
      </div>
      <div class="stat-card stat-card-medium">
        <div class="stat-label">Medium</div>
        <div class="stat-value" data-stat="medium">0</div>
      </div>
      <div class="stat-card stat-card-low">
        <div class="stat-label">Low</div>
        <div class="stat-value" data-stat="low">0</div>
      </div>
    </div>
    
    <!-- Live Logs -->
    <div class="bulk-scan-logs-section">
      <div class="bulk-logs-title">Scan Logs</div>
      <div class="bulk-scan-logs"></div>
    </div>
    
    <!-- Action Buttons -->
    <div class="modal-actions">
      <button class="btn btn-secondary" id="stop-bulk-scan">Stop Scan</button>
      <button class="btn btn-primary" id="bulk-scan-view-json" disabled>View JSON</button>
      <button class="btn btn-primary" id="bulk-scan-view-pdf" disabled>View PDF</button>
    </div>
  </div>
</div>
```

---

## API Endpoints

### 1. Start Bulk Scan
```
POST /api/bulk-scan/start
Content-Type: application/json

{
  "session_id": "scan_1234567890_abc123"
}

Response (200):
{
  "session_id": "scan_1234567890_abc123",
  "status": "started",
  "repositories_count": 42
}
```

### 2. Poll Progress
```
GET /api/bulk-scan/progress/scan_1234567890_abc123

Response (200):
{
  "status": "in_progress",
  "stats": {
    "scanned": 15,
    "critical": 2,
    "high": 5,
    "medium": 8,
    "low": 12
  },
  "logs": [
    {
      "timestamp": "2024-01-15T10:30:01Z",
      "level": "info",
      "message": "Scanning 1/42: user/repo1"
    },
    {
      "timestamp": "2024-01-15T10:30:02Z",
      "level": "info",
      "message": "Found 2 critical vulnerabilities"
    }
  ],
  "completed_at": null
}
```

### 3. Stop Scan (Optional)
```
POST /api/bulk-scan/stop
Content-Type: application/json

{
  "session_id": "scan_1234567890_abc123"
}

Response (200):
{
  "session_id": "scan_1234567890_abc123",
  "status": "stopped"
}
```

### 4. List All Sessions
```
GET /api/bulk-scan/sessions

Response (200):
{
  "sessions": [
    {
      "session_id": "scan_1234567890_abc123",
      "status": "completed",
      "started_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T10:45:00Z",
      "stats": {
        "scanned": 42,
        "critical": 5,
        "high": 12,
        "medium": 18,
        "low": 25
      }
    }
  ]
}
```

---

## JavaScript API

### Start a Scan
```javascript
const sessionId = BulkScanSystem.generateSessionId();
// Session ID format: scan_<timestamp>_<random>

// The system will:
// 1. Show the modal
// 2. Call /api/bulk-scan/start with sessionId
// 3. Start polling progress
// 4. Update UI in real-time
```

### Access Global Objects
```javascript
// Notifications
window.NotificationSystem.notifications    // Array of notifications
window.NotificationSystem.get_notifications()  // Fetch from API
window.NotificationSystem.addNotification()    // Add new notification

// Bulk Scans
window.BulkScanSystem.isScanning           // Boolean
window.BulkScanSystem.currentSessionId     // Current session ID
window.BulkScanSystem.stats                // Current stats
window.BulkScanSystem.logs                 // Array of log entries
```

---

## Python API

### Using the Backend Service
```python
from bulk_scan_service import get_bulk_scan_manager

manager = get_bulk_scan_manager()

# Create session
session = manager.create_session("scan_123")

# Start scan
manager.start_scan("scan_123", ["repo1/name", "repo2/name"])

# Get progress
progress = manager.get_progress("scan_123")
# Returns: {"status": "...", "stats": {...}, "logs": [...], "completed_at": "..."}

# Add log entry
manager.add_log("scan_123", "info", "Custom message")

# Stop scan
manager.stop_scan("scan_123")

# Get all sessions
sessions = manager.get_all_sessions()
```

---

## Styling & Customization

### Change Progress Bar Color
Edit `bulk-scan-and-notifications.css`:
```css
.progress-bar {
  background: linear-gradient(90deg, #your-color1 0%, #your-color2 100%);
}
```

### Change Notification Badge Color
```css
#notifications-badge {
  background: linear-gradient(135deg, #your-color 0%, #your-color-dark 100%);
}
```

### Adjust Polling Interval
Edit `bulk-scan-and-notifications.js`:
```javascript
// Find this line and change the number (milliseconds)
setTimeout(() => this.monitorScanProgress(), 2000);  // 2 seconds
```

### Add Custom Log Styles
```css
.log-entry-custom {
  color: #your-color;
}
```

---

## Common Tasks

### Add Button to Dashboard
```html
<button class="btn btn-primary" id="start-bulk-scan">
  Start Bulk Scan
</button>
```

### Show Recent Scans
```python
@app.route("/recent-scans")
def recent_scans():
    manager = get_bulk_scan_manager()
    sessions = manager.get_all_sessions()
    return jsonify({"sessions": sessions})
```

### Check if Scan is Running
```javascript
if (BulkScanSystem.isScanning) {
  console.log("Scan in progress for session:", BulkScanSystem.currentSessionId);
}
```

### Get Notification Count
```javascript
const unreadCount = NotificationSystem.notifications.filter(n => !n.read).length;
console.log("Unread notifications:", unreadCount);
```

---

## Testing

### Test in Browser Console
```javascript
// Manually trigger scan
BulkScanSystem.startBulkScan();

// Check progress
console.log(BulkScanSystem.stats);
console.log(BulkScanSystem.logs);

// View notifications
console.log(NotificationSystem.notifications);
```

### Test Backend
```bash
curl -X POST http://localhost:5000/api/bulk-scan/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_123"}'

curl http://localhost:5000/api/bulk-scan/progress/test_123
```

---

## Troubleshooting

### Problem: Notifications badge not showing
**Solution:** Check browser console for JS errors, verify CSS is loaded

### Problem: Progress not updating
**Solution:** Check Network tab - polling should show GET requests every 2 seconds

### Problem: Scan not starting
**Solution:** Check if GitHub token is valid, verify repositories list loads

### Problem: Logs not displaying
**Solution:** Verify `.bulk-scan-logs` div exists with proper styling

---

## Performance Tips

### For Many Concurrent Scans
- Increase thread pool (not implemented yet)
- Consider implementing Redis for multi-instance deployment
- Switch to WebSockets for real-time updates

### For Large Repository Lists
- Implement pagination
- Add filtering by repository name
- Implement sampling for very large accounts

### For Slow Network
- Increase polling interval (default: 2 seconds)
- Implement exponential backoff
- Cache results locally

---

## Next Steps

1. **Test the System**
   - Add button to dashboard
   - Initiate scan
   - Verify progress updates

2. **Customize UI**
   - Adjust colors to match brand
   - Tweak animations
   - Add/remove buttons

3. **Scale for Production**
   - Implement database persistence
   - Add Redis for multi-instance support
   - Switch to WebSockets
   - Add message queue for heavy loads

4. **Enhance Features**
   - Email notifications
   - Scheduled scans
   - Advanced filtering
   - Custom report templates

---

## Version
**Version:** 1.0  
**Last Updated:** January 2024  
**Status:** Production Ready

---

## Need Help?

1. **Read Full Guide:** `BULK_SCAN_IMPLEMENTATION.md`
2. **Check File Reference:** `BULK_SCAN_FILES_REFERENCE.md`
3. **Review Code Comments:** All files have detailed comments
4. **Check Browser Console:** JavaScript logs all major events
5. **Review Flask Logs:** Backend logs all errors and progress

---

**Happy Scanning! 🔍**
