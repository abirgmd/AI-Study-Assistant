@echo off
chcp 65001 >nul
rem Lance le service IA sans fichier .env : le jeton est lu dans config\ia-service.php au moment du lancement
rem et passe seulement en variable d environnement au processus (rien n est ecrit sur le disque).
for /f "usebackq tokens=4 delims='" %%t in (`findstr /C:"'token' =>" "%~dp0config\ia-service.php"`) do set "AI_INTERNAL_TOKEN=%%t"
if not defined AI_INTERNAL_TOKEN echo ERREUR : jeton introuvable dans config\ia-service.php & pause & exit /b 1
set AI_EMBEDDING_BACKEND=hashing
set AI_LLM_BACKEND=ollama
set AI_OLLAMA_URL=http://127.0.0.1:11434
set AI_OLLAMA_MODEL=qwen2.5:3b
start "Service IA 8001" /D "%~dp0ai-service" "%~dp0ai-service\.venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
echo Service IA lance sur http://127.0.0.1:8001 (Ollama : qwen2.5:3b).
pause
