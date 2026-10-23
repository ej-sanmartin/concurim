# Security policy

## Model

- The viewer is local-only: it binds `127.0.0.1`, rejects other `Host`
  headers, sends a strict CSP, serves static files
  with path containment, and serves source text only from the loaded trace.
- The viewer has a small write surface: opening a trace, uploading a program to
  a private scratch directory, and starting/cancelling a run. Every `POST`
  needs a per-launch token (embedded only in the served page), a same-origin
  `Origin`, and is size-limited. Scratch files use sanitized paths and caps.
- **Recording runs your Python code with your user's permissions. There is no
  sandbox.** A run starts only after the plan (command, working directory,
  arguments, interpreter) is shown and "Record execution" is clicked. Dropping
  a `.concurim` trace never executes anything.
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
