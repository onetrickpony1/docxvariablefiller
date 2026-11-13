# Building and developing DOCX Variable Filler

## Supported environment

- Windows 10 or Windows 11
- Python 3.12 or 3.13
- Tkinter/Tcl/Tk included with the Python installation
- Microsoft Word is not required to generate a document

Development is currently tested with Python 3.13.3 and Tk 8.6. The packaged
Windows executable bundles its Python runtime and dependencies.

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
workstation. See [SECURITY.md](../SECURITY.md) for the required internal review,
build, malware scanning, signing, and deployment process.
