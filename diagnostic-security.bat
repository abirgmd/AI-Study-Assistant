@echo off
chcp 65001 >nul
cd /d "%~dp0ai-service"
".venv\Scripts\python.exe" -m pytest tests\test_security.py -v --tb=long -o faulthandler_timeout=45 > "%~dp0resultats-security.txt" 2>&1
echo CODE RETOUR %ERRORLEVEL% >> "%~dp0resultats-security.txt"
echo FIN >> "%~dp0resultats-security.txt"
