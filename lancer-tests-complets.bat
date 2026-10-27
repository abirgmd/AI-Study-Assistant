@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "LOG=%~dp0resultats-tests-complets.txt"
set "PY313=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "PYV=%~dp0ai-service\.venv\Scripts\python.exe"
set "PHP=C:\xampp\php\php.exe"
set "MYSQL=C:\xampp\mysql\bin\mysql.exe"
set "BASE=http://localhost/ai-study-assistant-integre/public/"

> "%LOG%" echo === TESTS COMPLETS AI Study Assistant ===
>> "%LOG%" echo.

>> "%LOG%" echo === 1. Python 3.13 ===
if not exist "%PY313%" goto erreur_python
>> "%LOG%" echo OK : %PY313%

>> "%LOG%" echo.
>> "%LOG%" echo === 2. Environnement du service IA : ai-service\.venv ===
if not exist "%PYV%" "%PY313%" -m venv "%~dp0ai-service\.venv" >> "%LOG%" 2>&1
"%PYV%" -m pip install -q -r "%~dp0ai-service\requirements-ci.txt" >> "%LOG%" 2>&1
>> "%LOG%" echo Dependances : code retour %ERRORLEVEL%

>> "%LOG%" echo.
>> "%LOG%" echo === 3. Services MySQL et Apache ===
netstat -ano | findstr ":3306" | findstr "LISTENING" >nul
if errorlevel 1 if exist C:\xampp\mysql_start.bat start "MySQL XAMPP" /MIN C:\xampp\mysql_start.bat
netstat -ano | findstr ":80 " | findstr "LISTENING" >nul
if errorlevel 1 if exist C:\xampp\apache_start.bat start "Apache XAMPP" /MIN C:\xampp\apache_start.bat
timeout /t 15 /nobreak >nul

>> "%LOG%" echo.
>> "%LOG%" echo === 4. Base de donnees : database\schema.sql (non destructif) ===
"%MYSQL%" -uroot --default-character-set=utf8mb4 < database\schema.sql >> "%LOG%" 2>&1
>> "%LOG%" echo Import : code retour %ERRORLEVEL%

>> "%LOG%" echo.
>> "%LOG%" echo === 5. Service IA sur 127.0.0.1:8001 (fenetre dediee) ===
if not exist "%~dp0ai-service\.env" goto sans_env
start "Service IA 8001" /D "%~dp0ai-service" "%PYV%" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
timeout /t 15 /nobreak >nul
goto etape6
:sans_env
>> "%LOG%" echo ATTENTION : ai-service\.env absent. Le service IA n'est pas demarre. Creez ce fichier puis relancez.
:etape6

>> "%LOG%" echo.
>> "%LOG%" echo === 6. lancer-tests-ia.bat : syntaxe, ia_modules, ruff, pytest ===
echo.| call "%~dp0lancer-tests-ia.bat" >nul 2>&1
type "%~dp0resultats-tests-ia.txt" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo === 7. Tests PHP (sans reseau) ===
>> "%LOG%" echo --- quiz_validation_test ---
"%PHP%" tests\quiz_validation_test.php >> "%LOG%" 2>&1
>> "%LOG%" echo --- study_test ---
"%PHP%" tests\study_test.php >> "%LOG%" 2>&1
>> "%LOG%" echo --- pdf_test ---
"%PHP%" tests\pdf_test.php >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo === 8. Tests HTTP de bout en bout (XAMPP + service IA demarres) ===
>> "%LOG%" echo --- smoke_ia ---
"%PYV%" tests\smoke_ia.py %BASE% >> "%LOG%" 2>&1
>> "%LOG%" echo Code retour : %ERRORLEVEL%
>> "%LOG%" echo --- smoke ---
"%PYV%" tests\smoke.py %BASE% >> "%LOG%" 2>&1
>> "%LOG%" echo Code retour : %ERRORLEVEL%
>> "%LOG%" echo --- smoke_corrections ---
"%PYV%" tests\smoke_corrections.py %BASE% >> "%LOG%" 2>&1
>> "%LOG%" echo Code retour : %ERRORLEVEL%

>> "%LOG%" echo.
>> "%LOG%" echo === 9. Module Evaluation (Gemini : cle dans config\gemini.php) ===
>> "%LOG%" echo --- ai-test (ping) ---
"%PHP%" feedback\tests\ai-test.php >> "%LOG%" 2>&1
>> "%LOG%" echo --- helper-test ---
"%PHP%" feedback\tests\helper-test.php >> "%LOG%" 2>&1
>> "%LOG%" echo --- pdf-test ---
"%PHP%" feedback\tests\pdf-test.php feedback\tests\quiz-reponses-1.pdf >> "%LOG%" 2>&1
>> "%LOG%" echo --- feedback-test ---
"%PHP%" feedback\tests\feedback-test.php >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo === FIN ===
goto fin

:erreur_python
>> "%LOG%" echo ERREUR : Python 3.13 introuvable : %PY313%
goto fin

:fin
type "%LOG%"
pause
