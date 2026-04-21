# GVD - GitHub Vulnerability Detector

GVD is a lightweight GitHub-connected security project made of two parts:

- A simple SaaS web app that lets users sign in with GitHub, browse repositories, and trigger scans from a clean dashboard.
- A local-first CLI scanning engine that analyzes Git repositories for secrets, sensitive files, and security risks.

The core goal is straightforward:

> Which of my GitHub repositories might have security issues?

GVD answers that question in one place, with one login, and with minimal friction.

## Overview

GVD is designed to feel:

- Simple to use
- Fast to navigate
- Trustworthy in appearance
- Clear rather than complex

The SaaS app connects to GitHub through OAuth, fetches the user's accessible repositories, and displays them in a clean dashboard. From there, each repository can be scanned through the GVD engine after being cloned locally.

The project is intentionally lightweight. The frontend uses plain HTML and CSS. The backend is a small Flask app. The scanner is a Python CLI focused on practical repository security analysis.

## Core Features

- GitHub OAuth login
- Central dashboard of accessible repositories
- Light, clean SaaS interface
- Repository cards with visibility, description, and scan action
- Incremental loading with `See more`
- Local repository cloning before analysis
- Secret and sensitive file detection
- Git history scanning
- JSON, Markdown, and summary report generation

## Product Experience

### Authentication Flow

Users authenticate using GitHub OAuth.

Flow:

1. User clicks `Login with GitHub`
2. User is redirected to the GitHub authorization page
3. User grants access
4. GitHub redirects back to the app
5. The app exchanges the code for an access token
6. A user session is created

After login, the app:

- Retrieves the user profile
- Fetches all accessible repositories
- Displays them on the dashboard

### Dashboard Experience

The dashboard is intentionally light and structured.

Header:

- Left side: app logo and app name `GVD`
- Right side: GitHub username and logout button

Repository display:

- Grid-based layout
- 5 cards per row on large screens
- Consistent spacing and alignment
- Light theme with minimal visual noise

Each repository card contains:

- Repository name
- Visibility badge (`public` or `private`)
- Short description
- `Scan` button
- `Details` link or repository link target

Behavior:

- Clicking the card opens repository details or the repository link
- Clicking `Scan` sends the repository to the backend scanning flow

### Pagination / Loading

To keep the UI clean and fast:

- The dashboard shows 15 repositories by default
- A `See more` button loads 15 more
- This continues incrementally without overwhelming the user

### Scanning Flow

When a user clicks `Scan`:

1. The backend receives the request
2. The selected repository is cloned locally
3. The GVD scanning engine analyzes the repository
4. Findings can be exported as reports

The scan is intended to produce:

- Vulnerabilities found
- Severity
- Fix recommendations

The results UI can be expanded later, but the scanning pipeline is the foundation of the product.

## Design Philosophy

The UI is intentionally:

- Light theme
- Minimal
- Structured
- Consistent
- Easy to read and maintain

GVD avoids:

- Dark mode by default
- Heavy visuals
- Complex interactions
- Flashy animations
- Frontend frameworks for the dashboard

The intended feel is that of a reliable developer and security tool.

## Target Users

GVD is aimed at:

- Individual developers
- Indie hackers
- Small teams
- People managing many GitHub repositories
- Users who want quick security insight without operational complexity

## Project Architecture

At a high level:

```text
GitHub OAuth -> Flask SaaS app -> Repository dashboard -> Clone locally -> GVD scanner -> Reports
```

Conceptually, the project is split into:

- `saas/` for the web application
- `cli/` for the scanning engine and report generation

## Repository Structure

```text
gvd/
├── README.md
├── LICENSE
├── saas/
│   ├── app.py
│   ├── auth.py
│   ├── github.py
│   ├── clone.py
│   ├── requirements.txt
│   ├── templates/
│   │   ├── login.html
│   │   └── dashboard.html
│   ├── static/
│   │   └── style.css
│   └── repos/
├── cli/
│   ├── pyproject.toml
│   ├── README.md
│   ├── cli.py
│   ├── core/
│   │   ├── git_utils.py
│   │   └── models.py
│   ├── scanner/
│   │   ├── git_history.py
│   │   ├── file_scanner.py
│   │   ├── pattern_engine.py
│   │   └── risk_engine.py
│   ├── report/
│   │   ├── builder.py
│   │   └── exporter.py
│   └── utils/
│       └── logger.py
```

## SaaS App

The SaaS application lives in `saas/`.

Responsibilities:

- GitHub OAuth authentication
- User session management
- Fetching repositories through the GitHub API
- Displaying the dashboard
- Triggering local clone and scan actions

Main files:

- `saas/app.py` - Flask entry point and routes
- `saas/auth.py` - GitHub OAuth helpers
- `saas/github.py` - GitHub API repository fetching
- `saas/clone.py` - Local cloning logic
- `saas/templates/` - HTML templates
- `saas/static/style.css` - Dashboard styling

### Current SaaS Routes

- `/` - Login page
- `/login` - Redirect to GitHub OAuth
- `/callback` - OAuth callback handler
- `/dashboard` - Repository dashboard
- `/clone` - POST endpoint to scan a selected repository
- `/logout` - Clear session and log out

