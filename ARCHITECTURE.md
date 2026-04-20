# GVD PDF Report Generator - Architecture & Data Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GVD CLI SYSTEM                          │
└─────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │ CLI Input    │
                          └──────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
            ┌───────▼────────┐        ┌──────▼──────┐
            │ Scanner Module │        │ Git History │
            │ (file_scanner) │        │ (git_utils) │
            └───────┬────────┘        └──────┬──────┘
                    │                         │
                    └────────────┬────────────┘
                                 │
                        ┌────────▼────────┐
                        │  FINDINGS LIST  │
                        │ [Finding, ...] │
                        └────────┬────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        │                        │                        │
        │                        │                        │
   ┌────▼──────┐        ┌────────▼────────┐      ┌─────────▼───────┐
   │ Report    │        │ Report Exporter │      │ PDF Builder     │
   │ Builder   │        │                 │      │ (NEW)           │
   └────┬──────┘        └────────┬────────┘      └─────────┬───────┘
        │                        │                         │
        │                        │                         │
   ┌────▼──────────────────┐     │     ┌───────────────────▼────────┐
   │ build_json_report()   │     │     │ build_pdf_report()         │
   │ build_markdown()      │     │     ├────────────────────────────┤
   │ build_summary_text()  │     │     │ Functions:                 │
   └────┬──────────────────┘     │     │ • build_header()           │
        │                        │     │ • build_summary_section()  │
        │                        │     │ • build_repo_section()     │
   ┌────▼──────────────────┐     │     │ • build_finding_row()      │
   │ export_all()          │     │     │ • get_custom_styles()      │
   │ (JSON, MD, TXT)       │     │     │ • COLORS design system     │
   └────┬──────────────────┘     │     └───────────────────┬────────┘
        │                        │                         │
        │◄───────────────────────┤                         │
        │                        │                         │
   ┌────▼──────────────────────────────────────────────────▼─────┐
   │                    REPORT EXPORTER                          │
   │  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
   │  │ report.json  │ │ report.md    │ │ report.pdf ✨NEW✨ │  │
   │  └──────────────┘ └──────────────┘ └────────────────────┘  │
   │  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
   │  │ summary.txt  │ │  ...more...  │ │ A4 compatible      │  │
   │  └──────────────┘ └──────────────┘ └────────────────────┘  │
   └──────────────────────────────────────────────────────────────┘
```

---

## PDF Generation Pipeline

```
INPUT: List[Finding]
   │
   │ Organize by repo
   ├──────────────────────────────────────┐
   │                                      │
   ▼                                      ▼
[Getting Styles]                   [Process Findings]
   │                                      │
   ├─ CustomTitle                         ├─ Count by severity
   ├─ RepoHeader                          ├─ Sort repositories
   ├─ FindingBadge                        ├─ Sort findings
   ├─ FilePath                            └─ Group by repo
   ├─ Recommendation                         │
   └─ Muted                                  ▼
      │                               [Get Color Scheme]
      │                                    │
      │                                    ├─ Primary Blue
      │                                    ├─ Critical Red
      │                                    ├─ High Orange
      │                                    ├─ Medium Yellow
      │                                    ├─ Low Green
      │                                    └─ Accents
      │                                       │
      └────────────────────┬─────────────────┘
                           │
                           ▼
                    [Build Elements]
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    [Header]          [Summary]          [Repos]
        │                  │                  │
        ├─ Title           ├─ Stats Table     ├─ Repo Name
        ├─ Subtitle        ├─ Counts          ├─ Stats
        └─ Date            └─ Badges          └─ Findings
                                                  │
                                    ┌─────────────┴─────────────┐
                                    │                           │
                                    ▼                           ▼
                              [Finding Row]            [Finding Row]
                                    │                           │
                                    ├─ Badge                    ├─ Badge
                                    ├─ Type & Path              ├─ Type & Path
                                    └─ Recommendation           └─ Recommendation
        │
        └────────────────┬──────────────┐
                         │              │
                         ▼              ▼
                    [Spacers]      [Styles]
                         │              │
                         └──────┬───────┘
                                │
                                ▼
                     [SimpleDocTemplate]
                                │
                                ▼
                        [PDF Generation]
                                │
                                ▼
                          OUTPUT: .pdf
```

---

## Data Transformation

```
FINDINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Finding {
  repo_name: "backend-api",
  file_path: "src/config.py",
  line_number: 42,
  secret_type: "DATABASE_URL",
  severity: CRITICAL,
  content: "postgres://...",
  fix_recommendation: "Move to env vars"
}

