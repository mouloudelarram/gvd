# Bulk Scan & Notifications - Testing & Verification Guide

## Integration Status

✅ **Backend Service:** `bulk_scan_service.py` - Ready
✅ **Frontend CSS:** `bulk-scan-and-notifications.css` - Ready  
✅ **Frontend JS:** `bulk-scan-and-notifications.js` - Ready
✅ **Flask Routes:** 4 new API endpoints in `app.py` - Ready
✅ **Dashboard:** Bulk scan modal and JavaScript - Ready
✅ **Base Template:** CSS/JS links added - Ready

---

## Pre-Flight Checklist

### Backend Verification
- [ ] `bulk_scan_service.py` exists in `saas/` directory
- [ ] No syntax errors in `bulk_scan_service.py` (test import)
- [ ] API routes added to `app.py` (search for "bulk-scan")
- [ ] `get_repos()` function works in `github.py`
- [ ] Flask app imports complete without errors

### Frontend Verification
- [ ] `bulk-scan-and-notifications.css` exists in `saas/static/css/`
- [ ] `bulk-scan-and-notifications.js` exists in `saas/static/js/`
- [ ] Both files linked in `base.html`
- [ ] Dashboard includes bulk-scan modal HTML
- [ ] Dashboard JavaScript initialized on page load

### File Existence Check
Run in PowerShell from workspace root:
```powershell
# Check backend service
Test-Path "saas/bulk_scan_service.py"

# Check CSS file
Test-Path "saas/static/css/bulk-scan-and-notifications.css"

# Check JS file
Test-Path "saas/static/js/bulk-scan-and-notifications.js"

# Check base.html has links
Select-String -Path "saas/templates/base.html" -Pattern "bulk-scan"
```

---

## Step 1: Verify Backend Service

### 1.1 Test Service Import
```python
# In Python terminal
from saas.bulk_scan_service import get_bulk_scan_manager

manager = get_bulk_scan_manager()
print("✓ Manager initialized:", type(manager))
```

**Expected Output:**
```
✓ Manager initialized: <class 'bulk_scan_service.BulkScanManager'>
```

### 1.2 Test Session Creation
```python
session = manager.create_session("test_123")
print("✓ Session created:", session.session_id)
print("✓ Status:", session.status)
print("✓ Stats:", session.stats)
```

**Expected Output:**
```
✓ Session created: test_123
✓ Status: pending
✓ Stats: ScanStats(scanned=0, critical=0, high=0, medium=0, low=0)
```

### 1.3 Test Notifications
```python
manager._add_notification("Test Title", "Test Message")
notifs = manager.get_notifications()
print("✓ Notifications:", len(notifs))
print("✓ First notification:", notifs[0]["title"])
```

**Expected Output:**
```
✓ Notifications: 1
✓ First notification: Test Title
```

---

## Step 2: Verify Flask API Routes

### 2.1 Start Flask App
```bash
cd saas
flask run --port=5000
```

**Expected Output:**
```
 * Running on http://127.0.0.1:5000
```

### 2.2 Test POST /api/bulk-scan/start

**Request:**
```bash
curl -X POST http://localhost:5000/api/bulk-scan/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_scan_001"}'
```

**Expected Response (200):**
```json
{
  "session_id": "test_scan_001",
  "status": "started",
  "repositories_count": 42
}
```

**Failure Check:**
- If you get 401: User not authenticated (login first)
- If you get 400: session_id is missing
- If you get 500: Check Flask logs for errors

### 2.3 Test GET /api/bulk-scan/progress/{session_id}

**Request:**
```bash
curl http://localhost:5000/api/bulk-scan/progress/test_scan_001
```

**Expected Response (200):**
```json
{
  "status": "in_progress",
  "stats": {
    "scanned": 5,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4
  },
  "logs": [...],
  "completed_at": null
}
```

### 2.4 Test POST /api/bulk-scan/stop

**Request:**
```bash
curl -X POST http://localhost:5000/api/bulk-scan/stop \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_scan_001"}'
```

**Expected Response (200):**
```json
{
  "session_id": "test_scan_001",
  "status": "stopped"
}
```

---

## Step 3: Verify Frontend Components

### 3.1 Check CSS Loading
Open browser DevTools (F12) → Network tab

**Expected:**
- `bulk-scan-and-notifications.css` loads with status 200
- No CSS syntax errors in Console

### 3.2 Check JavaScript Loading
In browser console:

```javascript
// Check if global objects exist
console.log("NotificationSystem:", window.NotificationSystem);
console.log("BulkScanSystem:", window.BulkScanSystem);

// Should show: Object { ... }
```

**Expected Output:**
```
NotificationSystem: Object { notifications: Array, ... }
BulkScanSystem: Object { isScanning: false, ... }
```

### 3.3 Test Notification Badge
In browser console:

```javascript
// Manually add a notification
NotificationSystem.addNotification({
  title: "Test Notification",
  message: "This is a test"
});

// Should see badge appear in navbar with count
console.log("Notifications:", NotificationSystem.notifications);
```

---

## Step 4: End-to-End Testing

### 4.1 Full Bulk Scan Flow

**Prerequisites:**
- User is logged in
- User has repositories on GitHub
- Flask app is running
- Network requests are working

**Steps:**

1. **Open Dashboard**
   - Navigate to `http://localhost:5000/dashboard`
   - Verify notification badge appears in navbar
   - Verify "Scan All" button is visible

2. **Click Scan All Button**
   - Look for bulk-scan-modal to appear
   - Verify progress bar shows 0%
   - Verify stats show 0 for all counts

3. **Monitor Progress**
   - Watch progress bar update
   - Verify statistics grid updates
   - Check live logs for new entries
   - Progress should update every 2 seconds

4. **Verify Completion**
   - Progress bar reaches 100%
   - Status message shows completed
   - Report buttons become enabled
   - Success toast appears

5. **Test Report Buttons**
   - Click "View JSON Report" - should show formatted JSON
   - Click "View PDF Report" - should display PDF
   - Click "Download JSON" - file downloads
   - Click "Download PDF" - file downloads

### 4.2 Monitor Browser Console
- [ ] No JavaScript errors during scan
- [ ] Network tab shows polling requests every 2 seconds
- [ ] Each request returns updated stats
- [ ] No CORS errors

### 4.3 Monitor Server Logs
```
Flask console should show:
- POST /api/bulk-scan/start
- GET /api/bulk-scan/progress/... (repeated)
- No 500 errors
```

---

## Common Issues & Solutions

### Issue: "Notifications badge not appearing"
**Solutions:**
1. Check browser console for JavaScript errors
2. Verify CSS file loads (Network tab)
3. Check if JavaScript initialized: `console.log(window.NotificationSystem)`
4. Refresh page with Ctrl+Shift+R (hard refresh)

### Issue: "Scan button doesn't respond"
**Solutions:**
1. Verify user is logged in (check session)
2. Check browser console for JavaScript errors
3. Check network tab for failed requests
4. Verify `/api/all-user-repos` returns data

### Issue: "Progress not updating"
**Solutions:**
1. Check Network tab - should show requests every 2 seconds
2. Verify Flask app is running on port 5000
3. Check server logs for exceptions
4. Verify `bulk_scan_service.py` is imported correctly
5. Try refreshing the page

### Issue: "Statistics don't match final report"
**Solutions:**
1. This is normal if scan is still in progress
2. Wait for completion status
3. Check if all repositories finished scanning
4. Verify no repositories had errors

### Issue: "Modal doesn't close properly"
**Solutions:**
1. Check if close button has proper event handler
2. Verify modal CSS classes exist
3. Refresh page
4. Check for JavaScript errors in console

---

## Step 5: Performance Testing

### 5.1 Load Testing (Single User)
**Test:** Start bulk scan with 10+ repositories

**Metrics to Monitor:**
- Initial load time: < 500ms
- Progress update frequency: ≤ 2 seconds
- Memory usage: < 100MB
- CPU usage: < 20%

### 5.2 UI Responsiveness
**Test:** During active scan, perform other actions

- [ ] Can still search repositories
- [ ] Can still filter repositories
- [ ] Modal doesn't freeze
- [ ] Can click other buttons
- [ ] Toast notifications still appear

### 5.3 Network Efficiency
**Test:** Monitor Network tab during scan

- [ ] Progress requests are ~1-2 KB each
- [ ] No repeated requests for same data
- [ ] No memory leaks (memory stabilizes)

---

## Step 6: Cross-Browser Testing

Test on these browsers:

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | Test | Primary target |
| Firefox | Test | CSS Grid support |
| Safari | Test | Apple devices |
| Edge | Test | Windows 10+ |

**Test Points:**
- [ ] CSS renders correctly
- [ ] Animations smooth
- [ ] Progress bar displays
- [ ] All buttons clickable
- [ ] Logs scroll properly

