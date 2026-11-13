# DOCX Variable Filler: notes for AI assistants

Project-specific rules for working on this repo. It is built for locked-down corporate Windows PCs, so it is
Windows-only by design. [SECURITY.md](SECURITY.md) is part of the product: keep it accurate whenever behaviour changes.

## Rules

- No network access of any kind, and no telemetry, analytics, updaters, background processes, registry changes or
  administrator rights.
- Never execute or evaluate anything from a document, a value or a configuration file. Values are inserted as plain
  text.
- Never log document content or replacement values.
- The template is never overwritten. Output goes only to a path the user picked, through one temporary file in that
  folder, replaced atomically.
- Company Profiles live at the fixed path `%APPDATA%\DocumentTemplateFiller\companies.json`, with a strict, versioned
  schema. A schema change needs a narrow, tested migration from every older version. Imports never partially apply.
- Dependencies are pinned (`requirements.txt`, `requirements-dev.txt`). Change pins deliberately, and update
  SECURITY.md's dependency review when you do.

## Code

`src/main.py` starts the app (`--smoke-test` builds the whole window and exits). `src/gui.py` is the Tkinter
interface. `src/document_processor.py` is the replacement engine, and it must not depend on the Company Profile code.
`company_*.py` hold the profiles: the model, storage, operations, placeholder mapping and manager window.

## Tests

`python -m pytest tests -q`. Every test document is generated in code. Never add real templates or company data. The
tests also run on Linux and macOS in CI, even though the app itself is Windows-only.
