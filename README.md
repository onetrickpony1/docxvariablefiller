# DOCX Variable Filler

A small offline Windows desktop app that fills double-curly-brace variables in Microsoft Word `.docx` templates. It
scans the document and its filename, asks for each value once, and saves a separate completed document. It uses Python,
`python-docx` and Tkinter, and has no network features at all.

```text
Template:  Employment Agreement - {{Employee Name}}.docx
Contains:  This agreement is made with {{Employee Name}}, starting on {{Start Date}} ...
Saved as:  Employment Agreement - Jane Borg.docx
```

## Features

- **Variables everywhere they matter:** body text, tables (nested too), headers, footers and the filename.
- **Formatting kept.** A value takes the formatting of the variable it replaces, even when Word has split it across
  several runs.
- **Smart dates.** Related date variables (day in words, month, year and so on) share one date entry.
- **Review highlighting** (optional): every inserted value is highlighted yellow so it can be checked.
- **Rich text editor** (optional) for variables that need bold, italic or lists.
- **Company Profiles**: save a company's details once and fill its placeholders from a list.
- **Safe saving.** The template is never overwritten, and an existing output is replaced only after you confirm.
- **Offline and unprivileged.** No network, telemetry or updates, and no administrator rights needed.

## Install

Runs on Windows 10 or 11. Microsoft Word is not needed to generate documents.

Build the single-file `DocxVariableFiller.exe` with `build.bat`, or run it from source with Python 3.12 or 3.13. Both
are described in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). The build is deliberately unsigned: signing and deployment
belong to your organisation's release process (see [SECURITY.md](SECURITY.md)).

## Use

1. Select **Select Word Template** and choose a `.docx` file.
2. Enter a value for each variable, and check the proposed output filename.
3. Select **Generate Document** and choose where to save it.

The full guide, covering variable syntax, smart dates, rich text, Company Profiles and known limitations, is in
[docs/USAGE.md](docs/USAGE.md).

## Notes

- Text boxes, shapes, comments, footnotes, tracked changes, fields, content controls and hyperlinks are not processed.
  See "Known limitations" in [docs/USAGE.md](docs/USAGE.md).
- [SECURITY.md](SECURITY.md) describes the security model, file access and the internal review, build and deployment
  process.

## License

GNU General Public License v3.0 or later (GPL-3.0-or-later). See [LICENSE](LICENSE). The licence does not replace your
organisation's source review, controlled build, malware scanning, signing or deployment requirements.
