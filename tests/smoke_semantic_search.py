"""Smoke test HTTP du service de recherche sémantique (module 2).

Lance service.py avec l'embedder de test (aucun modèle à télécharger), vérifie
/health, l'authentification et un classement réel, puis arrête le service.
Aucune base de données ni serveur PHP n'est nécessaire.

Usage : python tests/smoke_semantic_search.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "semantic_search"
TOKEN = "smoke-test-token"

NOTES = [
    {
        "id": "n1",
        "title": "Régularisation",
        "text": (
            "Le sur-apprentissage fait apprendre le bruit du jeu d'entraînement. "
            "La régularisation L2 pénalise les grands poids et améliore la généralisation."
        ),
    },
    {
        "id": "n2",
        "title": "Bases de données",
        "text": (
            "Une base de données relationnelle organise les données en tables, "
            "avec des clés primaires et des clés étrangères."
        ),
    },
]


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS: {label}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    url: str,
    payload: dict | None = None,
    token: str | None = None,
    timeout: float = 30,
) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        method = "POST"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.load(response)


def wait_health(base: str, process: subprocess.Popen[str]) -> dict:
    deadline = time.time() + 20
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Le service s'est arrêté avant de répondre.")
        try:
            status, data = request_json(f"{base}/health", timeout=1)
            if status == 200:
                return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.3)
    raise RuntimeError("Le service n'a pas répondu dans le délai imparti.")


def main() -> int:
    if not (MODULE / "service.py").is_file():
        print("FAIL: modules/semantic_search/service.py introuvable.", file=sys.stderr)
        return 1
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        str(MODULE / "service.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--token",
        TOKEN,
        "--embedder",
        "hashing",
    ]
    process = subprocess.Popen(
        command,
        cwd=MODULE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        health = wait_health(base, process)
        check(health.get("status") == "ok", "Health : service disponible")
        check(health.get("embedder") == "hashing", "Health : embedder de test chargé")

        try:
            request_json(
                f"{base}/search",
                {"query": "régularisation", "notes": NOTES, "top_k": 1},
                timeout=10,
            )
            raise AssertionError("Le service a accepté une requête sans jeton.")
        except urllib.error.HTTPError as error:
            check(error.code == 401, "Authentification : requête sans jeton refusée (401)")

        status, data = request_json(
            f"{base}/search",
            {"query": "comment limiter le sur-apprentissage ?", "notes": NOTES, "top_k": 1},
            token=TOKEN,
        )
        check(status == 200, "Recherche : réponse HTTP 200")
        check(len(data.get("results", [])) == 1, "Recherche : un passage demandé, un passage renvoyé")
        check(data["results"][0]["note_id"] == "n1", "Recherche : cours sur la régularisation classé premier")
        check(data.get("backend") in {"faiss", "numpy"}, "Recherche : index FAISS ou numpy utilisé")
        check(int(data.get("passages", 0)) >= 1, "Recherche : passages indexés")

        status, data = request_json(
            f"{base}/search",
            {"query": "base de données relationnelle", "notes": NOTES, "top_k": 1},
            token=TOKEN,
        )
        check(
            status == 200 and data["results"][0]["note_id"] == "n2",
            "Recherche : cours sur les bases de données classé premier",
        )

        try:
            request_json(
                f"{base}/search",
                {"query": "a", "notes": NOTES, "top_k": 1},
                token=TOKEN,
            )
            raise AssertionError("Le service a accepté une question trop courte.")
        except urllib.error.HTTPError as error:
            check(error.code == 422, "Validation : question trop courte refusée (422)")

        print("Tous les tests smoke de la recherche sémantique sont passés.")
        return 0
    except Exception as error:  # pragma: no cover - affichage de diagnostic
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        out, err = process.communicate()
        if err.strip():
            print("--- journal du service ---", file=sys.stderr)
            print(err.strip(), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