---

## Step 7: Mobile Testing

### Viewport Sizes to Test
- [ ] Mobile: 375px (iPhone SE)
- [ ] Mobile: 414px (iPhone 12)
- [ ] Tablet: 768px (iPad)
- [ ] Tablet: 1024px (iPad Pro)

**Mobile Test Checklist:**
- [ ] Modal fits on screen
- [ ] Progress bar visible
- [ ] Statistics grid responsive
- [ ] Logs scrollable
- [ ] Buttons clickable
- [ ] No horizontal scroll needed

---

## Debugging Tips

### Enable Verbose Logging
**Frontend JavaScript:**
```javascript
// Add this to browser console
window.DEBUG = true;
// Then restart the scan
```

**Backend Python:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Monitor Network Activity
In browser DevTools:
1. Open Network tab
2. Start scan
3. Watch for polling requests
4. Check response payloads
5. Look for errors (red entries)

### Test Without UI
**Direct API calls:**
```bash
# Terminal - test backend directly
curl -X POST http://localhost:5000/api/bulk-scan/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "direct_test"}'
```

### Check Session State
**In browser console:**
```javascript
console.log(BulkScanSystem.stats);
console.log(BulkScanSystem.currentSessionId);
console.log(BulkScanSystem.logs);
```

---

## Verification Checklist (Final)

### Backend
- [ ] `bulk_scan_service.py` imports without errors
- [ ] BulkScanManager singleton works
- [ ] Sessions created and managed correctly
- [ ] Threading works without deadlocks
- [ ] Notifications added to queue
- [ ] Progress polling returns valid data
- [ ] Scan completion handled correctly

### Frontend - CSS
- [ ] Notification badge displays
- [ ] Progress bar animates
- [ ] Statistics cards styled correctly
- [ ] Live logs console styled
- [ ] Mobile responsive
- [ ] All animations smooth

### Frontend - JavaScript
- [ ] NotificationSystem initialized
- [ ] BulkScanSystem initialized
- [ ] Scan button triggers correctly
- [ ] Modal opens/closes
- [ ] Polling works every 2 seconds
- [ ] Progress bar updates
- [ ] Statistics update
- [ ] Logs append correctly
- [ ] Completion handling works

### Flask Routes
- [ ] POST /api/bulk-scan/start works
- [ ] POST /api/bulk-scan/stop works
- [ ] GET /api/bulk-scan/progress works
- [ ] GET /api/bulk-scan/sessions works
- [ ] Authentication required
- [ ] Error handling works
- [ ] Response format correct

### Integration
- [ ] Dashboard button triggers scan
- [ ] Modal appears immediately
- [ ] Progress updates in real-time
- [ ] Completion notifications work
- [ ] Report buttons work
- [ ] Toast notifications appear
- [ ] All errors handled gracefully

---

## Deployment Readiness

Before deploying to production:

- [ ] All tests pass
- [ ] No console errors
- [ ] No network errors
- [ ] Performance acceptable
- [ ] Mobile responsive
- [ ] Error handling robust
- [ ] Logging comprehensive
- [ ] Security reviewed
- [ ] Rate limiting considered
- [ ] Database connections tested (if added)

---

## Test Reports

### Test Execution Log
```
Date: ___________
Tester: _________
Environment: ____

Test Results:
- Backend Service: [ ] PASS [ ] FAIL
- Flask Routes: [ ] PASS [ ] FAIL
- Frontend CSS: [ ] PASS [ ] FAIL
- Frontend JS: [ ] PASS [ ] FAIL
- E2E Flow: [ ] PASS [ ] FAIL
- Performance: [ ] PASS [ ] FAIL
- Mobile: [ ] PASS [ ] FAIL

Issues Found:
1. _______________
2. _______________

Sign-off: ________
```

---

**Document Version:** 1.0
**Last Updated:** January 2024
**Status:** Ready for Testing

---

## Next Steps

1. **Run Backend Verification** (Step 1-2)
2. **Verify Flask Routes** (Step 2)
3. **Check Frontend** (Step 3)
4. **Run Full E2E Test** (Step 4)
5. **Document any issues**
6. **Fix issues and re-test**
7. **Performance test** (Step 5)
8. **Cross-browser test** (Step 6)
9. **Mobile test** (Step 7)
10. **Sign-off and deploy**

---

**Questions?** Refer to `BULK_SCAN_IMPLEMENTATION.md` for detailed documentation.
