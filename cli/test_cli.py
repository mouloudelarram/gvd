"""Comprehensive test suite for GVD CLI scanner."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from core.models import Finding, Severity
from scanner.pattern_engine import PatternEngine
from scanner.git_history import GitHistoryScanner
from scanner.file_scanner import FileScanner
from scanner.risk_engine import RiskEngine
from report.builder import ReportBuilder
from report.exporter import ReportExporter


class TestPatternEngine:
    """Test pattern matching engine."""
    
    def test_aws_key_pattern(self):
        """Test AWS key pattern detection."""
        engine = PatternEngine()
        
        # Valid AWS key
        matches = engine.match_pattern("AKIA1234567890123456")
        assert len(matches) == 1
        assert matches[0]['type'] == 'aws_key'
        assert matches[0]['severity'] == Severity.CRITICAL
        
        # Invalid AWS key (wrong length)
        matches = engine.match_pattern("AKIA123")
        assert len(matches) == 0
    
    def test_generic_api_key_pattern(self):
        """Test generic API key pattern detection."""
        engine = PatternEngine()
        
        # Valid API key
        matches = engine.match_pattern("api_key=sk-1234567890abcdef1234567890abcdef")
        assert len(matches) == 1
        assert matches[0]['type'] == 'generic_api_key'
        assert matches[0]['severity'] == Severity.HIGH
        
        # Too short
        matches = engine.match_pattern("api_key=short")
        assert len(matches) == 0
    
    def test_private_key_pattern(self):
        """Test private key pattern detection."""
        engine = PatternEngine()
        
        # Private key header
        matches = engine.match_pattern("-----BEGIN PRIVATE KEY-----")
        assert len(matches) == 1
        assert matches[0]['type'] == 'private_key'
        assert matches[0]['severity'] == Severity.CRITICAL
    
    def test_database_url_pattern(self):
        """Test database URL pattern detection."""
        engine = PatternEngine()
        
        # Database URL
        matches = engine.match_pattern("DATABASE_URL=postgresql://user:pass@host:5432/db")
        assert len(matches) == 1
        assert matches[0]['type'] == 'database_url'
        assert matches[0]['severity'] == Severity.CRITICAL
    
    def test_multiple_patterns(self):
        """Test detection of multiple patterns in one string."""
        engine = PatternEngine()
        
        content = """
        AWS_ACCESS_KEY_ID=AKIA1234567890123456
        api_key=sk-1234567890abcdef1234567890abcdef
        DATABASE_URL=postgresql://user:pass@host:5432/db
        """
        
        matches = engine.match_pattern(content)
        assert len(matches) == 3
        
        types = [m['type'] for m in matches]
        assert 'aws_key' in types
        assert 'generic_api_key' in types
        assert 'database_url' in types


class TestGitHistoryScanner:
    """Test git history scanning functionality."""
    
    @patch('scanner.git_history.run_git_command')
    def test_scan_history_success(self, mock_run_git):
        """Test successful git history scanning."""
        mock_run_git.return_value = """
commit abc123
diff --git a/secrets.txt b/secrets.txt
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/secrets.txt
@@ -0,0 +1 @@
+AKIA1234567890123456
        """
        
        pattern_engine = PatternEngine()
        scanner = GitHistoryScanner(pattern_engine)
        
        findings = list(scanner.scan_history(Path("/tmp/repo"), "test-repo"))
        
        assert len(findings) == 1
        assert findings[0].secret_type == 'aws_key'
        assert findings[0].severity == Severity.CRITICAL
        assert findings[0].commit_hash == 'abc123'
        assert findings[0].file_path == 'secrets.txt'
    
    @patch('scanner.git_history.run_git_command')
    def test_scan_history_empty(self, mock_run_git):
        """Test scanning empty repository."""
        mock_run_git.return_value = ""
        
        pattern_engine = PatternEngine()
        scanner = GitHistoryScanner(pattern_engine)
        
        findings = list(scanner.scan_history(Path("/tmp/repo"), "test-repo"))
        assert len(findings) == 0


class TestFileScanner:
    """Test file scanning functionality."""
    
    @patch('scanner.file_scanner.run_git_command')
    def test_scan_sensitive_files(self, mock_run_git):
        """Test sensitive file detection."""
        mock_run_git.return_value = """
