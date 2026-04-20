"""
Example script demonstrating PDF report generation with GVD.

Usage:
    python -m cli.report.example_pdf_report
    or from parent directory: python -m cli.report.example_pdf_report
"""

import sys
from pathlib import Path

# Add parent directory to path if needed
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cli.core.models import Finding, Severity
from cli.report.builder import ReportBuilder
from cli.report.exporter import ReportExporter
from cli.report.pdf_builder import build_pdf_report


def generate_example_findings():
    """Generate example findings for demonstration."""
    return [
        # Critical findings
        Finding(
            repo_name="backend-api",
            commit_hash="abc123def456",
            file_path="src/config/database.py",
            line_number=42,
            secret_type="DATABASE_URL",
            severity=Severity.CRITICAL,
            content="postgres://admin:supersecret@db.internal:5432/prod",
            fix_recommendation="Move database credentials to environment variables and use AWS Secrets Manager for production.",
        ),
        Finding(
            repo_name="backend-api",
            commit_hash="def789ghi012",
            file_path=".env.local",
            line_number=5,
            secret_type="AWS_ACCESS_KEY",
            severity=Severity.CRITICAL,
            content="AKIA3XAMPLE...",
            fix_recommendation="Rotate AWS credentials immediately. Revoke this access key and generate a new one.",
        ),
        
        # High severity findings
        Finding(
            repo_name="backend-api",
            commit_hash="ghi345jkl678",
            file_path="src/auth/jwt.py",
            line_number=15,
            secret_type="JWT_SECRET",
            severity=Severity.HIGH,
            content="super-secret-jwt-key-change-this",
            fix_recommendation="Use a strong, randomly generated JWT secret. Consider using RSA key pairs.",
        ),
        Finding(
            repo_name="frontend-app",
            commit_hash="jkl901mno234",
            file_path="public/config.js",
            line_number=8,
            secret_type="API_KEY",
            severity=Severity.HIGH,
            content="sk_live_exampleapikey12345678",
            fix_recommendation="API keys should never be committed. Use environment variables and runtime injection.",
        ),
        
        # Medium severity findings
        Finding(
            repo_name="frontend-app",
            commit_hash="mno567pqr890",
            file_path="src/utils/logger.js",
            line_number=23,
            secret_type="PRIVATE_KEY",
            severity=Severity.MEDIUM,
            content="-----BEGIN RSA PRIVATE KEY-----",
            fix_recommendation="Remove private keys from source code. Use key management services.",
        ),
        Finding(
            repo_name="data-pipeline",
            commit_hash="pqr123stu456",
            file_path="notebooks/analysis.ipynb",
            line_number=42,
            secret_type="STRIPE_KEY",
            severity=Severity.MEDIUM,
            content="rk_live_example...",
            fix_recommendation="Sensitive keys should be managed through secure vaults, not notebooks.",
        ),
        
        # Low severity findings
        Finding(
            repo_name="data-pipeline",
            commit_hash="stu789vwx012",
            file_path="README.md",
            line_number=15,
            secret_type="EMAIL_EXPOSED",
            severity=Severity.LOW,
            content="admin@company.internal",
            fix_recommendation="Consider removing internal email addresses from public documentation.",
        ),
    ]


def main():
    """Generate example PDF report."""
    
    # Create example findings
    findings = generate_example_findings()
    
    # Create output directory
    output_dir = Path("./example_reports")
    output_dir.mkdir(exist_ok=True)
    
    print(f"Generating example security report with {len(findings)} findings...")
    print(f"Output directory: {output_dir.resolve()}")
    print()
    
    # Method 1: Using ReportBuilder and ReportExporter (generates all formats)
    print("Method 1: Full Export (JSON, Markdown, Summary, PDF)")
    print("-" * 60)
    
    builder = ReportBuilder(findings)
    exporter = ReportExporter(builder, output_dir)
    exporter.export_all()
    
    print(f"✓ Generated report.json")
    print(f"✓ Generated report.md")
    print(f"✓ Generated summary.txt")
    print(f"✓ Generated report.pdf")
    print()
    
    # Method 2: Direct PDF generation
    print("Method 2: Direct PDF Generation")
    print("-" * 60)
    
    pdf_path = build_pdf_report(
        findings=findings,
        output_path=output_dir / "direct_report.pdf"
    )
    print(f"✓ Generated {pdf_path.name}")
    print()
    
    # Print summary stats
    print("Report Summary")
    print("-" * 60)
    print(f"Total Findings: {len(findings)}")
    print(f"Repositories: {len(set(f.repo_name for f in findings))}")
    print(f"Critical: {len([f for f in findings if f.severity.value == 'CRITICAL'])}")
    print(f"High: {len([f for f in findings if f.severity.value == 'HIGH'])}")
    print(f"Medium: {len([f for f in findings if f.severity.value == 'MEDIUM'])}")
    print(f"Low: {len([f for f in findings if f.severity.value == 'LOW'])}")
    print()
    
    # List generated files
    print("Generated Files")
    print("-" * 60)
    for file in sorted(output_dir.glob("*")):
        size_kb = file.stat().st_size / 1024
        print(f"  {file.name:<25} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