Finding {
  repo_name: "frontend-app",
  ...
}

         ▼ AGGREGATE & SORT

REPOSITORIES (sorted by critical count)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. "backend-api"
   Critical: 2 | High: 1 | Medium: 0 | Low: 0
   
   Findings (sorted by severity):
   - CRITICAL: DATABASE_URL
   - CRITICAL: AWS_KEY
   - HIGH: JWT_SECRET

2. "frontend-app"
   Critical: 0 | High: 1 | Medium: 1 | Low: 0
   
   Findings (sorted by severity):
   - HIGH: API_KEY
   - MEDIUM: PRIVATE_KEY

         ▼ BUILD REPORT ELEMENTS

REPORT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Header
   - Title: "GVD Security Report"
   - Subtitle: "Generated on [DATE] • 2 repos"

2. Summary Section
   - Total Repos: 2
   - Total Findings: 5
   - Critical: 2 | High: 2 | Medium: 1 | Low: 0

3. Repository Section (backend-api)
   - Stats: Total 3, Critical 2, ...
   - Finding 1: [🔴 CRITICAL] DATABASE_URL @ src/config.py:42
   - Finding 2: [🔴 CRITICAL] AWS_KEY @ .env:5
   - Finding 3: [🟠 HIGH] JWT_SECRET @ src/auth/jwt.py:15

4. Repository Section (frontend-app)
   - Stats: Total 2, Critical 0, ...
   - Finding 1: [🟠 HIGH] API_KEY @ public/config.js:8
   - Finding 2: [🟡 MEDIUM] PRIVATE_KEY @ src/utils/logger.js:23

5. Footer
   - Generated timestamp and credits

         ▼ APPLY STYLING

STYLED PDF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Typography: Helvetica/Courier fonts, proper sizes
- Colors: Blue primary, Red/Orange/Yellow/Green severity
- Tables: Header backgrounds, alternating rows
- Spacing: 0.5" margins, clear section breaks
- Layout: Letter size (8.5" × 11")

         ▼ GENERATE

PDF FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

report.pdf
- Size: ~5-10 KB (varies by finding count)
- Pages: Auto (usually 1-2)
- Format: Letter/A4
- Print-ready ✓
```

---

## Integration Flow

```
                        Your Existing Code
                        ┌─────────────────────────────┐
                        │  findings = scan_repos()    │
                        │  builder = ReportBuilder()  │
                        │  exporter = ReportExporter()│
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────┐
                        │  exporter.export_all()      │
                        │  (UNCHANGED API)            │
                        └──────────────┬──────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
        [JSON Export]            [Markdown Export]        [PDF Export] ✨NEW
              │                        │                        │
              ▼                        ▼                        ▼
        report.json              report.md                report.pdf
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                                       ▼
                            Output Directory
                         (reports/)
                         - report.json
                         - report.md
                         - report.pdf ✨
                         - summary.txt
```

---

## Class & Function Hierarchy

```
pdf_builder.py
├── COLORS (dict)
│   ├── primary
│   ├── critical
│   ├── high
│   ├── medium
│   ├── low
│   ├── text
│   ├── muted
│   ├── background
│   └── border
│
├── SEVERITY_COLORS (dict)
│
├── Functions:
│   ├── get_custom_styles() → StyleSheet
│   │   ├── CustomTitle
│   │   ├── CustomSubtitle
│   │   ├── RepoHeader
│   │   ├── FindingBadge
│   │   ├── FilePath
│   │   ├── Recommendation
│   │   └── Muted
│   │
│   ├── build_header(styles, total_repos) → List[Element]
│   │
│   ├── build_summary_section(styles, findings) → List[Element]
│   │   └── Builds summary statistics table
│   │
│   ├── build_repo_section(styles, repo_name, findings) → List[Element]
│   │   ├── Repo header
│   │   ├── Stats table
│   │   └── Findings list
│   │
│   ├── build_finding_row(styles, finding) → Table
│   │   └── Single finding display
│   │
│   ├── get_severity_badge(severity) → str
│   │
│   ├── build_pdf_report(findings, output_path, ...) → Path
│   │   ├── Orchestrates all building functions
│   │   ├── Handles sorting
│   │   ├── Generates PDF
│   │   └── Returns Path
│   │
│   └── build_pdf_report_from_dict(data, output_path, ...) → Path
│       └── Converts dict to Finding objects
│
└── Constants
    ├── PAGE CONFIGURATION
    └── DESIGN PARAMETERS
