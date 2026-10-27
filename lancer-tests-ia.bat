@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PHP=C:\xampp\php\php.exe
if exist "%~dp0ai-service\.venv\Scripts\python.exe" (set PY="%~dp0ai-service\.venv\Scripts\python.exe") else (set PY=python)
echo === Syntaxe PHP des fichiers du module Assistant IA 2 === > resultats-tests-ia.txt
for %%f in (public\ia-api.php public\api.php ia-modules\service.php ia-modules\courses.php ia-modules\rag.php) do %PHP% -l %%f >> resultats-tests-ia.txt 2>&1
echo. >> resultats-tests-ia.txt
echo === Syntaxe JavaScript === >> resultats-tests-ia.txt
node --check public\assets\ia-modules.js >> resultats-tests-ia.txt 2>&1
echo. >> resultats-tests-ia.txt
echo === tests/ia_modules_test.php === >> resultats-tests-ia.txt
%PHP% tests\ia_modules_test.php >> resultats-tests-ia.txt 2>&1
echo. >> resultats-tests-ia.txt
echo === ai-service : pytest et ruff === >> resultats-tests-ia.txt
pushd ai-service
%PY% -m ruff check . >> ..\resultats-tests-ia.txt 2>&1
%PY% -m pytest >> ..\resultats-tests-ia.txt 2>&1
popd
echo. >> resultats-tests-ia.txt
echo Test de bout en bout (service IA et serveur demarres) : >> resultats-tests-ia.txt
echo   %PY% tests\smoke_ia.py http://localhost/ai-study-assistant-integre/public/ >> resultats-tests-ia.txt
echo FIN >> resultats-tests-ia.txt
type resultats-tests-ia.txt
pause
