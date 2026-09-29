@echo off
rem PLANFGEN - studio web. Double-cliquer ce fichier, ou : python -m web
rem Le studio s'ouvre dans le navigateur sur http://127.0.0.1:8765/
cd /d "%~dp0.."
python -m web %*
if errorlevel 1 pause
