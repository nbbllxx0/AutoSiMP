# Security Policy

## Supported Scope

This repository is a research prototype for local topology-optimization
configuration and solver orchestration. It is not a hosted service and does not
process credentials on behalf of users.

## Credentials

Do not commit API keys, `.env` files, generated outputs containing private
prompts, or local experiment archives. Optional LLM-backed features read
`GEMINI_API_KEY` from the shell environment in the Python backend. Browser-side
demo keys are kept in memory only and are not intentionally persisted.

## Reporting Issues

For security-relevant issues in this research code, open a GitHub issue with a
minimal reproduction and avoid including secrets or private datasets. If the
issue contains sensitive details, first create a minimal public report that
does not disclose the secret value or exploit payload.
