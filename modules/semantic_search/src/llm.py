"""Génération RAG optionnelle avec Ollama.

La recherche sémantique reste le cœur du module. Ollama ajoute une couche de
génération ancrée exclusivement sur les passages retrouvés. Aucun appel à une API
cloud et aucune clé ne sont nécessaires.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.module import SearchResult


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
MAX_CONTEXT_CHARS = 6000

SYSTEM_PROMPT = (
    "Tu es un assistant de révision pour des notes de cours. "
    "Réponds en français, uniquement à partir des extraits fournis. "
    "Si les extraits ne suffisent pas, dis-le clairement. "
    "N'invente aucune information et cite les extraits avec [1], [2], etc."
)


class OllamaError(RuntimeError):
    """Erreur de communication ou de réponse avec Ollama."""


def build_context(
    results: Sequence[SearchResult],
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Formate les passages retrouvés en sources numérotées."""
    if not results:
        raise ValueError("Aucun passage à fournir au modèle.")
    if max_chars < 100:
        raise ValueError("max_chars doit être supérieur ou égal à 100.")

    sources: list[str] = []
    used = 0
    for index, result in enumerate(results, start=1):
        block = f"[{index}] {result.title}\n{result.passage.strip()}"
        if sources and used + len(block) > max_chars:
            break
        sources.append(block)
        used += len(block) + 2

    return "\n\n".join(sources)


def build_messages(
    query: str,
    results: Sequence[SearchResult],
    *,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> list[dict[str, str]]:
    """Construit les messages envoyés à Ollama."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("La question ne peut pas être vide.")
    if not results:
        raise ValueError("Aucun passage retrouvé : impossible de générer une réponse.")

    context = build_context(results, max_chars=max_context_chars)
    user_prompt = (
        f"Question :\n{query.strip()}\n\n"
        f"Extraits de cours :\n{context}\n\n"
        "Réponds de façon concise. Appuie chaque affirmation utile sur un extrait "
        "et termine par une ligne « Sources : [1], [2] ». "
        "Si les extraits ne permettent pas de répondre, écris-le explicitement."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise OllamaError(
            f"Ollama a refusé la requête (HTTP {exc.code}) : {detail}"
        ) from exc
    except URLError as exc:
        raise OllamaError(
            "Ollama est injoignable. Vérifiez que `ollama serve` tourne et que "
            "l'adresse du serveur est correcte."
        ) from exc
    except TimeoutError as exc:
        raise OllamaError("Ollama n'a pas répondu dans le délai imparti.") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaError("Ollama a renvoyé une réponse non JSON.") from exc
    if not isinstance(data, dict):
        raise OllamaError("Ollama a renvoyé une réponse invalide.")
    return data


def generate_answer(
    query: str,
    results: Sequence[SearchResult],
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout: float = 120.0,
    post_json: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
) -> str:
    """Demande à Ollama une réponse fondée sur les passages retrouvés."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Le nom du modèle Ollama ne peut pas être vide.")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("L'adresse d'Ollama ne peut pas être vide.")
    if timeout <= 0:
        raise ValueError("Le délai d'attente doit être positif.")

    messages = build_messages(query, results)
    payload = {
        "model": model.strip(),
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    endpoint = f"{base_url.rstrip('/')}/api/chat"
    requester = post_json or _post_json

    data = requester(endpoint, payload, timeout)
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise OllamaError(
            "Ollama n'a renvoyé aucun texte. Vérifiez que le modèle est installé "
            f"(`ollama pull {model.strip()}`)."
        )
    return content.strip()
