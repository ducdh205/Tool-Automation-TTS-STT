@echo off
rem TTS-STT Tool (portable). Close this window to stop the tool (wyoming stops with it).
title TTS-STT Tool
cd /d "%~dp0"
"%~dp0runtime\py312\python.exe" "%~dp0launch.py" %*
if errorlevel 1 (
  echo.
  echo Tool gap loi khi khoi dong ^(chi tiet o tren^).
  pause
)
