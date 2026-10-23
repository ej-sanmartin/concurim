# Security policy

## Model

- The viewer is local-only: it binds `127.0.0.1`, rejects other `Host`
  headers, sends a strict CSP, has no write endpoints, serves static files
  with path containment, and serves source text only from the loaded trace.
- Traces are data: they are parsed with `json` and validated; size limits
  apply; nothing is unpickled or executed. Strings are rendered as text.
- No telemetry, uploads, accounts, or network use.
- Recording can expose information. Source embedding and payload previews are
  opt-in; previews cover only built-in primitives, are redacted by configured
  patterns *before* truncation, and never call `repr()` on user objects.

## Reporting

Please report vulnerabilities privately through GitHub Security Advisories on
the repository (or by email to the maintainers once published) instead of a
public issue. Include a trace or steps to reproduce. We aim to acknowledge
within a few days.

## Sharing traces

A `.concurim` file may contain file paths, thread names, queue names and, if
enabled, source code or data previews. Review with `concurim inspect` and the
viewer's **Trace** tab before sharing.
