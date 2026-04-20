"""Professional PDF report generator for GVD security scans using reportlab."""

from typing import List, Dict, Optional
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image,
    KeepTogether,
)

from cli.core.models import Finding


# Color palette
COLORS = {
    "primary": colors.HexColor("#1e40af"),  # Blue
    "critical": colors.HexColor("#dc2626"),  # Red
    "high": colors.HexColor("#ea580c"),  # Orange
    "medium": colors.HexColor("#ca8a04"),  # Yellow
    "low": colors.HexColor("#16a34a"),  # Green
    "text": colors.HexColor("#111827"),  # Dark text
    "muted": colors.HexColor("#6b7280"),  # Gray
    "background": colors.HexColor("#f9fafb"),  # Light background
    "border": colors.HexColor("#e5e7eb"),  # Light border
}

SEVERITY_COLORS = {
    "CRITICAL": COLORS["critical"],
    "HIGH": COLORS["high"],
    "MEDIUM": COLORS["medium"],
    "LOW": COLORS["low"],
}


def get_custom_styles():
    """Create custom paragraph styles."""
    styles = getSampleStyleSheet()
    
    # Title style
    styles.add(ParagraphStyle(
        name="CustomTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=COLORS["primary"],
        spaceAfter=6,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    ))
    
    # Subtitle style
    styles.add(ParagraphStyle(
        name="CustomSubtitle",
        parent=styles["Normal"],
        fontSize=12,
        textColor=COLORS["muted"],
        spaceAfter=12,
        alignment=TA_LEFT,
    ))
    
    # Repo header style
    styles.add(ParagraphStyle(
        name="RepoHeader",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=COLORS["primary"],
        spaceAfter=6,
        fontName="Helvetica-Bold",
        borderPadding=6,
    ))
    
    # Finding type badge
    styles.add(ParagraphStyle(
        name="FindingBadge",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    ))
    
    # Finding file path
    styles.add(ParagraphStyle(
        name="FilePath",
        parent=styles["Normal"],
        fontSize=9,
        textColor=COLORS["text"],
        fontName="Courier",
    ))
    
    # Finding recommendation
    styles.add(ParagraphStyle(
        name="Recommendation",
        parent=styles["Normal"],
        fontSize=9,
        textColor=COLORS["text"],
        leading=11,
    ))
    
    # Muted text for metadata
    styles.add(ParagraphStyle(
        name="Muted",
        parent=styles["Normal"],
        fontSize=8,
        textColor=COLORS["muted"],
    ))
    
    return styles


def build_header(styles, total_repos: int = 0):
    """Build the header section."""
    elements = []
    
    # Title
    elements.append(Paragraph("GVD Security Report", styles["CustomTitle"]))
    
    # Subtitle with metadata
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    subtitle = f"Generated on {now}"
    if total_repos > 0:
        subtitle += f" • {total_repos} repositor{'ies' if total_repos != 1 else 'y'} scanned"
    
    elements.append(Paragraph(subtitle, styles["CustomSubtitle"]))
    elements.append(Spacer(1, 0.2 * inch))
    
    return elements


def build_summary_section(styles, findings: List[Finding]):
    """Build the summary statistics section."""
    elements = []
    
    # Count findings by severity
    total = len(findings)
    critical = len([f for f in findings if f.severity.value == "CRITICAL"])
    high = len([f for f in findings if f.severity.value == "HIGH"])
    medium = len([f for f in findings if f.severity.value == "MEDIUM"])
    low = len([f for f in findings if f.severity.value == "LOW"])
    
    # Count unique repos
    repos = len(set(f.repo_name for f in findings))
    
    # Summary title
    elements.append(Paragraph("Security Summary", styles["Heading2"]))
    elements.append(Spacer(1, 0.1 * inch))
    
    # Summary statistics table
    summary_data = [
        ["Metric", "Count"],
        ["Repositories Scanned", str(repos)],
        ["Total Findings", str(total)],
        ["🔴 Critical", str(critical)],
        ["🟠 High", str(high)],
        ["🟡 Medium", str(medium)],
        ["🟢 Low", str(low)],
    ]
    
    summary_table = Table(summary_data, colWidths=[3 * inch, 1.5 * inch])
    summary_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        
        # Data rows
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLORS["background"]]),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORS["border"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        
        # Colored backgrounds for severity counts
        ("BACKGROUND", (1, 3), (1, 3), SEVERITY_COLORS["CRITICAL"]),  # Critical
        ("BACKGROUND", (1, 4), (1, 4), SEVERITY_COLORS["HIGH"]),  # High
        ("BACKGROUND", (1, 5), (1, 5), SEVERITY_COLORS["MEDIUM"]),  # Medium
        ("BACKGROUND", (1, 6), (1, 6), SEVERITY_COLORS["LOW"]),  # Low
        ("TEXTCOLOR", (1, 3), (1, 6), colors.white),  # White text for visibility
        ("FONTNAME", (1, 3), (1, 6), "Helvetica-Bold"),  # Bold for emphasis
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    return elements


def get_severity_badge(severity: str) -> str:
    """Get formatted severity badge."""
    badges = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🟢 LOW",
    }
    return badges.get(severity, severity)


def build_finding_row(styles, finding: Finding) -> Table:
    """Build a single finding row."""
    severity = finding.severity.value
    
    # Prepare content
    badge_text = get_severity_badge(severity)
    finding_type = finding.secret_type
    file_path = finding.file_path
    if finding.line_number:
        file_path += f":{finding.line_number}"
    
    recommendation = finding.fix_recommendation or "Review and remediate this finding."
    
    # Build row data
    row_data = [
        [
            Paragraph(badge_text, styles["FindingBadge"]),
            Paragraph(f"<b>{finding_type}</b><br/>{file_path}", styles["FilePath"]),
            Paragraph(recommendation, styles["Recommendation"]),
        ]
    ]
    
    # Create table for finding
    finding_table = Table(row_data, colWidths=[0.8 * inch, 2.2 * inch, 2.5 * inch])
    finding_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "TOP"),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 0), COLORS["background"]),
        ("LEFTPADDING", (0, 0), (-1, 0), 8),
        ("RIGHTPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, 0), 0.5, COLORS["border"]),
    ]))
    
    return finding_table


