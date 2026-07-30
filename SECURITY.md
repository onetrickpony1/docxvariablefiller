# Security and Internal Deployment

## Security model

DOCX Variable Filler is designed for a locked-down corporate Windows computer.
It is a local desktop utility, not a connected service.

The application:

- performs no network requests;
- has no analytics or telemetry;
- has no automatic update mechanism;
- does not execute external commands, scripts, macros, or document content;
- does not create background processes or services;
- does not modify the Windows registry;
- does not require administrator privileges;
- does not permanently log document content or replacement values;
- stores the last selected template path, two global checkbox preferences, and
  rich-editor-enabled variable positions;
- stores user-managed Company Profiles in its fixed per-user configuration
  directory.

Installing or updating Python packages is a separate development/build activity
and can use the network. The built application itself contains no network
feature.

## File access

At runtime the application reads the `.docx` template explicitly chosen in the
Open dialog and, when requested, a Company Profiles JSON import explicitly
selected by the user. It writes the completed `.docx` and Company Profiles JSON
exports only to paths explicitly selected in Save As dialogs.

After the user has selected a template, its path is remembered and that same
file may be rescanned automatically on a later launch. Selecting **Clear**
removes the remembered path.

Company Profiles are stored only in the application's own per-user directory:

```text
%APPDATA%\DocumentTemplateFiller\companies.json
```

The path is fixed by the application and is never taken from configuration
content. The JSON file has a strict schema, version, size limit, profile-count
limit, field-length limits, type checks, duplicate-key rejection, and
case-insensitive display-name uniqueness. Configuration values are never
executed or evaluated.

Company Profile schema version 2 supports one required and two optional
directors. A narrowly defined version 1 migration maps the legacy director
field to Director 1 and supplies empty Directors 2–3. Legacy data still passes
the complete current validation model before use and is never evaluated.

The GUI converts a selected validated profile into ordinary placeholder/value
pairs before generation. The DOCX replacement engine has no dependency on the
Company Profile model or storage layer. Only company placeholders actually
present in the selected template receive values, and the user can review or edit
those values before saving a document.

Company Profile imports use the same strict version, schema, size, field, and
collection validation as the active configuration. Import merges only after
confirmation, rejects all duplicate display names, and never partially imports
or silently overwrites an existing profile. Exports use atomic same-directory
writes and cannot target the active configuration file.

The original template path is protected and cannot be used as the output path.
An existing output requires explicit confirmation before replacement.

To prevent a failed write from damaging an existing output, saving uses one
short-lived temporary file in the selected output directory. The temporary file
is replaced atomically into the chosen output path after the DOCX package is
fully written. Cleanup is attempted after both success and failure. The
application does not use a shared system temporary directory for document
content.

The single-file PyInstaller executable necessarily extracts bundled application
code, Python, Tcl/Tk, and dependency files into a per-user `_MEI...` directory
under the operating-system temporary directory while it runs. Document content
and replacement values are not intentionally written to that extraction
directory. PyInstaller removes the directory on normal exit. An abnormal process
termination or operating-system failure can leave an extraction directory for
the company's normal endpoint-cleanup policy to remove.

No other user documents are scanned. The application does not enumerate nearby
folders, follow links in document content, or open the generated file
automatically.

## Information retention

Template text and replacement values exist only:

- in memory while the application is running;
- in the generated document selected by the user;
- in a short-lived output-directory temporary file during saving.

Smart-date entries follow the same rule. They are parsed locally with the
Python standard library, expanded into plain-text replacement pairs in memory,
and are never written to preferences or a separate date store. Placeholder
recognition uses a fixed naming grammar rather than evaluating configuration,
document text, or user input.

The application creates one per-user preference file:

```text
%APPDATA%\DocumentTemplateFiller\settings.json
```

It contains only the last selected template path, the review-highlighting
checkbox state, the leave-blanks-unchanged checkbox state, and integer positions
of rich-editor-enabled variables for the remembered template. Placeholder
names, rich formatting, template text, and replacement values are not stored.
Preferences are written atomically through a short-lived file in the same
settings directory.

