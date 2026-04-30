import json
from pathlib import Path
try:
    from cli.report.builder import ReportBuilder
    from cli.report.pdf_builder import build_pdf_report
except ImportError:
    from report.builder import ReportBuilder
    from report.pdf_builder import build_pdf_report


class ReportExporter:
    def __init__(self, builder: ReportBuilder, output_dir: Path):
        self.builder = builder
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self):
        """Export all report formats."""
        try:
            # JSON
            json_data = self.builder.build_json_report()
            json_path = self.output_dir / "report.json"
            with open(json_path, "w") as f:
                json.dump(json_data, f, indent=2)
            
            # Markdown
            md_content = self.builder.build_markdown_report()
            md_path = self.output_dir / "report.md"
            with open(md_path, "w") as f:
                f.write(md_content)
            
            # Summary
            summary = self.builder.build_summary_text()
            summary_path = self.output_dir / "summary.txt"
            with open(summary_path, "w") as f:
                f.write(summary)
            
            # PDF Report
            pdf_path = self.output_dir / "report.pdf"
            build_pdf_report(self.builder.findings, pdf_path)
            
        except Exception as e:
            print(f"Error exporting reports: {e}")
            # Still try to write JSON if PDF fails
            try:
                json_data = self.builder.build_json_report()
                json_path = self.output_dir / "report.json"
                with open(json_path, "w") as f:
                    json.dump(json_data, f, indent=2)
            except Exception as json_error:
                print(f"Error writing JSON report: {json_error}")
