# GVD Handbook

This handbook provides comprehensive guidance for using GVD (Git Vulnerabilities Detector) effectively in various scenarios.

## Table of Contents

- [Quick Start](#quick-start)
- [Advanced Usage](#advanced-usage)
- [Understanding Reports](#understanding-reports)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [Integration Examples](#integration-examples)
- [Performance Tips](#performance-tips)

## Quick Start

### Basic Scanning

```bash
# Scan current repository
gvd scan

# Scan a specific repository
gvd scan --path /path/to/my/project

# Save reports to custom directory
gvd scan --output ./security-audit
```

### First Run Example

When you run GVD on a repository for the first time:

```
$ gvd scan
Scanning repository: my-app
Scanning git history for patterns... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
Scanning for sensitive files...      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

                               Security Findings
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity ┃ Type           ┃ File      ┃ Commit   ┃ Fix                       ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┫
│ CRITICAL │ aws_key        │ config.py │ a1b2c3d  │ Rotate AWS credentials    │
│          │                │           │          │ immediately               │
└──────────┴────────────────┴───────────┴──────────┴───────────────────────────┘

Reports exported to gvd-report
```

## Advanced Usage

### Scanning Large Repositories

For repositories with extensive history:

```bash
# Scan with custom output for large repos
gvd scan --path /large/repo --output /tmp/gvd-large-repo

# Focus on specific branches
cd /path/to/repo
git checkout main
gvd scan  # Only scans reachable history from main
```

### CI/CD Integration

#### GitHub Actions Example

```yaml
name: Security Scan
on: [push, pull_request]

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
      with:
        fetch-depth: 0  # Fetch full history

    - name: Install GVD
      run: |
        pip install git+https://github.com/your-org/gvd.git

    - name: Run Security Scan
      run: gvd scan --output ./security-reports

    - name: Upload Reports
      uses: actions/upload-artifact@v3
      with:
        name: security-reports
        path: security-reports/
```

#### GitLab CI Example

```yaml
security_scan:
  image: python:3.9
  before_script:
    - pip install git+https://github.com/your-org/gvd.git
  script:
    - gvd scan --output ./security-reports
  artifacts:
    paths:
      - security-reports/
    expire_in: 1 week
  only:
    - merge_requests
    - main
```

### Pre-commit Hook

Add GVD to your pre-commit hooks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: gvd-scan
        name: GVD Security Scan
        entry: gvd
        args: [scan]
        language: system
        pass_filenames: false
```

## Understanding Reports

### JSON Report Structure

The `report.json` file contains machine-readable findings:

```json
{
  "repo_name": "my-project",
  "total_findings": 3,
  "findings": [
    {
      "commit_hash": "a1b2c3d4e5f6...",
      "file_path": "config/production.py",
      "line_number": null,
      "secret_type": "aws_key",
      "severity": "CRITICAL",
      "content": "AWS_ACCESS_KEY_ID = \"AKIAIOSFODNN7EXAMPLE\"",
      "fix_recommendation": "Rotate AWS credentials immediately"
    },
    {
      "commit_hash": "b2c3d4e5f6g7...",
      "file_path": ".env",
      "line_number": null,
      "secret_type": "token",
      "severity": "HIGH",
      "content": "GITHUB_TOKEN=ghp_1234567890abcdef...",
      "fix_recommendation": "Rotate token and check for exposure"
    }
  ]
}
```

### Severity Levels Explained

#### CRITICAL 🔴
- **Private Keys**: RSA/DSA/ECDSA private key blocks
- **AWS Credentials**: Access keys and secret keys
- **Database Passwords**: Connection strings with embedded passwords
- **SSH Keys**: Private SSH keys

#### HIGH 🟠
- **API Keys**: Generic API keys and tokens
- **Authentication Tokens**: OAuth tokens, JWTs, etc.
- **Sensitive Files**: `.env`, `credentials.json`, private key files

#### MEDIUM 🟡
- **Config Files**: Production configs with sensitive data
- **Environment Variables**: Potentially sensitive env vars

#### LOW 🟢
- **Suspicious Patterns**: Files with "secret" in name but no actual secrets
- **Generic Passwords**: Weak or obvious passwords

### Report Analysis Tips

1. **Focus on CRITICAL first**: These require immediate action
2. **Check commit dates**: Older findings might already be mitigated
3. **Verify false positives**: Not all matches are actual secrets
4. **Review fix recommendations**: Each finding includes specific remediation steps

## Troubleshooting

### Common Issues

#### "Not a git repository" Error

```
Error: Not a git repository
```

**Solutions:**
- Ensure you're in a Git repository directory
- Use `--path` to specify the correct repository path
- Check if the `.git` directory exists

#### No Findings When Secrets Exist

**Possible causes:**
- Secrets might be in binary files (GVD only scans text)
- Patterns might not match your specific secret format
- Secrets might be in uncommitted changes (use `git add` first)

#### Performance Issues with Large Repositories

**Solutions:**
- Use `--output` to specify a fast storage location
- Consider scanning specific branches instead of all history
- Run during off-peak hours

#### Permission Errors

**On Windows:**
```bash
# Run PowerShell as Administrator
# Or use --output with a user-writable directory
gvd scan --output C:\Users\YourName\Desktop\reports
```

**On Linux/Mac:**
```bash
# Ensure write permissions to output directory
chmod 755 /path/to/output/dir
```

### Debug Mode

Enable verbose logging (if implemented):

```bash
# Set environment variable for debug output
export GVD_DEBUG=1
gvd scan
```

### False Positives

Common false positive scenarios:

1. **Test files**: `test_config.py` with dummy credentials
2. **Documentation**: Code examples in comments
3. **Environment variables**: `os.getenv("API_KEY")` calls
4. **Revoked credentials**: Already rotated keys

**Mitigation:**
- Review findings manually
- Use `.gvdignore` patterns (future feature)
- Focus on recent commits for active threats

## Best Practices

### Security Workflow Integration

1. **Pre-commit hooks**: Catch secrets before committing
2. **CI/CD pipelines**: Automated scanning on every push
3. **Regular audits**: Monthly scans of critical repositories
4. **Team training**: Educate developers about secret handling

### Repository Hygiene

#### Immediate Actions for Findings

**For CRITICAL findings:**
1. Rotate the credentials immediately
2. Update all systems using the old credentials
3. Remove from Git history using `git filter-repo`
4. Notify affected team members

**For HIGH findings:**
1. Assess exposure risk
2. Rotate tokens/keys
3. Update dependent systems
4. Consider history removal

#### Prevention

1. **Use environment variables**:
   ```python
   # Good
   api_key = os.getenv("API_KEY")

   # Bad
   api_key = "sk-1234567890abcdef"
   ```

2. **Never commit sensitive files**:
   - Add sensitive files to `.gitignore`
   - Use `.env.example` templates instead of real `.env` files

3. **Use secret management tools**:
   - AWS Secrets Manager
   - HashiCorp Vault
   - GitHub Secrets (for CI/CD)

### Team Guidelines

#### Developer Checklist

- [ ] Run `gvd scan` before pushing to shared branches
- [ ] Never commit real credentials
- [ ] Use environment variables for secrets
- [ ] Add sensitive files to `.gitignore`
- [ ] Review PRs for accidental secret commits

#### Security Team Checklist

- [ ] Regular repository audits
- [ ] Monitor for new secret types
- [ ] Update GVD patterns as needed
- [ ] Provide training on secure coding practices

## Integration Examples

### Jenkins Pipeline

```groovy
pipeline {
    agent any
    stages {
        stage('Security Scan') {
            steps {
                script {
                    sh 'pip install git+https://github.com/your-org/gvd.git'
                    sh 'gvd scan --output security-reports'
                }
            }
            post {
                always {
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'security-reports',
                        reportFiles: 'report.html',
                        reportName: 'GVD Security Report'
                    ])
                }
            }
        }
    }
}
```

### Azure DevOps Pipeline

```yaml
stages:
- stage: Security
  jobs:
  - job: GVD_Scan
    pool:
      vmImage: 'ubuntu-latest'
    steps:
    - checkout: self
      fetchDepth: 0
    - script: |
        python -m pip install --upgrade pip
        pip install git+https://github.com/your-org/gvd.git
        gvd scan --output $(Build.ArtifactStagingDirectory)/security-reports
      displayName: 'Run GVD Security Scan'
    - publish: $(Build.ArtifactStagingDirectory)/security-reports
      artifact: SecurityReports
      displayName: 'Publish Security Reports'
```

### Docker Integration

```dockerfile
FROM python:3.9-slim

# Install GVD
RUN pip install git+https://github.com/your-org/gvd.git

# Set working directory
WORKDIR /repo

# Run scan
CMD ["gvd", "scan", "--output", "/reports"]
```

Usage:
```bash
docker run --rm -v $(pwd):/repo -v /tmp/reports:/reports gvd-image
```

## Performance Tips

### Optimizing Scan Speed

1. **Repository size matters**:
   - Small repos (< 100 commits): Instant results
   - Medium repos (100-1000 commits): Few seconds
   - Large repos (1000+ commits): Minutes

2. **Storage location**:
   - Use SSD storage for output directory
   - Avoid network-mounted drives

3. **Git configuration**:
   ```bash
   # Speed up Git operations
   git config --global core.preloadIndex true
   git config --global core.fscache true
   ```

### Memory Usage

- GVD uses streaming processing to minimize memory usage
- For very large repositories, consider:
  - Increasing system RAM
  - Scanning during low-memory periods
  - Using `--format json` for smaller output

### Parallel Scanning

For scanning multiple repositories:

```bash
# Bash script for batch scanning
#!/bin/bash
repos=("repo1" "repo2" "repo3")
for repo in "${repos[@]}"; do
    echo "Scanning $repo..."
    gvd scan --path "$repo" --output "reports/$repo"
done
```

## Support and Contributing

### Getting Help

1. **Check this handbook first**
2. **Review GitHub issues** for similar problems
3. **Create an issue** with:
   - GVD version (`gvd --version`)
   - Repository size (commit count)
   - Error messages
   - Expected vs actual behavior

### Contributing to GVD

We welcome contributions! See the main README for development setup.

**Areas for contribution:**
- New secret patterns
- Performance optimizations
- Additional report formats
- Integration with other tools
- Documentation improvements

### Roadmap

**Planned features:**
- `.gvdignore` configuration files
- Custom pattern definitions
- SARIF report format for GitHub Security tab
- GitHub Actions integration
- Performance profiling and optimization
- Multi-threaded scanning

---

*This handbook is continuously updated. Check back for new content and features.*