@echo off
setlocal

cd /d "%~dp0"

set "PROJECT_PYTHON=.venv\Scripts\python.exe"

if not exist "%PROJECT_PYTHON%" (
    echo Creating local virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :failure
)

echo Installing pinned dependencies...
"%PROJECT_PYTHON%" -m pip install --requirement requirements-dev.txt
if errorlevel 1 goto :failure

echo Running automated tests...
set "TEST_TEMP=%CD%\.build-test-temp"
if exist "%TEST_TEMP%" rmdir /s /q "%TEST_TEMP%"
"%PROJECT_PYTHON%" -m pytest tests -q --basetemp="%TEST_TEMP%" -p no:cacheprovider
set "TEST_EXIT=%ERRORLEVEL%"
if exist "%TEST_TEMP%" rmdir /s /q "%TEST_TEMP%"
if not "%TEST_EXIT%"=="0" goto :failure

echo Building DocxVariableFiller.exe...
"%PROJECT_PYTHON%" -m PyInstaller --noconfirm --clean DocxVariableFiller.spec
if errorlevel 1 goto :failure

if not exist "dist\DocxVariableFiller.exe" (
    echo Build completed without producing the expected executable.
    goto :failure
)

echo.
echo Build completed successfully:
echo %CD%\dist\DocxVariableFiller.exe
exit /b 0

:failure
echo.
echo Build failed. Review the messages above.
exit /b 1