## CLI Scanner

The CLI scanner lives in `cli/`.

Responsibilities:

- Analyze Git history
- Detect secrets and risky patterns
- Detect sensitive files
- Assign severity
- Generate security reports

Scanner capabilities include:

- Full Git history scanning
- Regex-based secret detection
- Sensitive file detection
- Severity classification
- Exported reports in multiple formats

Examples of findings:

- API keys
- Tokens
- Credentials
- Private keys
- `.env` files
- Sensitive config files

## How Scanning Works

The scanner is local-first. That means repositories are scanned on the machine running GVD rather than being uploaded to an external service.

Typical flow:

1. Repository is selected from the SaaS dashboard or provided directly to the CLI
2. Git content and history are analyzed
3. Pattern matching and file checks run
4. Risk and severity are determined
5. Reports are generated for review

This approach keeps the project practical, transparent, and easier to reason about.

## Docker Setup (Recommended)

### Quick Start with Docker

The easiest way to run GVD is with Docker and Docker Compose:

```bash
# 1. Clone the project
git clone <repository-url>
cd gvd

# 2. Create environment file
cp saas/.env.example saas/.env
# Edit saas/.env with your GitHub OAuth credentials

# 3. Run with Docker Compose
docker-compose up --build

# Access the app at http://localhost:5000
```

### Docker Services

- **gvd-saas**: Flask web application (port 5000)
- **gvd-cli**: CLI scanner service
- **nginx**: Optional reverse proxy for production

For detailed Docker instructions, see [DOCKER_SETUP.md](DOCKER_SETUP.md).

---

## Local Development Setup

### Requirements

- Python 3.10+ recommended
- Git
- A GitHub OAuth application

### 1. Clone the project

```bash
git clone <repository-url>
cd gvd
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

For the SaaS app:

```bash
pip install -r saas/requirements.txt
```

For the CLI package:

```bash
pip install -e ./cli
```

If you want both environments available in one venv, installing both commands above is fine.

## GitHub OAuth Setup

Create a GitHub OAuth App at:

```text
https://github.com/settings/developers
```

Recommended callback URL:

```text
http://localhost:5000/callback
```

Create a `.env` file inside `saas/`:

```env
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
FLASK_SECRET_KEY=your_secret_key
```

GitHub scopes typically used here include:

- `repo`
- `read:user`

## Running the SaaS App

From the `saas/` directory:

```bash
python app.py
```

Then open:

```text
http://localhost:5000
```

What happens next:

1. Log in with GitHub
2. View your repositories
3. Click `Scan` on any repository
4. Let GVD clone and analyze it locally

## Running the CLI

From the project root after installing the CLI:

```bash
gvd scan
```

Scan a specific repository:

```bash
gvd scan --path /path/to/repo
```

Choose a custom output directory:

```bash
gvd scan --output ./gvd-report
```

Choose report format:

```bash
gvd scan --format json
```

## CLI Commands

```text
gvd {scan,init,help}
```

Common options:

- `--path` - path to the Git repository
- `--output` - output directory for reports
- `--format` - report format (`json`, `markdown`, or `all`)

## Reports

GVD can generate reports such as:

- `report.json`
- `report.md`
- `summary.txt`

These reports are intended to help both automation and manual review.

Typical report content includes:

- Repository name
- Total findings
- Severity
- File path
- Commit hash
- Recommendation

## Example Use Cases

- A solo developer wants to scan old side projects for leaked secrets
- A small team wants a single dashboard for checking many repositories
- A maintainer wants a local-first way to inspect Git history for exposed credentials
- A user wants a simple UI instead of running manual scans by hand

## Current State

Today, the project includes:

- A working Flask-based SaaS frontend
- GitHub OAuth login flow
- Repository listing dashboard
- Local clone flow
- A Python CLI scanner
- Report generation modules

Areas that can still be extended:

- Dedicated vulnerability results dashboard
- Severity filtering in the UI
- Auto-scan on new commits via webhooks
- Pull request suggestions or fixes
- Notifications
- Better scan result surfacing in the web app

## Future Extensions

Potential product directions:

- Results dashboard with per-repo history
- Severity filters and search
- Scheduled scans
- GitHub webhook integration
- Team accounts and shared views
- Pull request or remediation workflows
- Notifications by email or chat

## Contributing

Contributions are welcome.

A good contribution path is:

1. Fork the repository
2. Create a feature branch
3. Make focused changes
4. Test locally
5. Open a pull request

Good areas to contribute:

- Scanner accuracy improvements
- Better reporting
- Dashboard UX improvements
- Test coverage
- GitHub integration enhancements

## Security Notes

GVD is a security aid, not a guarantee.

- Findings should be reviewed by a human
- False positives are possible
- Sensitive credentials discovered during scans should be rotated immediately
- Repository history cleanup may require tools like `git filter-repo` or equivalent workflows

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Summary

GVD is a GitHub-connected SaaS plus local scanning engine built to help developers quickly understand which repositories may contain security issues.

It focuses on:

- One login
- One dashboard
- Minimal friction
- Clear UI
- Useful security signals

If you want a simple, readable, and maintainable foundation for repository security scanning, GVD is exactly that.
