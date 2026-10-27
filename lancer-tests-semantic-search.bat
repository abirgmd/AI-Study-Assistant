@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
set "PY=%ROOT%modules\semantic_search\.venv\Scripts\python.exe"
set "PHP=C:\xampp\php\php.exe"
if not exist "%PY%" (
  echo Environnement Python absent. Lancez d'abord lancer-recherche-semantique.bat.
  pause
  exit /b 1
)
if not exist "%PHP%" (
  where php >nul 2>nul
  if errorlevel 1 (
    echo PHP introuvable. Installez XAMPP ou ajoutez php au PATH.
    pause
    exit /b 1
  )
  set "PHP=php"
)
set "OUT=%ROOT%resultats-tests-semantic-search.txt"
echo === Tests Python (module 2) === > "%OUT%"
set "PYTHONPATH=%ROOT%modules\semantic_search"
"%PY%" -m pytest "%ROOT%modules\semantic_search\tests" -q >> "%OUT%" 2>&1
set "PYTEST=%ERRORLEVEL%"
echo. >> "%OUT%"
echo === Tests PHP (integration) === >> "%OUT%"
"%PHP%" "%ROOT%tests\semantic_search_test.php" >> "%OUT%" 2>&1
set "PHPTEST=%ERRORLEVEL%"
echo. >> "%OUT%"
echo === Smoke test du service === >> "%OUT%"
"%PY%" "%ROOT%tests\smoke_semantic_search.py" >> "%OUT%" 2>&1
set "SMOKE=%ERRORLEVEL%"
echo. >> "%OUT%"
if "%PYTEST%"=="0" if "%PHPTEST%"=="0" if "%SMOKE%"=="0" (
  echo TOUS LES TESTS SONT PASSES. >> "%OUT%"
) else (
  echo ECHEC : Python=%PYTEST% PHP=%PHPTEST% Smoke=%SMOKE% >> "%OUT%"
)
type "%OUT%"
pause
if not "%PYTEST%"=="0" exit /b 1
if not "%PHPTEST%"=="0" exit /b 1
if not "%SMOKE%"=="0" exit /b 1
exit /b 0
