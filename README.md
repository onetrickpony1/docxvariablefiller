# DOCX Variable Filler

DOCX Variable Filler is a small offline Windows desktop application that fills
double-curly-brace variables in Microsoft Word `.docx` templates. It scans both
the document and its filename, asks for each value once, and saves a separate
completed document.

The application uses Python, `python-docx`, and the standard-library Tkinter
GUI. It has no server, cloud integration, analytics, telemetry, updater, or
network functionality.

## Supported environment

- Windows 10 or Windows 11
- Python 3.12 or 3.13
- Tkinter/Tcl/Tk included with the Python installation
- Microsoft Word is not required to generate a document

Development is currently tested with Python 3.13.3 and Tk 8.6. The packaged
Windows executable bundles its Python runtime and dependencies.

## Variable syntax

Variables use double curly braces:

```text
{{Employee Name}}
{{Start Date}}
{{Company}}
{{Job Title}}
{{Serial Number}}
```

Names must contain at least one non-whitespace character. Whitespace immediately
inside the braces is ignored for matching, so `{{ Name }}` and `{{Name}}` refer
to the same variable. Names are case-sensitive.

Replacement values are always treated as plain text. They are not interpreted
as Python, regular expressions, XML, HTML, or nested template expressions.

## Smart date variables

Recognised date variables are grouped into one **Smart Dates** input per
logical date. Group names are not hardcoded. For example, all of these belong
to the `Original` date:

```text
{{Ordinal Day in Words of Original}}
{{Day of Original in Digits}}
{{Month of Original}}
{{Year of Original in Words}}
{{Year of Original in Digits}}
```

`Original` can be replaced by any shared group name, such as `Commencement`,
`Bob`, or `Contract Signing`. The documented component grammar is:

```text
{{Ordinal Day [in Words|Digits] of Group [in Words|Digits]}}
{{Day [in Words|Digits] of Group [in Words|Digits]}}
{{Month [in Words|Digits] of Group [in Words|Digits]}}
{{Year [in Words|Digits] of Group [in Words|Digits]}}
```

The format may appear before or after `of`, but conflicting or repeated format
instructions are left as ordinary variables instead of being guessed.

Any other variable containing `Date` as exactly one complete word is treated as
a full date. Both `{{Start Date}}` and `{{Date of Start}}` therefore create a
single `Start date` input. Substrings such as `Update` are not dates, and
`{{Date}}` alone remains an ordinary variable because it has no group name.

Dates are entered in the explicitly day-first form `DD/MM/YYYY`. One-digit days
and months are accepted. A two-digit year is accepted and always means
2000–2099, so `5/10/25` is shown for confirmation as 5 October 2025. Invalid
calendar dates are rejected.

For 5 October 2025, generated values include:

| Placeholder component | Output |
| --- | --- |
| `Ordinal Day` or `Ordinal Day ... in Digits` | `5th` |
| `Ordinal Day ... in Words` | `fifth` |
| `Day ... in Words` | `five` |
| `Day ... in Digits` | `5` |
| `Month` or `Month ... in Words` | `October` |
| `Month ... in Digits` | `10` |
| `Year ... in Words` | `two thousand and twenty-five` |
| `Year ... in Digits` | `2025` |
| Full `Date` variable | `05/10/2025` |

The GUI shows how each entry was interpreted before generation. Smart-date
values are expanded into ordinary placeholder/value pairs, so the document
replacement engine remains generic. The resulting plain text inherits normal
placeholder formatting and supports review highlighting. A date used in a
filename is subject to normal Windows filename sanitization, so `/` becomes
`_`.

An `Ordinal Day` placeholder without a format, or with `in Digits`, uses a
numeric ordinal such as `1st`, `15th`, or `21st`. Adding `in Words` produces
`first`, `fifteenth`, or `twenty-first`. A non-ordinal
`Day ... in Digits` produces a plain number such as `5`, while a non-ordinal
`Day ... in Words` produces a cardinal word such as `five`.

## Supported document locations

The current version scans and replaces variables in:

- normal body paragraphs;
- tables and nested tables;
- default, first-page, and even-page headers;
- default, first-page, and even-page footers.

Shared headers and footers are processed only once. Merely scanning a document
does not create missing header or footer parts.

## Formatting preservation

When a variable is contained in one Word run, replacement changes only that
run's text and retains its run formatting.

Variables split across two or more runs are detected using combined paragraph
text. For an ordinary input field, the replacement takes the formatting of the
first non-whitespace character of the variable name inside `{{` and `}}`.
Variable characters are removed from the affected runs while text before and
after the variable remains in its original runs.

Supported run formatting retained by this approach includes bold, italic,
underline, strikethrough, font family, font size, font colour, superscript,
subscript, text highlighting, and character style. A placeholder containing
mixed formatting uses the run containing the first non-whitespace character
inside the braces for the inserted value.

## Review highlighting

The checkbox **Highlight changed text for review** is off by default.

When enabled, every inserted document value is isolated in a formatting-matched
run and highlighted with Word's yellow highlight colour. Surrounding text and
unrelated existing highlights are not changed. This feature does not use Track
Changes, comments, or revision metadata. Filename substitutions cannot be
highlighted.

When review highlighting is disabled, an ordinary replacement inherits any
highlight present on the variable name's formatting-source run.

When **Highlight changed text for review** and **Leave blank variables
unchanged** are both enabled, every retained blank placeholder remains visible
as `{{Variable Name}}` and is highlighted yellow. Only the placeholder
characters are highlighted; surrounding text is unchanged. Retained blank
placeholders are not counted as document replacements.

## Optional rich text editor

Every variable row includes a **Rich text editor** checkbox. It is unchecked by
default. Enabling it expands that variable into a larger, scrollable editor
with controls for:

- bold;
- italic;
- underline;
- bullet lists;
- numbered lists.

Select text before applying bold, italic, or underline. The usual `Ctrl+B`,
`Ctrl+I`, and `Ctrl+U` shortcuts are also supported. Bullet and numbering
buttons operate on the selected lines, or on the current line when there is no
selection. Pressing Enter at the end of a list item continues the list.

Character formatting can replace a variable embedded within surrounding text.
Multiple paragraphs, bullet lists, and numbered lists require the variable to
be the only visible content in its Word paragraph. Generation stops with a
clear error if block content would otherwise alter surrounding text.

Bullet and numbering definitions are created directly in the generated DOCX.
They work with any variable name, including `{{variable}}`, and do not require
the template to contain Word styles named `List Bullet` or `List Number`.

Rich-editor content inherits the effective font family and font size of the
original placeholder text. This includes direct run formatting and formatting
provided by a Word character style. Bold, italic, and underline remain
controlled by the rich editor. Other character attributes use the destination
paragraph's normal formatting. Review mode still highlights only inserted text
in yellow.

If a rich value also appears in the output filename, formatting is omitted and
its paragraphs are joined with ` - ` before normal Windows filename
sanitization.

## Filename replacement

Variables in the original filename stem are combined with document variables.
For example:

```text
Employment Agreement - {{Employee Name}}.docx
```

can become:

```text
Employment Agreement - John Smith.docx
```

The `.docx` extension is preserved. Characters invalid in Windows filenames are
replaced with underscores:

```text
< > : " / \ | ? *
```

Control characters are also replaced. Trailing spaces and full stops are
removed. Reserved Windows device names such as `CON`, `PRN`, `AUX`, `NUL`,
`COM1`, and `LPT1` are prevented.

The GUI continuously displays the proposed filename. If a replacement value is
sanitized, the final proposed filename is explicitly confirmed before the Save
As dialog.

### Filename template notes

Complete double-tilde regions in the template filename act as removable notes:

```text
Offer ~~Check approvals before generating~~ - {{Employee Name}}.docx
```

becomes:

```text
Offer  - Jane Smith.docx
```

The note text and both `~~` markers are removed from the proposed and generated
filename. Multiple notes are supported. Variables inside filename notes are
ignored and do not appear in the form. Notes apply only to the template
filename, not document content or replacement values.