def build_repo_section(styles, repo_name: str, repo_findings: List[Finding]):
    """Build a section for a single repository."""
    elements = []
    
    # Repository header
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(f"📁 {repo_name}", styles["RepoHeader"]))
    
    # Count findings by severity
    critical = len([f for f in repo_findings if f.severity.value == "CRITICAL"])
    high = len([f for f in repo_findings if f.severity.value == "HIGH"])
    medium = len([f for f in repo_findings if f.severity.value == "MEDIUM"])
    low = len([f for f in repo_findings if f.severity.value == "LOW"])
    total = len(repo_findings)
    
    # Stats table
    stats_data = [
        ["Total", "Critical", "High", "Medium", "Low"],
        [str(total), str(critical), str(high), str(medium), str(low)],
    ]
    
    stats_table = Table(stats_data, colWidths=[1 * inch, 1 * inch, 1 * inch, 1 * inch, 1 * inch])
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0, 1), (-1, 1), COLORS["background"]),
    ]))
    
    elements.append(stats_table)
    elements.append(Spacer(1, 0.1 * inch))
    
    # Findings list
    if repo_findings:
        elements.append(Paragraph("Findings", styles["Heading3"]))
        elements.append(Spacer(1, 0.08 * inch))
        
        # Sort findings by severity (critical first)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_findings = sorted(
            repo_findings,
            key=lambda x: severity_order.get(x.severity.value, 999)
        )
        
        for finding in sorted_findings:
            elements.append(build_finding_row(styles, finding))
            elements.append(Spacer(1, 0.08 * inch))
    else:
        elements.append(Paragraph("✅ No findings", styles["Muted"]))
    
    return elements


def build_pdf_report(
    findings: List[Finding],
    output_path: Path,
    pagesize=letter,
    include_no_findings: bool = True,
) -> Path:
    """
    Build a professional PDF security report from findings.
    
    Args:
        findings: List of Finding objects to include in the report
        output_path: Path where the PDF will be saved
        pagesize: Page size (letter or A4)
        include_no_findings: Whether to include repos with no findings
    
    Returns:
        Path to the generated PDF
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create PDF document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=pagesize,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    
    # Get styles
    styles = get_custom_styles()
    
    # Build elements
    elements = []
    
    # Header
    total_repos = len(set(f.repo_name for f in findings))
    elements.extend(build_header(styles, total_repos))
    
    # Summary section
    if findings:
        elements.extend(build_summary_section(styles, findings))
        
        # Repository sections
        repos_dict: Dict[str, List[Finding]] = {}
        for finding in findings:
            if finding.repo_name not in repos_dict:
                repos_dict[finding.repo_name] = []
            repos_dict[finding.repo_name].append(finding)
        
        # Sort repos by critical findings (descending)
        sorted_repos = sorted(
            repos_dict.items(),
            key=lambda x: (
                len([f for f in x[1] if f.severity.value == "CRITICAL"]),
                len(x[1])
            ),
            reverse=True
        )
        
        for repo_name, repo_findings in sorted_repos:
            repo_elements = build_repo_section(styles, repo_name, repo_findings)
            elements.extend(repo_elements)
            elements.append(Spacer(1, 0.2 * inch))
    else:
        # No findings
        elements.append(Paragraph(
            "✅ No security findings detected",
            styles["Heading2"]
        ))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(
            "All repositories passed security scan.",
            styles["Normal"]
        ))
    
    # Footer
    elements.append(Spacer(1, 0.3 * inch))
    footer_text = f"<font size=8 color='{COLORS['muted'].hexval()}'>Report generated by GVD - Git Vulnerabilities Detector | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>"
    elements.append(Paragraph(footer_text, styles["Normal"]))
    
    # Build PDF
    doc.build(elements)
    
    return output_path


def build_pdf_report_from_dict(
    data: Dict,
    output_path: Path,
    pagesize=letter,
) -> Path:
    """
    Build a professional PDF security report from a dictionary.
    
    Expected dictionary structure:
    {
        "total_repos": int,
        "total_findings": int,
        "repos": [
            {
                "name": str,
                "findings": [...Finding objects or dicts...]
            }
        ]
    }
    
    Args:
        data: Dictionary containing report data
        output_path: Path where the PDF will be saved
        pagesize: Page size (letter or A4)
    
    Returns:
        Path to the generated PDF
    """
    # Convert dict findings to Finding objects if needed
    findings = []
    
    for repo_data in data.get("repos", []):
        for finding_data in repo_data.get("findings", []):
            if isinstance(finding_data, dict):
                from cli.core.models import Severity
                finding = Finding(
                    repo_name=finding_data.get("repo_name") or repo_data.get("name"),
                    commit_hash=finding_data.get("commit_hash", ""),
                    file_path=finding_data.get("file_path", ""),
                    line_number=finding_data.get("line_number"),
                    secret_type=finding_data.get("secret_type", ""),
                    severity=Severity(finding_data.get("severity", "MEDIUM")),
                    content=finding_data.get("content", ""),
                    fix_recommendation=finding_data.get("fix_recommendation", ""),
                )
                findings.append(finding)
            else:
                findings.append(finding_data)
    
    return build_pdf_report(findings, output_path, pagesize)
