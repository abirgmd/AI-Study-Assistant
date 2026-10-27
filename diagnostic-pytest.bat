@echo off
chcp 65001 >nul
cd /d "%~dp0ai-service"
".venv\Scripts\python.exe" -m pytest -v --tb=short > "%~dp0resultats-pytest.txt" 2>&1
echo CODE RETOUR PYTEST %ERRORLEVEL% >> "%~dp0resultats-pytest.txt"
echo FIN >> "%~dp0resultats-pytest.txt"
