@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE="
for %%P in (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do if exist %%P set "PYTHON_EXE=%%~P"
if not defined PYTHON_EXE (
  where python >nul 2>nul && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  echo Python 3.10+ not found. Install Python or set PYTHON_EXE.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -m engine
echo.
if exist "%~dp0data\report.html" start "" "%~dp0data\report.html"
endlocal
