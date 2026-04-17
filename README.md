# GVD - Git Vulnerabilities Detector

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fast, local-first CLI security tool that detects exposed secrets and sensitive data in Git repository history. Built for developers who want to scan their repositories for leaked credentials without relying on external services.

## ✨ Features

- 🔍 **Full Git History Scanning** - Analyzes all commits, branches, and history
- 🛡️ **Secret Detection** - Finds API keys, passwords, tokens, and credentials
- 📁 **Sensitive File Detection** - Identifies dangerous files like `.env`, private keys
- ⚡ **Fast & Offline** - No internet required, streaming analysis
- 🎨 **Rich CLI Interface** - Beautiful terminal output with progress bars
- 📊 **Structured Reports** - JSON, Markdown, and summary outputs
- 🏗️ **Standalone Executable** - Build single-file binaries for distribution

## 🚀 Quick Start

### Installation

#### Option 1: Install from source
```bash
git clone <repository-url>
cd gvd
pip install .
```

#### Option 2: Development installation
```bash
git clone <repository-url>
cd gvd
pip install -e .
```

### Basic Usage

```bash
# Scan current directory
gvd scan

# Scan specific repository
gvd scan --path /path/to/repo

# Custom output directory
gvd scan --output ./security-reports

# Generate specific report format
gvd scan --format json
```

## 🏗️ Building Standalone Executable

### Prerequisites
- Python 3.8+
- Git

### Build Steps

1. **Install dependencies:**
```bash
pip install -e .
pip install pyinstaller
```

2. **Build executable:**
```bash
# For Windows
pyinstaller --onefile gvd/cli.py

# For Linux/Mac
pyinstaller --onefile gvd/cli.py
```

3. **Find the executable:**
   - Windows: `dist/cli.exe` (rename to `gvd.exe`)
   - Linux/Mac: `dist/cli` (rename to `gvd`)

4. **Test the executable:**
```bash
./gvd --help
```

## 📖 Usage Guide

### Command Line Options

```
Usage: gvd [-h] [--path PATH] [--output OUTPUT] [--format {json,markdown,all}]
           {scan,init,help}

GVD - Git Vulnerabilities Detector

positional arguments:
  {scan,init,help}      Command to run

options:
  -h, --help            show this help message and exit
  --path PATH           Path to git repository (default: current directory)
  --output OUTPUT       Output directory for reports (default: ./gvd-report)
  --format {json,markdown,all}
                        Report format (default: all)
```

### Commands

- `gvd scan` - Scan repository for vulnerabilities
- `gvd init` - Initialize GVD (placeholder)
- `gvd help` - Show help information

### Example Output

```
Scanning repository: my-project
Scanning git history for patterns... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
Scanning for sensitive files...      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

                               Security Findings
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity ┃ Type           ┃ File      ┃ Commit   ┃ Fix                       ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ CRITICAL │ aws_key        │ config.py │ a1b2c3d  │ Rotate AWS credentials    │
│          │                │           │          │ immediately               │
│ HIGH     │ sensitive_file │ .env      │ e4f5g6h  │ Remove sensitive file     │
│          │                │           │          │ from repository history   │
│          │                │           │          │ using git filter-repo     │
└──────────┴────────────────┴───────────┴──────────┴───────────────────────────┘

Reports exported to gvd-report
```

## 📊 Report Formats

GVD generates three types of reports in the output directory:

### JSON Report (`report.json`)
Machine-readable format with detailed findings:
```json
{
  "repo_name": "my-project",
  "total_findings": 2,
  "findings": [
    {
      "commit_hash": "a1b2c3d...",
      "file_path": "config.py",
      "secret_type": "aws_key",
      "severity": "CRITICAL",
      "content": "AWS_KEY = \"AKIAIOSFODNN7EXAMPLE\"",
      "fix_recommendation": "Rotate AWS credentials immediately"
    }
  ]
}
```

### Markdown Report (`report.md`)
Human-readable format with formatted tables and recommendations.

### Summary Text (`summary.txt`)
Quick overview with statistics.

## 🔍 Detection Capabilities

### Secret Patterns
- **AWS Keys**: `AKIA[0-9A-Z]{16}`
- **API Keys**: Generic patterns with 20+ characters
- **Tokens**: Authentication tokens
- **Database URLs**: Connection strings with credentials
- **Private Keys**: RSA/DSA key blocks
- **Passwords**: Password assignments

### Sensitive Files
- `.env` and `.env.*` files
- SSH keys (`id_rsa`, `id_dsa`)
- Certificate files (`*.pem`, `*.key`)
- Config files (`credentials.json`, `secrets.json`, `config.production.*`)

### Severity Levels
- 🔴 **CRITICAL**: Private keys, AWS credentials, database passwords
- 🟠 **HIGH**: API keys, tokens, sensitive files
- 🟡 **MEDIUM**: Config files with sensitive data
- 🟢 **LOW**: Suspicious naming patterns

## 🛠️ Development

### Setup Development Environment
```bash
git clone <repository-url>
cd gvd
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
pip install -r requirements-dev.txt  # If exists
```

### Project Structure
```
gvd/
├── cli.py              # Main CLI entry point
├── scanner/            # Scanning modules
│   ├── git_history.py  # Git history analysis
│   ├── file_scanner.py # File-based detection
│   ├── pattern_engine.py # Regex patterns
│   └── risk_engine.py  # Risk assessment
├── core/               # Core utilities
│   ├── git_utils.py    # Git operations
│   └── models.py       # Data models
├── report/             # Report generation
│   ├── builder.py      # Report building
│   └── exporter.py     # File export
└── utils/              # Utilities
    └── logger.py       # Logging
```

### Running Tests
```bash
# Run the scanner on test repository
gvd scan --path test-repo
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

GVD is a security tool designed to help identify potential security issues in Git repositories. Always verify findings manually and follow your organization's security procedures when handling sensitive data.

## 📚 Handbook

For detailed usage examples, troubleshooting, and advanced features, see the [HANDBOOK.md](HANDBOOK.md) file.