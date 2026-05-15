"""
GVD Bulk Scan & Notifications Module
Handles bulk repository scanning and real-time notifications
"""

import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ScanStatus(Enum):
    """Scan session status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class LogLevel(Enum):
    """Log level enumeration"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ScanLog:
    """Individual log entry"""
    timestamp: str
    level: str
    message: str


@dataclass
class ScanStats:
    """Scan statistics"""
    scanned: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


@dataclass
class ScanSession:
    """Bulk scan session"""
    session_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    stats: Optional[ScanStats] = None
    logs: Optional[List[ScanLog]] = None
    report_data: Optional[Dict[str, Any]] = None


class BulkScanManager:
    """Manages bulk scan sessions and operations"""
    
    def __init__(self):
        self.sessions: Dict[str, ScanSession] = {}
        self.notifications: List[Dict[str, Any]] = []
        self.max_notifications = 50
        self.lock = threading.Lock()
    
    def create_session(self, session_id: str) -> ScanSession:
        """Create a new scan session"""
        session = ScanSession(
            session_id=session_id,
            status=ScanStatus.PENDING.value,
            started_at=self._get_timestamp(),
            stats=ScanStats(),
            logs=[]
        )
        
        with self.lock:
            self.sessions[session_id] = session
        
        self._add_notification(
            title="Bulk Scan Started",
            message=f"Scan session {session_id} has been initiated"
        )
        
        return session
    
    def start_scan(self, session_id: str, repositories: List[str]) -> bool:
        """Start a bulk scan for the given repositories"""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False
            
            session.status = ScanStatus.IN_PROGRESS.value
        
        # Start scan in background thread
        thread = threading.Thread(
            target=self._run_scan,
            args=(session_id, repositories),
            daemon=True
        )
        thread.start()
        
        return True
    
    def _run_scan(self, session_id: str, repositories: List[str]):
        """Execute the bulk scan (runs in background thread)"""
        try:
            session = self.sessions[session_id]
            total_repos = len(repositories)
            
            for idx, repo in enumerate(repositories):
                with self.lock:
                    # Check if scan was stopped
                    if session.status == ScanStatus.STOPPED.value:
                        break
                    
                    # Simulate scan progress
                    session.stats.scanned += 1
                    
                    # Simulate vulnerability findings
                    if idx % 5 == 0:
                        session.stats.critical += 1
                    if idx % 3 == 0:
                        session.stats.high += 1
                    if idx % 2 == 0:
                        session.stats.medium += 1
                    session.stats.low += 1
                    
                    # Add log entry
                    self.add_log(
                        session_id,
                        LogLevel.INFO.value,
                        f"Scanning {idx + 1}/{total_repos}: {repo}"
                    )
                
                # Simulate scan delay
                time.sleep(0.5)
            
            # Mark as completed
            with self.lock:
                if session.status != ScanStatus.STOPPED.value:
                    session.status = ScanStatus.COMPLETED.value
                    session.completed_at = self._get_timestamp()
                    self.add_log(
                        session_id,
                        LogLevel.SUCCESS.value,
                        f"Bulk scan completed! Scanned {session.stats.scanned} repositories"
                    )
            
            self._add_notification(
                title="Bulk Scan Completed",
                message=f"Scan session {session_id} has completed successfully"
            )
        
        except Exception as e:
            with self.lock:
                session = self.sessions[session_id]
                session.status = ScanStatus.FAILED.value
                session.completed_at = self._get_timestamp()
                self.add_log(
                    session_id,
                    LogLevel.ERROR.value,
                    f"Scan failed: {str(e)}"
                )
            
            self._add_notification(
                title="Bulk Scan Failed",
                message=f"Scan session {session_id} encountered an error",
                level="error"
            )
            
            logger.error(f"Bulk scan error: {e}")
    
    def stop_scan(self, session_id: str) -> bool:
        """Stop an ongoing scan"""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session or session.status != ScanStatus.IN_PROGRESS.value:
                return False
            
            session.status = ScanStatus.STOPPED.value
            session.completed_at = self._get_timestamp()
            self.add_log(
                session_id,
                LogLevel.WARNING.value,
                "Scan stopped by user"
            )
        
        self._add_notification(
            title="Bulk Scan Stopped",
            message=f"Scan session {session_id} has been stopped"
        )
        
        return True
    
    def add_log(self, session_id: str, level: str, message: str):
        """Add a log entry to a scan session"""
        with self.lock:
            session = self.sessions.get(session_id)
            if session and session.logs is not None:
                log_entry = ScanLog(
                    timestamp=self._get_timestamp(),
                    level=level,
                    message=message
                )
                session.logs.append(log_entry)
    
    def get_session(self, session_id: str) -> Optional[ScanSession]:
        """Get a scan session by ID"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def get_progress(self, session_id: str) -> Dict[str, Any]:
        """Get the progress of a scan session"""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return {"error": "Session not found"}
            
            return {
                "status": session.status,
                "stats": asdict(session.stats) if session.stats else {},
                "logs": [asdict(log) for log in session.logs[-20:]] if session.logs else [],
                "completed_at": session.completed_at
            }
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all scan sessions"""
        with self.lock:
            return [
                {
                    "session_id": s.session_id,
                    "status": s.status,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                    "stats": asdict(s.stats) if s.stats else {}
                }
                for s in self.sessions.values()
            ]
    
    def _add_notification(
        self,
        title: str,
        message: str = "",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None
    ):
        """Add a notification"""
        notification = {
            "id": len(self.notifications) + 1,
            "title": title,
            "message": message,
            "level": level,
            "timestamp": self._get_timestamp(),
            "read": False,
            "data": data or {}
        }
        
        with self.lock:
            self.notifications.insert(0, notification)
            
            # Keep only recent notifications
            if len(self.notifications) > self.max_notifications:
                self.notifications = self.notifications[:self.max_notifications]
    
    def get_notifications(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Get notifications"""
        with self.lock:
            if unread_only:
                return [n for n in self.notifications if not n["read"]]
            return self.notifications.copy()
    
    def mark_notification_as_read(self, notification_id: int) -> bool:
        """Mark a notification as read"""
        with self.lock:
            for notification in self.notifications:
                if notification["id"] == notification_id:
                    notification["read"] = True
                    return True
        return False
    
    def clear_notifications(self) -> bool:
        """Clear all notifications"""
        with self.lock:
            self.notifications.clear()
        return True
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format"""
        return datetime.utcnow().isoformat() + "Z"


# Global singleton instance
_bulk_scan_manager: Optional[BulkScanManager] = None


def get_bulk_scan_manager() -> BulkScanManager:
    """Get the global BulkScanManager instance"""
    global _bulk_scan_manager
    if _bulk_scan_manager is None:
        _bulk_scan_manager = BulkScanManager()
    return _bulk_scan_manager
