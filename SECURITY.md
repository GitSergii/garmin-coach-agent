# Security Policy

## Supported Versions

This project is under active development. Security fixes are applied on the default branch.

## Reporting a Vulnerability

Please do not open public issues for security vulnerabilities.
Report privately to the maintainer and include:

- affected file/module
- reproduction steps
- impact assessment
- suggested fix (optional)

## Security Controls

- Secrets are loaded from environment variables.
- Garmin passwords are encrypted at rest before database storage.
- Telegram access is locked to a single owner (user/chat) and private chat only.
- In production, preconfigure owner IDs and disable first-bind after bootstrap.
- ADK session persistence uses `DatabaseSessionService` with async DB URLs.
- Startup should fail fast when required skills are missing/broken or session DB config is invalid.
- NL2SQL is enabled by default for showcase (`ENABLE_NL2SQL=true`) with read-only query guardrails.
- If NL2SQL is enabled, only single-statement read-only `SELECT` queries are allowed.

## Operator Checklist

- Rotate keys immediately if they were ever committed.
- Enable repository secret scanning.
- Use least-privilege database credentials in production.
- Keep `.env` out of version control.
