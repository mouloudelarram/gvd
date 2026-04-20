# Professional PDF Report Generation

## Overview

The GVD PDF report generator transforms security scan results into professional, structured PDF reports using **reportlab.platypus**.

## Features

✅ **Professional Design**
- Clean, modern layout with proper hierarchy
- Professional color scheme
- Consistent spacing and alignment

✅ **Comprehensive Content**
- Header with title, date, and repo count
- Summary statistics with severity breakdown
- Detailed repository sections
- Finding details with recommendations

✅ **Visual Hierarchy**
- Large, bold titles
- Colored severity badges
- Organized tables instead of raw text
- Clear section separation

✅ **Severity Highlighting**
- 🔴 Critical (Red #dc2626)
- 🟠 High (Orange #ea580c)
- 🟡 Medium (Yellow #ca8a04)
- 🟢 Low (Green #16a34a)

## Usage

### Basic Usage (Automatic Integration)

The PDF export is **automatically integrated** into the report export pipeline:

```python
from pathlib import Path
from cli.core.models import Finding, Severity
from cli.report.builder import ReportBuilder
from cli.report.exporter import ReportExporter

# Create findings
findings = [
    Finding(
        repo_name="my-repo",
        commit_hash="abc123def",
        file_path="src/config.py",
        line_number=42,
        secret_type="AWS_KEY",
        severity=Severity.CRITICAL,
        content="AKIA...",
        fix_recommendation="Rotate the AWS key immediately and revoke access."
    )
]

# Build and export
builder = ReportBuilder(findings)
exporter = ReportExporter(builder, Path("./reports"))
exporter.export_all()  # Generates report.pdf + other formats
```

### Direct PDF Generation

For direct PDF generation:

```python
from pathlib import Path
from cli.report.pdf_builder import build_pdf_report

# Using Finding objects
pdf_path = build_pdf_report(
    findings=findings,
    output_path=Path("./reports/security_report.pdf")
)
print(f"Report generated at: {pdf_path}")
```

### From Dictionary Data

If you have data in dictionary format:

```python
from cli.report.pdf_builder import build_pdf_report_from_dict

data = {
    "total_repos": 2,
    "total_findings": 5,
    "repos": [
        {
            "name": "backend-api",
            "findings": [
                {
                    "repo_name": "backend-api",
                    "commit_hash": "abc123",
                    "file_path": "config.py",
                    "line_number": 10,
                    "secret_type": "DATABASE_URL",
                    "severity": "HIGH",
                    "content": "postgres://...",
                    "fix_recommendation": "Move to environment variables"
                }
            ]
        }
    ]
}

pdf_path = build_pdf_report_from_dict(
    data=data,
    output_path=Path("./reports/scan_report.pdf")
)
```

## PDF Structure

### 1. Header
```
┌─────────────────────────────────────────────┐
│ GVD Security Report                         │
│ Generated on April 20, 2026 • 5 repos       │
└─────────────────────────────────────────────┘
```

### 2. Summary Section
```
┌─────────────────────────────────────────────┐
│ Security Summary                            │
├──────────────────────┬──────────────────────┤
│ Metric               │ Count                │
├──────────────────────┼──────────────────────┤
│ Repositories Scanned │ 5                    │
│ Total Findings       │ 12                   │
│ 🔴 Critical         │ 2                    │
│ 🟠 High             │ 4                    │
│ 🟡 Medium           │ 4                    │
│ 🟢 Low              │ 2                    │
└──────────────────────┴──────────────────────┘
```

### 3. Repository Sections
```
📁 my-backend-repo

┌─────────┬──────────┬──────┬────────┬─────┐
│ Total   │ Critical │ High │ Medium │ Low │
├─────────┼──────────┼──────┼────────┼─────┤
│ 3       │ 1        │ 1    │ 1      │ 0   │
└─────────┴──────────┴──────┴────────┴─────┘

Findings:
┌─────────┬──────────────────────┬────────────────────────────────┐
│ 🔴 CRIT │ DATABASE_URL         │ Move to environment variables  │
│         │ src/config.py:42     │                                │
├─────────┼──────────────────────┼────────────────────────────────┤
│ 🟠 HIGH │ AWS_KEY              │ Rotate key and revoke access   │
│         │ .env:10              │                                │
└─────────┴──────────────────────┴────────────────────────────────┘
```

## Color Scheme

| Element      | Color   | Hex Code |
|--------------|---------|----------|
| Primary      | Blue    | #1e40af  |
| Critical     | Red     | #dc2626  |
| High         | Orange  | #ea580c  |
| Medium       | Yellow  | #ca8a04  |
| Low          | Green   | #16a34a  |
| Text         | Dark    | #111827  |
| Muted        | Gray    | #6b7280  |
| Background   | Light   | #f9fafb  |
| Border       | Light   | #e5e7eb  |

## Customization

### Change Page Size

```python
from reportlab.lib.pagesizes import A4, letter

# Use A4 instead of letter
build_pdf_report(findings, Path("report.pdf"), pagesize=A4)
```

### Custom Styling

Edit the `get_custom_styles()` function in `pdf_builder.py` to customize:
- Font sizes and names
- Colors
- Spacing
- Alignment

### Custom Colors

Modify the `COLORS` dictionary at the top of `pdf_builder.py`:

```python
COLORS = {
    "primary": colors.HexColor("#your_color"),
    "critical": colors.HexColor("#your_critical_color"),
    # ... etc
}
```

## Advanced Options

### Include/Exclude Specific Severity Levels

```python
# Filter findings before passing to build_pdf_report
filtered = [f for f in findings if f.severity.value != "LOW"]
build_pdf_report(filtered, Path("report.pdf"))
```

### Sort by Repository or Severity

The PDF automatically sorts:
- Repositories by critical findings count (descending)
- Findings within repos by severity (Critical → Low)

### No Findings Handling

When there are no findings, the report displays:
```
✅ No security findings detected
All repositories passed security scan.
```

## Dependencies

Add to `pyproject.toml`:
```toml
dependencies = ["reportlab>=4.0.0"]
```

Install with:
```bash
pip install -r requirements-dev.txt
# or
pip install reportlab
```

## Performance

- Handles 100+ findings efficiently
- Page breaks are automatic
- Memory-efficient stream processing

## Troubleshooting

### Import Error: `reportlab`
```bash
pip install reportlab
```

### PDF won't generate
- Ensure output directory exists
- Check file permissions
- Verify Finding objects have required fields

### Styling looks wrong
- Clear reportlab cache: `rm -rf ~/.reportlab_cache`
- Restart Python process

## Integration Examples

### CLI Integration

```python
# In cli.py
@click.command()
@click.option('--pdf', is_flag=True, help='Export as PDF')
def scan(pdf):
    findings = scan_repos()
    builder = ReportBuilder(findings)
    exporter = ReportExporter(builder, Path("./reports"))
    
    if pdf:
        exporter.export_all()
```

### Scheduled Reports

```python
# Generate daily reports
from schedule import every, run_pending
from cli.report.pdf_builder import build_pdf_report

def generate_daily_report():
    findings = scan_all_repos()
    output = Path(f"reports/gvd_{datetime.now():%Y%m%d}.pdf")
    build_pdf_report(findings, output)

every().day.at("09:00").do(generate_daily_report)
```

## Best Practices

✅ **Do:**
- Use semantic finding descriptions
- Include actionable recommendations
- Group related findings
- Generate reports regularly
- Archive old reports

❌ **Don't:**
- Include sensitive data in recommendations
- Generate reports for inactive repos
- Override severity levels arbitrarily
- Ignore critical findings

## Future Enhancements

Potential improvements:
- [ ] Email delivery integration
- [ ] Custom logos/branding
- [ ] Trending charts
- [ ] CVSS score integration
- [ ] Remediation timeline
- [ ] Compliance mapping (CIS, OWASP)