.env
config.json
secrets.txt
id_rsa
        """
        
        scanner = FileScanner()
        findings = scanner.scan_sensitive_files(Path("/tmp/repo"), "test-repo")
        
        # Should find .env and id_rsa as sensitive files
        assert len(findings) >= 2
        
        sensitive_files = [f.file_path for f in findings]
        assert '.env' in sensitive_files
        assert 'id_rsa' in sensitive_files
    
    def test_is_sensitive_file(self):
        """Test sensitive file pattern matching."""
        scanner = FileScanner()
        
        assert scanner._is_sensitive_file('.env') == True
        assert scanner._is_sensitive_file('.env.production') == True
        assert scanner._is_sensitive_file('id_rsa') == True
        assert scanner._is_sensitive_file('config.pem') == True
        assert scanner._is_sensitive_file('secrets.json') == True
        
        assert scanner._is_sensitive_file('README.md') == False
        assert scanner._is_sensitive_file('index.js') == False


class TestRiskEngine:
    """Test risk assessment engine."""
    
    def test_assess_risk_no_change(self):
        """Test risk assessment without modification."""
        engine = RiskEngine()
        
        finding = Finding(
            repo_name="test-repo",
            commit_hash="abc123",
            file_path="test.txt",
            line_number=1,
            secret_type="aws_key",
            severity=Severity.CRITICAL,
            content="AKIA1234567890123456",
            fix_recommendation="Rotate AWS credentials"
        )
        
        result = engine.assess_risk(finding)
        assert result == finding


class TestReportBuilder:
    """Test report building functionality."""
    
    def test_build_json_report_empty(self):
        """Test building JSON report with no findings."""
        builder = ReportBuilder([])
        
        report = builder.build_json_report()
        
        assert report['repo_name'] == ""
        assert report['total_findings'] == 0
        assert report['severity_counts'] == {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        assert report['findings'] == []
        assert 'scan_date' in report
    
    def test_build_json_report_with_findings(self):
        """Test building JSON report with findings."""
        findings = [
            Finding(
                repo_name="test-repo",
                commit_hash="abc123",
                file_path="secrets.txt",
                line_number=1,
                secret_type="aws_key",
                severity=Severity.CRITICAL,
                content="AKIA1234567890123456",
                fix_recommendation="Rotate AWS credentials"
            ),
            Finding(
                repo_name="test-repo",
                commit_hash="def456",
                file_path="config.py",
                line_number=10,
                secret_type="generic_api_key",
                severity=Severity.HIGH,
                content="api_key=sk-1234567890abcdef",
                fix_recommendation="Rotate API key"
            )
        ]
        
        builder = ReportBuilder(findings)
        report = builder.build_json_report()
        
        assert report['repo_name'] == "test-repo"
        assert report['total_findings'] == 2
        assert report['severity_counts']['CRITICAL'] == 1
        assert report['severity_counts']['HIGH'] == 1
        assert len(report['findings']) == 2
    
    def test_build_markdown_report(self):
        """Test building Markdown report."""
        findings = [
            Finding(
                repo_name="test-repo",
                commit_hash="abc123",
                file_path="secrets.txt",
                line_number=1,
                secret_type="aws_key",
                severity=Severity.CRITICAL,
                content="AKIA1234567890123456",
                fix_recommendation="Rotate AWS credentials"
            )
        ]
        
        builder = ReportBuilder(findings)
        report = builder.build_markdown_report()
        
        assert "# GVD Security Report" in report
        assert "test-repo" in report
        assert "Total findings: 1" in report
        assert "## CRITICAL (1)" in report
        assert "**File:** secrets.txt" in report
    
    def test_build_summary_text(self):
        """Test building summary text."""
        findings = [
            Finding(
                repo_name="test-repo",
                commit_hash="abc123",
                file_path="secrets.txt",
                line_number=1,
                secret_type="aws_key",
                severity=Severity.CRITICAL,
                content="AKIA1234567890123456",
                fix_recommendation="Rotate AWS credentials"
            )
        ]
        
        builder = ReportBuilder(findings)
        summary = builder.build_summary_text()
        
        assert "GVD Scan Summary" in summary
        assert "Total findings: 1" in summary
        assert "Critical: 1" in summary


class TestReportExporter:
    """Test report export functionality."""
    
    def test_export_all(self):
        """Test exporting all report formats."""
        findings = [
            Finding(
                repo_name="test-repo",
                commit_hash="abc123",
                file_path="secrets.txt",
                line_number=1,
                secret_type="aws_key",
                severity=Severity.CRITICAL,
                content="AKIA1234567890123456",
                fix_recommendation="Rotate AWS credentials"
            )
        ]
        
        builder = ReportBuilder(findings)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = ReportExporter(builder, Path(temp_dir))
            
            # Mock PDF generation to avoid reportlab dependency issues in tests
            with patch('report.exporter.build_pdf_report'):
                exporter.export_all()
            
            # Check that files were created
            assert (Path(temp_dir) / "report.json").exists()
            assert (Path(temp_dir) / "report.md").exists()
            assert (Path(temp_dir) / "summary.txt").exists()
            
            # Check JSON content
            with open(Path(temp_dir) / "report.json") as f:
                data = json.load(f)
                assert data['total_findings'] == 1
                assert data['severity_counts']['CRITICAL'] == 1


class TestCLIIntegration:
    """Test CLI integration."""
    
    @patch('cli.cli.is_git_repo')
    @patch('cli.cli.get_repo_root')
    @patch('cli.cli.get_repo_name')
    @patch('cli.cli.GitHistoryScanner')
    @patch('cli.cli.FileScanner')
    @patch('cli.cli.ReportExporter')
    def test_scan_repo_integration(self, mock_exporter, mock_file_scanner,
                                  mock_history_scanner, mock_get_name,
                                  mock_get_root, mock_is_git_repo):
        """Test complete repository scanning integration."""
        from cli.cli import scan_repo

        # Setup mocks
        mock_is_git_repo.return_value = True
        mock_get_root.return_value = Path("/tmp/repo")
        mock_get_name.return_value = "test-repo"
        
        # Mock scanner findings
        mock_history_scanner.return_value.scan_history.return_value = [
            Finding(
                repo_name="test-repo",
                commit_hash="abc123",
                file_path="secrets.txt",
                line_number=1,
                secret_type="aws_key",
                severity=Severity.CRITICAL,
                content="AKIA1234567890123456",
                fix_recommendation="Rotate AWS credentials"
            )
        ]
        
        mock_file_scanner.return_value.scan_sensitive_files.return_value = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            scan_repo(Path("/tmp/repo"), Path(temp_dir), "json")
            
            # Verify that export was called
            mock_exporter.return_value.export_all.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
