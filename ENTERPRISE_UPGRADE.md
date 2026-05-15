# GVD Enterprise Bulk Scanning Upgrade - Complete Implementation Guide

## SCOPE
Fix and upgrade "Scan All" to become enterprise-grade bulk repository scanning system.

## KEY CHANGES

### Backend (app.py)
1. Add job expiration cleanup
2. Add rate limiting on /scan-all
3. Track bulk scan reports in Flask session
4. Cleanup BULK_SCAN_JOBS on logout
5. Add notification endpoints

### Frontend (dashboard.js)  
1. Replace `handleScanAll()` - call `/scan-all` endpoint instead of local scanning
2. Add polling mechanism - poll `/scan-all/<job_id>` for real-time updates
3. Add notification system - toast notifications for scan events
4. Add report preview/download - integrate with report endpoints
5. Add dashboard stats update - refresh metrics after scan completes

### Session Management
1. Track active bulk scan jobs in session
2. Track available reports in session
3. Cleanup on logout
4. Support multiple scans per session

## FILES TO MODIFY
- saas/app.py (Backend)
- saas/static/js/dashboard.js (Frontend)
- saas/static/js/base.js (Notification system)
- saas/templates/dashboard.html (Markup for notifications)

## IMPLEMENTATION ORDER
1. Backend changes first (add endpoints, session tracking)
2. Frontend notification system (base.js)
3. Frontend bulk scan integration (dashboard.js)
4. Test end-to-end workflow