Both `settings.json` and `companies.json` are stored in
`%APPDATA%\DocumentTemplateFiller\`. On upgrade, a valid legacy settings file
from `%LOCALAPPDATA%\DocxVariableFiller\settings.json` is migrated by first
writing the validated settings atomically to the unified directory. The legacy
file is deleted only after that write succeeds. Invalid legacy data is neither
migrated nor used.

The application creates no database, recent-file list, analytics record, crash
report, or permanent log. Selecting **Clear** releases the application's
references to the selected path, detected variables, entered values, and
session error detail, then writes default preferences. Closing the process
releases all remaining in-memory document data.

Company Profile recovery is explicit. When corruption is detected, no profile
is accepted and mutation controls are disabled. If the user confirms recovery,
the original file is renamed to a unique `companies.corrupt-...json` recovery
copy before a new empty configuration is written. Recovery copies can contain
company information and are retained for deliberate administrator recovery;
the application does not silently delete them.

User-created Company Profile export files contain company information and
remain at the explicitly selected destination until the user or the
organization's retention process removes them. They are not application logs
and are never transmitted by the application.

The completion summary contains filenames, the selected output directory,
counts, review-mode status, and sanitized character names. It does not contain
replacement values.

Windows, endpoint-security software, backup software, or Microsoft Word may
independently retain operating-system metadata; those products are outside this
application's control.

## Operating-system impact and privileges

The application:

- runs in the current user's security context;
- requires no elevation;
- installs no driver, service, scheduled task, startup item, shell extension, or
  browser component;
- changes no registry keys;
- creates no background worker process;
- has no self-update function.

The source version requires a normal per-user Python environment. The packaged
version will be a user-mode executable.

## Dependencies

Direct dependencies are pinned in the repository.

| Dependency | Scope | Purpose |
| --- | --- | --- |
| `python-docx==1.2.0` | Runtime | Reads, modifies, and writes Open XML `.docx` packages. |
| `pytest==8.4.1` | Development only | Runs the automated test suite. It is not needed by the application at runtime. |
| `pyinstaller==6.21.0` | Development only | Bundles the reviewed Python application into the internal Windows executable. |

Tkinter, `pathlib`, `tempfile`, `zipfile`, `dataclasses`, `datetime`,
`calendar`, `re`, and other standard-library modules ship with Python.

`python-docx` installs necessary transitive packages:

- `lxml` parses and serializes the XML inside DOCX packages;
- `typing_extensions` supplies compatibility typing definitions.

`pytest` installs development-only transitive packages such as `pluggy`,
`packaging`, `iniconfig`, `colorama`, and `Pygments`.

PyInstaller and its transitive build packages, such as
`pyinstaller-hooks-contrib`, `pefile`, and `altgraph`, are not application
network features. They run only in the controlled build environment.

Before an internal build, the security team should:

1. verify package names and versions against the requirements files;
2. acquire packages through the company's approved repository or mirror;
3. scan downloaded wheels and source distributions;
4. review transitive versions and licenses;
5. produce and retain an internal dependency inventory or software bill of
   materials;
6. rebuild in a clean, controlled environment.

Locking and hashing transitive artifacts in the internal package repository is
recommended even though the repository pins only direct dependencies.

## DOCX security considerations

A `.docx` file is a ZIP-based package containing XML and related assets. The
application treats placeholder values as text and never evaluates document
content. It does not launch Microsoft Word, follow hyperlinks, run macros, or
execute embedded objects.

Parsing untrusted files still exercises Python, `zipfile`, `python-docx`, and
`lxml`. Corporate controls should therefore restrict template sources and keep
the approved runtime dependencies patched through a reviewed release process.
Macro-enabled `.docm` and legacy `.doc` files are rejected.

Unsupported structures are not intentionally modified. Text boxes, shapes,
SmartArt, comments, footnotes, endnotes, tracked changes, fields, content
controls, embedded documents, and custom unsupported XML are outside the
supported processing surface.

## Error handling

Normal users receive concise errors for missing or inaccessible files, invalid
or corrupted DOCX packages, invalid filenames, protected originals, existing
outputs, and failed saves. Raw tracebacks and underlying system details are not
shown in the GUI.

Technical exceptions are retained only in application memory for the current
session. They are not written to disk or transmitted.

Saving is performed through a same-directory temporary package. If document
serialization or final replacement fails, the application attempts to delete
that temporary file and leaves an existing destination unchanged.

## Required internal release process

For every release, including minor source or dependency changes, the company's
IT/security team should:

1. review all source-code changes;
2. review dependency changes and scan all dependency artifacts;
3. run the complete automated test suite in a clean environment;
4. build the executable internally from the reviewed commit;
5. malware-scan the resulting executable;
6. inspect the PyInstaller contents and confirm UPX is disabled;
7. digitally sign the approved executable using the company's signing process;
8. test the signed executable on a representative locked-down workstation;
9. distribute it only through the approved software-deployment process;
10. retain the reviewed source commit, dependency inventory, build record, scan
    result, and signing record.

Every new release must be separately reviewed, built, scanned, and signed.
Approval of one version does not approve later versions.

The project does not attempt to sign executables itself and does not contain
signing keys or credentials.

## Reporting security issues

Report suspected vulnerabilities through the company's internal security
reporting process. Do not attach sensitive templates or replacement values
unless the approved incident-handling procedure explicitly requires them.