An unmatched `~~` marker is retained unchanged because deleting the remainder
of an ambiguous filename would be unsafe. Note removal is exact, so surrounding
spaces or separators remain under the template author's control. The filename
preview reports the number of notes that will be removed.

## Installation for development

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Installing dependencies may access the Python package index. The application
itself never accesses the network.

## Running from source

```powershell
.\.venv\Scripts\python.exe -m src.main
```

If Tkinter cannot create a window, modify or reinstall Python and include its
Tcl/Tk component.

## Usage

1. Select **Select Word Template** and choose a `.docx` file.
2. Enter one value for each detected variable. Related smart-date variables
   share one day-first date entry.
3. Optionally enable **Highlight changed text for review**.
4. Review the proposed output filename.
5. Select **Generate Document**.
6. Complete any blank values, or explicitly select **Leave blank variables
   unchanged**.
7. Choose the output path in the Save As dialog.
8. Confirm overwrite if an output file already exists.
9. Review the in-application completion summary.

The original template is never overwritten. The output must be a different
`.docx` path explicitly selected by the user.

## Remembered preferences

The application remembers:

- the path of the last selected template;
- **Highlight changed text for review**;
- **Leave blank variables unchanged**;
- which variable rows had the **Rich text editor** enabled for the remembered
  template.

On the next launch, it rescans the remembered template if that file is still
available. Rich-editor state is stored only as validated variable positions,
not placeholder names. Input fields always start empty: document contents,
rich formatting, and replacement values are never stored in preferences.

Preferences are saved as a small per-user JSON file:

```text
%APPDATA%\DocumentTemplateFiller\settings.json
```

Company Profiles and preferences therefore share one application directory:

```text
%APPDATA%\DocumentTemplateFiller\
```

On the first launch after upgrading, a valid legacy settings file from
`%LOCALAPPDATA%\DocxVariableFiller\settings.json` is migrated to the unified
directory using an atomic write. The legacy file is removed only after the new
file is safely created. No registry entry is used. Selecting **Clear** forgets
the template and resets the saved checkbox states.

## Managing Company Profiles

Select **Manage Companies** to open the persistent company list. The window
supports:

- adding a validated company;
- editing the selected company;
- deleting the selected company after confirmation;
- importing Company Profiles from a selected JSON export;
- exporting Company Profiles to a selected JSON file.

Company display names are unique without regard to letter case. Only Company
Directors 2–3 are optional; all other fields, including Company Address Line 2
and Company Director 1, are required. Registration numbers use `C 12345`
format: uppercase `C`, one space, and five to eight digits.

Profiles are stored as versioned UTF-8 JSON:

```text
%APPDATA%\DocumentTemplateFiller\companies.json
```

Configuration is parsed strictly and is never evaluated. If it is malformed,
oversized, invalid UTF-8, or otherwise unsafe, no profiles are partially loaded
and all mutation controls are disabled. **Recover Corrupted File** requires
confirmation, moves the original to a uniquely named recovery copy in the same
application directory, and creates a new empty configuration.

The current configuration schema is version 2. Version 1 profiles are migrated
in memory by retaining their existing director as Company Director 1 and
initializing Directors 2–3 as empty. The next profile save writes version 2
atomically.

Import is a validated merge operation. Existing profiles are retained and
imported profiles are appended only after confirmation. A duplicate display
name, invalid field, unsupported schema, oversized file, or unsafe file rejects
the complete import; no existing profile is changed. Import never silently
overwrites a saved company.

Export uses the same versioned UTF-8 JSON format and atomic writer as the active
configuration. The user explicitly chooses the destination. The active
`companies.json` file cannot be selected as an export destination. Export files
contain company information and should be protected using the organization's
approved storage and transfer controls.

When a selected template contains a supported company placeholder, a
**Company** dropdown appears at the top of the variable form. Selecting a saved
profile populates only the matching company fields. The populated entries remain
ordinary editable inputs so the user can review or adjust them before
generation. These one-document edits do not alter the saved profile.