```

---

## Module Dependencies

```
pdf_builder.py
├── reportlab
│   ├── lib.pagesizes (letter, A4)
│   ├── lib.styles (getSampleStyleSheet, ParagraphStyle)
│   ├── lib.units (inch, mm)
│   ├── lib.colors (HexColor, colors)
│   ├── lib.enums (TA_CENTER, TA_LEFT, TA_RIGHT)
│   └── platypus
│       ├── SimpleDocTemplate
│       ├── Table
│       ├── TableStyle
│       ├── Paragraph
│       ├── Spacer
│       ├── PageBreak
│       └── Image
│
├── cli.core.models
│   ├── Finding
│   └── Severity
│
└── Standard Library
    ├── typing
    ├── datetime
    ├── io (BytesIO)
    └── pathlib (Path)
```

---

## File Structure

```
cli/
├── report/
│   ├── __init__.py
│   ├── builder.py              (Existing - JSON/Markdown)
│   ├── exporter.py             (MODIFIED - Added PDF)
│   ├── pdf_builder.py          (NEW - PDF Generation)
│   ├── PDF_GUIDE.md            (NEW - Documentation)
│   ├── PDF_REFERENCE.txt       (NEW - Design Reference)
│   └── example_pdf_report.py   (NEW - Examples)
│
├── core/
│   ├── __init__.py
│   └── models.py               (Finding, Severity classes)
│
├── pyproject.toml              (MODIFIED - Added reportlab)
│
└── reports/
    └── (Generated PDFs go here)

root/
├── INTEGRATION_GUIDE.md        (NEW - Integration docs)
└── PDF_ENHANCEMENT_SUMMARY.md  (NEW - Summary)
```

---

## Rendering Pipeline (Detailed)

```
STEP 1: INPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
findings: List[Finding] = [
    Finding(repo="backend-api", severity=CRITICAL, ...),
    Finding(repo="frontend-app", severity=HIGH, ...),
    ...
]

STEP 2: ORGANIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
repos_dict = {
    "backend-api": [Finding(...), Finding(...)],
    "frontend-app": [Finding(...)]
}
sorted_repos = sorted by (critical_count DESC, total_count DESC)

STEP 3: STYLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
styles = get_custom_styles()
├─ CustomTitle (28pt, bold, blue)
├─ CustomSubtitle (12pt, gray)
├─ RepoHeader (14pt, bold, blue)
├─ FindingBadge (10pt, bold)
├─ FilePath (9pt, monospace)
├─ Recommendation (9pt, normal)
└─ Muted (8pt, gray)

STEP 4: ELEMENT BUILDING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elements = []

# Add header
elements += build_header(styles, 2)
  → [Paragraph("GVD Security Report"), 
     Paragraph("Generated on..."),
     Spacer(1, 0.2*inch)]

# Add summary
elements += build_summary_section(styles, findings)
  → [Paragraph("Security Summary"),
     Spacer(1, 0.1*inch),
     Table([["Metric", "Count"], ...]),
     Spacer(1, 0.3*inch)]

# Add repo sections
for repo_name, repo_findings in sorted_repos:
    elements += build_repo_section(styles, repo_name, repo_findings)
      → [Spacer(1, 0.15*inch),
         Paragraph("📁 backend-api"),
         Table([["Total", "Critical", ...]]),
         Spacer(1, 0.1*inch),
         Paragraph("Findings"),
         Spacer(1, 0.08*inch),
         Table([["🔴 CRIT", "DATABASE_URL", "Move to env vars"]]),
         Spacer(1, 0.08*inch),
         Table([["🔴 CRIT", "AWS_KEY", "Rotate immediately"]]),
         ...]

# Add footer
elements += [Spacer(1, 0.3*inch),
             Paragraph("Report generated by GVD...")]

STEP 5: DOCUMENT CREATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
doc = SimpleDocTemplate(
    "report.pdf",
    pagesize=letter,
    rightMargin=0.5*inch,
    leftMargin=0.5*inch,
    topMargin=0.5*inch,
    bottomMargin=0.5*inch
)

STEP 6: PDF GENERATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
doc.build(elements)

✓ Automatic page breaks when needed
✓ Preserves table structure across pages
✓ Optimizes layout
✓ Compresses images (if any)

STEP 7: OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
report.pdf (5-10 KB)
├─ Professional header
├─ Summary statistics
├─ Repository sections
├─ Finding details with recommendations
└─ Footer with timestamp
```

---

This architecture ensures:
- ✅ Clean separation of concerns
- ✅ Easy customization
- ✅ Scalable design
- ✅ Professional output
- ✅ Maintainable code
