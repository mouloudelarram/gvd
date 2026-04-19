import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from cli.core.git_utils import is_git_repo, get_repo_root, get_repo_name
from cli.scanner.pattern_engine import PatternEngine
from cli.scanner.git_history import GitHistoryScanner
from cli.scanner.file_scanner import FileScanner
from cli.scanner.risk_engine import RiskEngine
from cli.report.builder import ReportBuilder
from cli.report.exporter import ReportExporter
from cli.utils.logger import setup_logger

logger = setup_logger()
console = Console()

def main():
    parser = argparse.ArgumentParser(description="GVD - Git Vulnerabilities Detector")
    parser.add_argument("command", choices=["scan", "init", "help"], help="Command to run")
    parser.add_argument("--path", default=".", help="Path to git repository")
    parser.add_argument("--output", default="./gvd-report", help="Output directory for reports")
    parser.add_argument("--format", choices=["json", "markdown", "all"], default="all", help="Report format")
    
    args = parser.parse_args()
    
    if args.command == "help":
        parser.print_help()
        return
    
    if args.command == "init":
        console.print("GVD initialized. Run 'gvd scan' to start scanning.")
        return
    
    if args.command == "scan":
        scan_repo(Path(args.path), Path(args.output), args.format)

def scan_repo(repo_path: Path, output_dir: Path, format: str):
    """Scan the repository."""
    if not is_git_repo(repo_path):
        console.print("[red]Error: Not a git repository[/red]")
        sys.exit(1)
    
    repo_root = get_repo_root(repo_path)
    repo_name = get_repo_name(repo_path)
    
    console.print(f"[green]Scanning repository: {repo_name}[/green]")
    
    pattern_engine = PatternEngine()
    history_scanner = GitHistoryScanner(pattern_engine)
    file_scanner = FileScanner()
    risk_engine = RiskEngine()
    
    findings = []
    
    with Progress() as progress:
        task1 = progress.add_task("[cyan]Scanning git history for patterns...", total=1)
        for finding in history_scanner.scan_history(repo_root, repo_name):
            finding = risk_engine.assess_risk(finding)
            findings.append(finding)
        progress.update(task1, completed=1)
        
        task2 = progress.add_task("[cyan]Scanning for sensitive files...", total=1)
        file_findings = file_scanner.scan_sensitive_files(repo_root, repo_name)
        for finding in file_findings:
            finding = risk_engine.assess_risk(finding)
            findings.append(finding)
        progress.update(task2, completed=1)
    
    # Display results
    display_findings(findings)
    
    # Export reports
    if findings or format != "none":
        builder = ReportBuilder(findings)
        exporter = ReportExporter(builder, output_dir)
        exporter.export_all()
        console.print(f"[green]Reports exported to {output_dir}[/green]")

def display_findings(findings: list):
    """Display findings in a table."""
    if not findings:
        console.print("[green]No vulnerabilities found![/green]")
        return
    
    table = Table(title="Security Findings")
    table.add_column("Severity", style="bold")
    table.add_column("Type")
    table.add_column("File")
    table.add_column("Commit")
    table.add_column("Fix")
    
    color_map = {
        "CRITICAL": "red",
        "HIGH": "yellow",
        "MEDIUM": "blue",
        "LOW": "green"
    }
    
    for f in findings:
        color = color_map.get(f.severity.value, "white")
        table.add_row(
            f"[{color}]{f.severity.value}[/{color}]",
            f.secret_type,
            f.file_path,
            f.commit_hash[:8],
            f.fix_recommendation
        )
    
    console.print(table)

if __name__ == "__main__":
    main()