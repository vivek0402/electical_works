@echo off
rem Double-click to start the SVKML demo: opens a small window, starts everything and opens the browser.
cd /d "%~dp0"
where uv >nul 2>nul || (echo uv is not installed. See https://docs.astral.sh/uv/ & pause & exit /b 1)
start "" uv run pythonw scripts\launcher.py
