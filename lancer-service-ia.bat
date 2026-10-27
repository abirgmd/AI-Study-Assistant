@echo off
chcp 65001 >nul
set "LOG=%~dp0resultats-service-ia.txt"
echo === Lancement du service IA (Ollama) === > "%LOG%"
rem Le jeton est lu au lancement dans config\ia-service.php et passe en variable d environnement (aucun fichier cree).
for /f "usebackq tokens=4 delims='" %%t in (`findstr /C:"'token' =>" "%~dp0config\ia-service.php"`) do set "AI_INTERNAL_TOKEN=%%t"
if not defined AI_INTERNAL_TOKEN (echo ERREUR : jeton introuvable dans config\ia-service.php>> "%LOG%" & goto fin)
echo jeton lu depuis config\ia-service.php : OK >> "%LOG%"
set AI_EMBEDDING_BACKEND=hashing
set AI_LLM_BACKEND=ollama
set AI_OLLAMA_URL=http://127.0.0.1:11434
set AI_OLLAMA_MODEL=qwen2.5:3b
cd /d "%~dp0ai-service"
"%~dp0ai-service\.venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001 >> "%LOG%" 2>&1
:fin
echo FIN >> "%LOG%"
pause
