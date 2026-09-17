@echo off
setlocal
set "PLUGIN_ROOT=%~dp0.."
set "PYTHONDONTWRITEBYTECODE=1"
python "%PLUGIN_ROOT%\scripts\megin.py" %*
