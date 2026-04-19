# Minimal GitHub Repo SaaS

## Setup

Create a GitHub OAuth app:

https://github.com/settings/developers

Set callback URL to:

`http://localhost:5000/callback`

Create a `.env` file in `saas/` with:

`GITHUB_CLIENT_ID=`

`GITHUB_CLIENT_SECRET=`

`FLASK_SECRET_KEY=`

Install:

`pip install -r requirements.txt`

Run:

`python app.py`

Then open `http://localhost:5000`.
