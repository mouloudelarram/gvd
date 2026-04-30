"""PDF generation service for GVD Flask application."""

from textwrap import wrap


def pdf_escape(value):
    """Escape special characters for PDF generation."""
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_bytes(lines):
    """Build PDF bytes from text lines."""
    wrapped_lines = []
    for line in lines:
        line = line or ""
        wrapped_lines.extend(wrap(line, width=95) or [""])

    lines_per_page = 44
    pages = [
        wrapped_lines[index:index + lines_per_page]
        for index in range(0, len(wrapped_lines), lines_per_page)
    ] or [["GVD report"]]

    objects = []
    kids = []
    font_ref = 3
    next_object_id = 4

    for page_lines in pages:
        page_id = next_object_id
        content_id = next_object_id + 1
        kids.append(f"{page_id} 0 R")

        text_commands = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in page_lines:
            text_commands.append(f"({pdf_escape(line)}) Tj")
            text_commands.append("T*")
        text_commands.append("ET")
        content_stream = "\n".join(text_commands).encode("latin-1", errors="replace")

        objects.append(
            (
                page_id,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_ref} 0 R >> >> /Contents {content_id} 0 R >>".encode("latin-1")
            )
        )
        objects.append(
            (
                content_id,
                b"<< /Length " + str(len(content_stream)).encode("ascii") + b" >>\nstream\n" + content_stream + b"\nendstream"
            )
        )
        next_object_id += 2

    pages_object = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("latin-1")
    objects = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, pages_object),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ] + objects

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, payload in objects:
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_position = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_repo_pdf_lines(scan_result):
    """Build PDF lines for repository report."""
    severity_counts = scan_result.get("severity_counts") or {}
    lines = [
        f"GVD Repository Report - {scan_result.get('owner', '')}/{scan_result.get('repo_name', '')}",
        "",
        f"Local path: {scan_result.get('repo_path', '')}",
        f"Findings: {scan_result.get('total_findings', 0)}",
        f"Critical: {severity_counts.get('CRITICAL', 0)}",
        f"High: {severity_counts.get('HIGH', 0)}",
        f"Medium: {severity_counts.get('MEDIUM', 0)}",
        f"Low: {severity_counts.get('LOW', 0)}",
        "",
        "Findings detail",
        "",
    ]

    findings = scan_result.get("findings", [])
    if not findings:
        lines.append("No vulnerabilities found.")
        return lines

    for finding in findings:
        lines.extend(
            [
                f"- Severity: {finding.get('severity', 'Unknown')}",
                f"  Type: {finding.get('secret_type', 'Unknown')}",
                f"  File: {finding.get('file_path', 'Unknown file')}",
                f"  Commit: {finding.get('commit_hash', 'N/A')}",
                f"  Fix: {finding.get('fix_recommendation', 'None')}",
                "",
            ]
        )
    return lines


def build_bulk_pdf_lines(report):
    """Build PDF lines for bulk scan report."""
    severity_counts = report.get("severity_counts") or {}
    lines = [
        "GVD Bulk Scan Report",
        "",
        f"Generated at: {report.get('generated_at', '')}",
        f"Repositories scanned: {report.get('scanned_repositories', 0)}",
        f"Repositories failed: {report.get('failed_repositories', 0)}",
        f"Total findings: {report.get('total_findings', 0)}",
        f"Critical: {severity_counts.get('CRITICAL', 0)}",
        f"High: {severity_counts.get('HIGH', 0)}",
        f"Medium: {severity_counts.get('MEDIUM', 0)}",
        f"Low: {severity_counts.get('LOW', 0)}",
        "",
        "Repository results",
        "",
    ]

    for repo in report.get("repositories", []):
        repo_counts = repo.get("severity_counts") or {}
        lines.extend(
            [
                f"- {repo.get('owner', '')}/{repo.get('repo_name', '')}",
                f"  Findings: {repo.get('total_findings', 0)}",
                f"  Critical: {repo_counts.get('CRITICAL', 0)} | High: {repo_counts.get('HIGH', 0)} | Medium: {repo_counts.get('MEDIUM', 0)} | Low: {repo_counts.get('LOW', 0)}",
                f"  Local path: {repo.get('repo_path', '')}",
            ]
        )
        findings = repo.get("findings", [])
        if findings:
            lines.append("  Findings detail:")
            for finding in findings:
                lines.append(
                    f"    {finding.get('severity', 'Unknown')} | {finding.get('secret_type', 'Unknown')} | "
                    f"{finding.get('file_path', 'Unknown file')} | Fix: {finding.get('fix_recommendation', 'None')}"
                )
        lines.append("")

    if report.get("failures"):
        lines.extend(["Failed repositories", ""])
        for failure in report["failures"]:
            lines.append(f"- {failure.get('owner', '')}/{failure.get('repo_name', '')}: {failure.get('error', 'Unknown error')}")

    return lines
