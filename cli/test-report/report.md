# GVD Security Report

Repository: gvd

Total findings: 6

## CRITICAL (3)

- **File:** HANDBOOK.md
  **Commit:** 4424a2c17b95b0d3174a6ff1d8c860fef3204dff
  **Type:** aws_key
  **Fix:** Rotate AWS credentials immediately

- **File:** README.md
  **Commit:** 4424a2c17b95b0d3174a6ff1d8c860fef3204dff
  **Type:** aws_key
  **Fix:** Rotate AWS credentials immediately

- **File:** gvd/scanner/pattern_engine.py
  **Commit:** 4424a2c17b95b0d3174a6ff1d8c860fef3204dff
  **Type:** private_key
  **Fix:** Remove private key from repository

## HIGH (3)

- **File:** DOCKER_SETUP.md
  **Commit:** ed8432784c5da71ab8982e3b6fd1f8fdb80c4565
  **Type:** secret
  **Fix:** Remove secret from repository

- **File:** saas/.env.example
  **Commit:** ed8432784c5da71ab8982e3b6fd1f8fdb80c4565
  **Type:** secret
  **Fix:** Remove secret from repository

- **File:** HANDBOOK.md
  **Commit:** 4424a2c17b95b0d3174a6ff1d8c860fef3204dff
  **Type:** token
  **Fix:** Rotate token and check for exposure

