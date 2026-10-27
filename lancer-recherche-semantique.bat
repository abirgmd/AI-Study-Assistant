@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0modules\semantic_search"
if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement Python du module 2...
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
if "%SEMANTIC_SEARCH_TOKEN%"=="" set "SEMANTIC_SEARCH_TOKEN=demo-semantic-search-token"
if "%SEMANTIC_SEARCH_EMBEDDER%"=="" set "SEMANTIC_SEARCH_EMBEDDER=sentence-transformers"
echo.
echo Service de recherche semantique : http://127.0.0.1:8002
echo Jeton : %SEMANTIC_SEARCH_TOKEN%
echo Laissez cette fenetre ouverte pendant la demo.
echo.
".venv\Scripts\python.exe" service.py --host 127.0.0.1 --port 8002 --token "%SEMANTIC_SEARCH_TOKEN%" --embedder "%SEMANTIC_SEARCH_EMBEDDER%"
if errorlevel 1 goto :error
goto :eof
:error
echo.
echo Echec du service. Verifiez Python, les dependances et la connexion Internet (premier telechargement du modele).
pause
exit /b 1
