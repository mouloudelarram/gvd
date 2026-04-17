from typing import List
from pathlib import Path
import json
from gvd.core.models import Finding

class ReportBuilder:
    def __init__(self, findings: List[Finding]):
        self.findings = findings

    def build_json_report(self) -> dict:
        """Build JSON report."""
        return {
            "repo_name": self.findings[0].repo_name if self.findings else "",
            "total_findings": len(self.findings),
            "findings": [
                {
                    "commit_hash": f.commit_hash,
                    "file_path": f.file_path,
                    "line_number": f.line_number,
                    "secret_type": f.secret_type,
                    "severity": f.severity.value,
                    "content": f.content,
                    "fix_recommendation": f.fix_recommendation
                }
                for f in self.findings
            ]
        }

    def build_markdown_report(self) -> str:
        """Build Markdown report."""
        md = f"# GVD Security Report\n\n"
        md += f"Repository: {self.findings[0].repo_name if self.findings else 'Unknown'}\n\n"
        md += f"Total findings: {len(self.findings)}\n\n"
        
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            sev_findings = [f for f in self.findings if f.severity.value == severity]
            if sev_findings:
                md += f"## {severity} ({len(sev_findings)})\n\n"
                for f in sev_findings:
                    md += f"- **File:** {f.file_path}\n"
                    md += f"  **Commit:** {f.commit_hash}\n"
                    if f.line_number:
                        md += f"  **Line:** {f.line_number}\n"
                    md += f"  **Type:** {f.secret_type}\n"
                    md += f"  **Fix:** {f.fix_recommendation}\n\n"
        return md

    def build_summary_text(self) -> str:
        """Build summary text."""
        total = len(self.findings)
        critical = len([f for f in self.findings if f.severity.value == "CRITICAL"])
        high = len([f for f in self.findings if f.severity.value == "HIGH"])
        medium = len([f for f in self.findings if f.severity.value == "MEDIUM"])
        low = len([f for f in self.findings if f.severity.value == "LOW"])
        
        summary = f"GVD Scan Summary\n"
        summary += f"Total findings: {total}\n"
        summary += f"Critical: {critical}\n"
        summary += f"High: {high}\n"
        summary += f"Medium: {medium}\n"
        summary += f"Low: {low}\n"
        return summary