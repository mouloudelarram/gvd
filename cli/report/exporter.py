import json
from pathlib import Path
from cli.report.builder import ReportBuilder
from cli.report.pdf_builder import build_pdf_report

class ReportExporter:
    def __init__(self, builder: ReportBuilder, output_dir: Path):
        self.builder = builder
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)

    def export_all(self):
        """Export all report formats."""
        # JSON
        json_data = self.builder.build_json_report()
        with open(self.output_dir / "report.json", "w") as f:
            json.dump(json_data, f, indent=2)
        
        # Markdown
        md_content = self.builder.build_markdown_report()
        with open(self.output_dir / "report.md", "w") as f:
            f.write(md_content)
        
        # Summary
        summary = self.builder.build_summary_text()
        with open(self.output_dir / "summary.txt", "w") as f:
            f.write(summary)
        
        # PDF Report
        pdf_path = self.output_dir / "report.pdf"
        build_pdf_report(self.builder.findings, pdf_path)