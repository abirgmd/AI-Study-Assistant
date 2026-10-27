"""Tests du client Ollama, sans appel réseau réel."""

from __future__ import annotations

from typing import Any

import pytest

from src.llm import (
    OllamaError,
    build_context,
    build_messages,
    generate_answer,
)
from src.module import SearchResult


RESULTS = [
    SearchResult(
        note_id="n1",
        title="Sur-apprentissage",
        passage="La régularisation limite le sur-apprentissage.",
        score=0.91,
    ),
    SearchResult(
        note_id="n2",
        title="Généralisation",
        passage="Un modèle doit généraliser à des données nouvelles.",
        score=0.84,
    ),
]


def test_build_context_numbers_sources() -> None:
    context = build_context(RESULTS)

    assert context.startswith("[1] Sur-apprentissage")
    assert "[2] Généralisation" in context
    assert "régularisation" in context


def test_build_messages_contains_question_and_sources() -> None:
    messages = build_messages("Comment éviter le sur-apprentissage ?", RESULTS)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Comment éviter le sur-apprentissage ?" in messages[1]["content"]
    assert "[1] Sur-apprentissage" in messages[1]["content"]
    assert "uniquement à partir des extraits" in messages[0]["content"]


def test_generate_answer_parses_ollama_response() -> None:
    captured: dict[str, Any] = {}

    def fake_post(
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "message": {
                "content": "La régularisation limite ce phénomène [1].\nSources : [1]"
            }
        }

    answer = generate_answer(
        "Comment éviter le sur-apprentissage ?",
        RESULTS,
        model="llama3.2",
        base_url="http://localhost:11434/",
        timeout=30,
        post_json=fake_post,
    )

    assert answer.startswith("La régularisation")
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["payload"]["model"] == "llama3.2"
    assert captured["payload"]["stream"] is False
    assert captured["timeout"] == 30


def test_generate_answer_rejects_empty_results() -> None:
    with pytest.raises(ValueError):
        generate_answer("Question", [])


def test_generate_answer_rejects_missing_content() -> None:
    def fake_post(
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        return {"done": True}

    with pytest.raises(OllamaError):
        generate_answer(
            "Question",
            RESULTS,
            post_json=fake_post,
        )