The supported automatic mappings are:

```text
{{Company Name}}
{{Company Registration Number}}
{{Company Address Line 1}}
{{Company Address Line 2}}
{{Company Postcode}}
{{Company Country}}
{{Company Director 1}}
{{Company Director 2}}
{{Company Director 3}}
```

For compatibility with existing templates, `{{Company Director}}` continues to
populate from Company Director 1.

The selector remains hidden for templates without company placeholders. If the
profile configuration is invalid, the selector is disabled and directs the user
to **Manage Companies** for explicit recovery.

## Tests

All test documents are generated programmatically:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers parsing, filename safety, supported document locations,
split-run replacement, formatting, review highlighting, output protection, and
temporary-file cleanup. It also covers Company Profile validation, strict
configuration parsing, atomic-write failure, CRUD persistence, placeholder
mapping, generic replacement-engine integration, and rich-text document
replacement.

## Executable build

Run the build from a normal PowerShell or Command Prompt:

```powershell
.\build.bat
```

The script:

1. creates `.venv` if it does not exist;
2. installs the pinned production and development dependencies;
3. runs the complete test suite using a disposable project-local test
   directory;
4. performs a clean PyInstaller build.

The output is:

```text
dist\DocxVariableFiller.exe
```

The specification creates a single Windows executable named
`DocxVariableFiller.exe`. It has no console window, requests no elevation, and
uses no UPX compression. The executable is deliberately not digitally signed;
signing belongs to the company's controlled release process.

IT can perform a non-interactive startup check after building:

```powershell
$process = Start-Process `
    -FilePath ".\dist\DocxVariableFiller.exe" `
    -ArgumentList "--smoke-test" `
    -Wait `
    -PassThru
$process.ExitCode
```

An exit code of `0` confirms that the packaged Python, Tcl/Tk runtime, and full
application interface initialized. Smoke-test mode opens no files and displays
no window.

The company should not distribute an executable built on an unreviewed
workstation. See [SECURITY.md](SECURITY.md) for the required internal review,
build, malware scanning, signing, and deployment process.

## License

This project is free software licensed under the
[GNU General Public License version 3](LICENSE) (`GPL-3.0-only`). It may be
used, studied, modified, and redistributed subject to the GPLv3 terms. The
licence does not replace the company's source review, controlled build,
malware scanning, signing, or deployment requirements.

## Known limitations

The following locations and structures are not supported:

- text boxes and shapes;
- SmartArt;
- embedded documents;
- comments;
- footnotes and endnotes;
- tracked changes;
- Word fields;
- content controls;
- unsupported or custom XML structures;
- variables crossing paragraph or table-cell boundaries.
- block rich text used where a placeholder shares its paragraph with other
  visible text.
- smart-date output uses English month and number wording;
- smart-date recognition follows the documented naming grammar and does not
  infer relationships from document proximity or unrestricted fuzzy matching.

Placeholders inside hyperlinks are not currently processed. Unsupported content
is otherwise left unchanged. The application does not attempt to repair damaged
documents or accept legacy `.doc` files.

## Security characteristics

- operates offline;
- makes no network requests;
- contains no telemetry, analytics, or automatic updates;
- runs without administrator rights;
- creates no services, background processes, or registry entries;
- reads the template selected by the user and may reopen its remembered path on
  a later launch;
- writes only to the output location selected by the user;
- retains replacement values only in application memory and the generated
  document;
- stores validated Company Profiles in the application-owned roaming-data
  directory using versioned JSON and atomic replacement;
- stores only the last template path, global checkbox states, and rich-editor
  variable positions in per-user preferences;
- creates no permanent log files;
- uses a short-lived same-folder temporary file for atomic output saving and
  removes it after success or failure;
- when packaged as one file, uses PyInstaller's per-user temporary extraction
  directory for bundled program/runtime files and removes it on normal exit.

See [SECURITY.md](SECURITY.md) for the complete security and dependency review.
